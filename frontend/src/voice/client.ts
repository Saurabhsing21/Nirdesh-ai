import { voiceWebSocketUrl } from "../api/auth";
import { errorForVoiceClose } from "../api/errors";
import { MicrophoneCapture } from "../audio/capture";
import { PcmPlaybackQueue } from "../audio/playback";
import { executeTodoTool, loadTodos, type Todo } from "../store/todos";
import {
  encodeCaptureFrame,
  parseServerEvent,
  type ServerEvent,
  type TurnMetricsEvent,
} from "./protocol";

export type VoiceClientCallbacks = {
  onState: (state: string) => void;
  onTranscript: (text: string, languageCode?: string | null) => void;
  onAgentText: (text: string) => void;
  onMetrics: (metrics: TurnMetricsEvent) => void;
  onInterrupted: (message: string) => void;
  onTodosChanged: (todos: Todo[]) => void;
  onBilling: (event: Extract<ServerEvent, { type: "billing" }>) => void;
  onError: (message: string) => void;
  onAuthenticationExpired?: () => void;
  // Optional structured hooks used by the redesigned UI; the legacy UI
  // relies only on the string-based callbacks above.
  onReady?: (event: Extract<ServerEvent, { type: "ready" }>) => void;
  onAgentState?: (event: Extract<ServerEvent, { type: "agent_state" }>) => void;
  onCallEnded?: (event: Extract<ServerEvent, { type: "call_ended" }>) => void;
};

export class VoiceClient {
  private socket: WebSocket | null = null;
  private readonly capture = new MicrophoneCapture();
  private readonly playback = new PcmPlaybackQueue();
  private captureSeq = 0;
  private currentAudioStart: Extract<ServerEvent, { type: "audio_start" }> | null = null;
  private currentThinkingTurnId: string | null = null;
  private playbackReportedForTurn: string | null = null;
  private playbackChain: Promise<void> = Promise.resolve();
  private acceptingAudio = false;
  private playedAudioMsByTurn = new Map<string, number>();
  private playbackEndByTurn = new Map<string, number>();
  private playbackStartByTurn = new Map<string, number>();
  private interruptedTurns = new Set<string>();
  private audioEpoch = 0;
  private muted = false;
  private serverEnded = false;
  private callEndedPromise: Promise<void> = Promise.resolve();
  private resolveCallEnded: (() => void) | null = null;
  private stopPromise: Promise<void> | null = null;

  constructor(
    private readonly token: string,
    private readonly callbacks: VoiceClientCallbacks,
  ) {}

  async start(): Promise<void> {
    const socket = new WebSocket(voiceWebSocketUrl(this.token));
    let resolveConnection: (() => void) | null = null;
    let rejectConnection: ((reason: Error) => void) | null = null;
    const connected = new Promise<void>((resolve, reject) => {
      resolveConnection = resolve;
      rejectConnection = reject;
    });
    this.serverEnded = false;
    this.callEndedPromise = new Promise((resolve) => {
      this.resolveCallEnded = resolve;
    });
    this.acceptingAudio = true;
    socket.binaryType = "arraybuffer";
    this.socket = socket;
    socket.onmessage = (event) => void this.handleMessage(event);
    socket.onclose = (event) => {
      if (rejectConnection != null) {
        rejectConnection(errorForVoiceClose(event.code));
        rejectConnection = null;
      }
      if (this.socket === socket) this.socket = null;
      this.resolveCallEnded?.();
      if (event.code === 4401) {
        this.callbacks.onAuthenticationExpired?.();
      } else if (!this.serverEnded) {
        this.callbacks.onState(
          event.code === 4403 ? "ended - balance exhausted" : "disconnected",
        );
      }
      // A remote close must release the microphone and AudioContexts even
      // when the UI never calls stop(), for example after a pipeline error.
      void this.stop().catch((error: unknown) => this.callbacks.onError(String(error)));
    };
    socket.onopen = () => {
      resolveConnection?.();
      resolveConnection = null;
      rejectConnection = null;
    };
    // The close event carries the useful application code; browser error
    // events intentionally do not expose handshake details.
    socket.onerror = () => undefined;
    await connected;
    if (this.socket !== socket) {
      // stop() ran while the socket was connecting; do not become a zombie
      // session that streams mic audio with playback disabled.
      socket.close(1000);
      return;
    }
    await this.capture.start((pcm, captureTimeMs) => {
      if (this.muted || socket.readyState !== WebSocket.OPEN) return;
      socket.send(encodeCaptureFrame(this.captureSeq, captureTimeMs, pcm));
      this.captureSeq += 1;
    });
    if (this.socket !== socket) {
      await this.capture.stop();
      socket.close(1000);
    }
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
  }

  isMuted(): boolean {
    return this.muted;
  }

  async stop(): Promise<void> {
    if (this.stopPromise == null) {
      this.stopPromise = this.performStop();
    }
    await this.stopPromise;
  }

  private async performStop(): Promise<void> {
    this.acceptingAudio = false;
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "end_call" }));
        await Promise.race([
          this.callEndedPromise,
          new Promise<void>((resolve) => window.setTimeout(resolve, 1500)),
        ]);
        if (socket.readyState === WebSocket.OPEN) socket.close(1000);
      } else if (socket.readyState === WebSocket.CONNECTING) {
        // Closing during the handshake aborts the connection so the server
        // never starts (and bills) a session nobody is attached to.
        socket.close();
      }
    }
    await this.capture.stop();
    await this.playbackChain;
    await this.playback.close();
  }

  private handleMessage(event: MessageEvent<string | ArrayBuffer>): void {
    if (event.data instanceof ArrayBuffer) {
      const pcm = event.data;
      const epoch = this.audioEpoch;
      this.playbackChain = this.playbackChain
        .then(() => this.handleAudio(pcm, epoch))
        .catch((error: unknown) => this.callbacks.onError(String(error)));
      return;
    }
    const message = parseServerEvent(event.data);
    switch (message.type) {
      case "ready":
        this.playback.setSampleRate(message.tts_sample_rate_hz);
        if (message.capabilities?.includes("response_cues_v1")) {
          void this.playback.preloadFeedback(
            "neutral_ack",
            "/audio/response-cues/neutral-ack.wav",
          );
        }
        this.callbacks.onReady?.(message);
        this.callbacks.onState("listening");
        break;
      case "agent_state":
        this.callbacks.onAgentState?.(message);
        this.callbacks.onState(
          message.detail ? `${message.state} - ${message.detail}` : message.state,
        );
        break;
      case "billing":
        this.callbacks.onBilling(message);
        break;
      case "final_transcript":
        this.currentThinkingTurnId = message.turn_id;
        this.callbacks.onTranscript(message.text, message.language_code);
        break;
      case "agent_text":
        this.callbacks.onAgentText(message.text);
        break;
      case "audio_start":
        this.playback.cancelAllFeedback();
        if (this.currentThinkingTurnId === message.turn_id) this.currentThinkingTurnId = null;
        this.currentAudioStart = message;
        break;
      case "response_cue":
        void this.handleResponseCue(message);
        break;
      case "response_cue_cancel":
        this.playback.cancelFeedback(message.turn_id, message.cue_id);
        if (this.currentThinkingTurnId === message.turn_id) this.currentThinkingTurnId = null;
        break;
      case "interrupt":
        this.handleInterrupt(message.turn_id);
        break;
      case "interrupt_resolved":
        this.callbacks.onInterrupted(
          `Turn ${message.turn_id.split(":").at(-1)} interruption acknowledged in ${
            message.barge_in_stop_ack_ms == null
              ? "n/a"
              : `${message.barge_in_stop_ack_ms.toFixed(1)} ms`
          }`,
        );
        break;
      case "tool_request":
        this.handleToolRequest(message);
        break;
      case "turn_metrics":
        this.callbacks.onMetrics(message);
        break;
      case "turn_complete":
        void this.reportPlaybackFinished(message.turn_id);
        break;
      case "error":
        this.callbacks.onError(message.message);
        break;
      case "call_ended":
        this.serverEnded = true;
        this.resolveCallEnded?.();
        this.callbacks.onCallEnded?.(message);
        this.callbacks.onState(
          message.reason === "balance_exhausted"
            ? "ended - balance exhausted"
            : "ended",
        );
        break;
      default:
        break;
    }
  }

  private handleToolRequest(
    message: Extract<ServerEvent, { type: "tool_request" }>,
  ): void {
    let result: Record<string, unknown>;
    try {
      result = executeTodoTool(message.name, message.arguments);
    } catch (error) {
      result = { ok: false, error: String(error) };
    }
    this.callbacks.onTodosChanged(loadTodos());
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: "tool_result",
          call_id: message.call_id,
          result,
        }),
      );
    }
  }

  private async handleResponseCue(
    message: Extract<ServerEvent, { type: "response_cue" }>,
  ): Promise<void> {
    if (
      !this.acceptingAudio ||
      this.currentThinkingTurnId !== message.turn_id ||
      this.interruptedTurns.has(message.turn_id)
    )
      return;
    const cueStartPerfMs = await this.playback.playFeedback(
      message.turn_id,
      message.cue_id,
      message.cue_key,
    );
    if (cueStartPerfMs == null || this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(
      JSON.stringify({
        type: "response_cue_started",
        turn_id: message.turn_id,
        cue_id: message.cue_id,
        cue_start_perf_ms: cueStartPerfMs,
        feedback_voice_to_voice_ms:
          cueStartPerfMs - message.last_speech_capture_time_ms,
      }),
    );
  }

  private async handleAudio(pcm: ArrayBuffer, epoch: number): Promise<void> {
    if (!this.acceptingAudio || epoch !== this.audioEpoch) return;
    const marker = this.currentAudioStart;
    if (!marker || this.interruptedTurns.has(marker.turn_id)) return;
    const schedule = await this.playback.enqueue(pcm);
    if (marker) {
      this.playedAudioMsByTurn.set(
        marker.turn_id,
        (this.playedAudioMsByTurn.get(marker.turn_id) ?? 0) + schedule.durationMs,
      );
      this.playbackEndByTurn.set(marker.turn_id, schedule.playbackEndPerfMs);
      if (!this.playbackStartByTurn.has(marker.turn_id)) {
        this.playbackStartByTurn.set(marker.turn_id, schedule.playbackStartPerfMs);
      }
    }
    if (
      marker &&
      this.playbackReportedForTurn !== marker.turn_id &&
      this.socket?.readyState === WebSocket.OPEN
    ) {
      this.playbackReportedForTurn = marker.turn_id;
      this.socket.send(
        JSON.stringify({
          type: "playback_started",
          turn_id: marker.turn_id,
          last_speech_capture_seq: marker.last_speech_capture_seq,
          audio_received_perf_ms: schedule.receivedPerfMs,
          decode_complete_perf_ms: schedule.decodeCompletePerfMs,
          scheduled_perf_ms: schedule.scheduledPerfMs,
          playback_start_perf_ms: schedule.playbackStartPerfMs,
          e2e_voice_to_voice_ms:
            schedule.playbackStartPerfMs - marker.last_speech_capture_time_ms,
          e2e_anchor_source: marker.speech_anchor_source,
        }),
      );
    }
  }

  private async reportPlaybackFinished(turnId: string): Promise<void> {
    await this.playbackChain;
    await this.playback.whenIdle();
    if (
      this.socket?.readyState !== WebSocket.OPEN ||
      this.interruptedTurns.has(turnId)
    )
      return;
    this.socket.send(
      JSON.stringify({
        type: "playback_finished",
        turn_id: turnId,
        playback_end_perf_ms: this.playbackEndByTurn.get(turnId) ?? performance.now(),
        played_audio_ms: this.playedAudioMsByTurn.get(turnId) ?? 0,
      }),
    );
  }

  private handleInterrupt(turnId: string): void {
    const interruptReceivedPerfMs = performance.now();
    const generatedAudioMs = this.playedAudioMsByTurn.get(turnId) ?? 0;
    const playbackStartPerfMs = this.playbackStartByTurn.get(turnId);
    const playedAudioMs =
      playbackStartPerfMs == null
        ? 0
        : Math.min(
            generatedAudioMs,
            Math.max(0, interruptReceivedPerfMs - playbackStartPerfMs),
          );
    this.interruptedTurns.add(turnId);
    this.audioEpoch += 1;
    this.currentAudioStart = null;
    if (this.currentThinkingTurnId === turnId) this.currentThinkingTurnId = null;
    this.playback.cancelAllFeedback();
    this.playback.flush();
    const queueClearedPerfMs = performance.now();
    this.callbacks.onState("interrupted - user started speaking");
    this.callbacks.onInterrupted(
      `Turn ${turnId.split(":").at(-1)} interrupted after ${playedAudioMs.toFixed(1)} ms played`,
    );
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: "interrupt_ack",
          turn_id: turnId,
          interrupt_received_perf_ms: interruptReceivedPerfMs,
          queue_cleared_perf_ms: queueClearedPerfMs,
          audio_queue_cleared: true,
          played_audio_ms: playedAudioMs,
        }),
      );
    }
  }
}
