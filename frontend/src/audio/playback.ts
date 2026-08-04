import { FeedbackCueLifecycle } from "./feedback";

export type PlaybackSchedule = {
  receivedPerfMs: number;
  decodeCompletePerfMs: number;
  scheduledPerfMs: number;
  playbackStartPerfMs: number;
  playbackEndPerfMs: number;
  durationMs: number;
};

export class PcmPlaybackQueue {
  private readonly context = new AudioContext();
  private readonly answerGain = this.context.createGain();
  private readonly feedbackGain = this.context.createGain();
  private readonly feedbackLifecycle = new FeedbackCueLifecycle();
  private readonly feedbackBuffers = new Map<string, AudioBuffer>();
  private sampleRateHz = 24000;
  private nextStartTime = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private idleWaiters: Array<() => void> = [];
  private feedbackSource: AudioBufferSourceNode | null = null;

  constructor() {
    this.answerGain.connect(this.context.destination);
    this.feedbackGain.gain.value = 0.45;
    this.feedbackGain.connect(this.context.destination);
  }

  setSampleRate(sampleRateHz: number): void {
    this.sampleRateHz = sampleRateHz;
  }

  async enqueue(pcm: ArrayBuffer): Promise<PlaybackSchedule> {
    this.cancelAllFeedback();
    await this.context.resume();
    const receivedPerfMs = performance.now();
    const samples = new Int16Array(pcm);
    const buffer = this.context.createBuffer(1, samples.length, this.sampleRateHz);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      channel[index] = samples[index] / 32768;
    }
    const decodeCompletePerfMs = performance.now();
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.answerGain);
    const startTime = Math.max(this.context.currentTime + 0.01, this.nextStartTime);
    this.nextStartTime = startTime + buffer.duration;
    this.sources.add(source);
    source.onended = () => {
      this.sources.delete(source);
      if (this.sources.size === 0) {
        this.idleWaiters.splice(0).forEach((resolve) => resolve());
      }
    };
    source.start(startTime);
    const contextToPerformanceOffset = performance.now() - this.context.currentTime * 1000;
    const scheduledPerfMs = performance.now();
    return {
      receivedPerfMs,
      decodeCompletePerfMs,
      scheduledPerfMs,
      playbackStartPerfMs: contextToPerformanceOffset + startTime * 1000,
      playbackEndPerfMs: contextToPerformanceOffset + (startTime + buffer.duration) * 1000,
      durationMs: buffer.duration * 1000,
    };
  }

  async preloadFeedback(key: string, url: string): Promise<void> {
    if (this.feedbackBuffers.has(key) || this.contextIsClosed()) return;
    try {
      const response = await fetch(url, { cache: "force-cache" });
      if (!response.ok) return;
      const encoded = await response.arrayBuffer();
      if (this.contextIsClosed()) return;
      const decoded = await this.context.decodeAudioData(encoded.slice(0));
      if (!this.contextIsClosed()) this.feedbackBuffers.set(key, decoded);
    } catch {
      // Feedback is optional. Asset/network/decode failures never fail a call.
    }
  }

  async playFeedback(
    turnId: string,
    cueId: string,
    key: string,
  ): Promise<number | null> {
    const generation = this.feedbackLifecycle.begin(turnId, cueId);
    const buffer = this.feedbackBuffers.get(key);
    if (!buffer || this.contextIsClosed()) return null;
    try {
      await this.context.resume();
    } catch {
      return null;
    }
    if (!this.feedbackLifecycle.canStart(turnId, cueId, generation)) return null;

    this.stopFeedbackSource(0);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.feedbackGain);
    this.feedbackGain.gain.cancelScheduledValues(this.context.currentTime);
    this.feedbackGain.gain.setValueAtTime(0.45, this.context.currentTime);
    const startTime = this.context.currentTime + 0.005;
    const contextToPerformanceOffset = performance.now() - this.context.currentTime * 1000;
    this.feedbackSource = source;
    source.onended = () => {
      if (this.feedbackSource === source) this.feedbackSource = null;
    };
    source.start(startTime);
    return contextToPerformanceOffset + startTime * 1000;
  }

  cancelFeedback(turnId: string, cueId: string): void {
    if (!this.feedbackLifecycle.cancel(turnId, cueId)) return;
    this.stopFeedbackSource(0.02);
  }

  cancelAllFeedback(): void {
    this.feedbackLifecycle.invalidate();
    this.stopFeedbackSource(0.02);
  }

  private stopFeedbackSource(fadeSeconds: number): void {
    const source = this.feedbackSource;
    if (source == null || this.contextIsClosed()) return;
    const now = this.context.currentTime;
    this.feedbackGain.gain.cancelScheduledValues(now);
    this.feedbackGain.gain.setValueAtTime(this.feedbackGain.gain.value, now);
    this.feedbackGain.gain.linearRampToValueAtTime(0, now + fadeSeconds);
    try {
      source.stop(now + fadeSeconds);
    } catch {
      // A source may have ended between lookup and stop().
    }
    this.feedbackSource = null;
  }

  async whenIdle(): Promise<void> {
    if (this.sources.size === 0) return;
    await new Promise<void>((resolve) => this.idleWaiters.push(resolve));
  }

  flush(): void {
    this.sources.forEach((source) => {
      try {
        source.stop();
      } catch {
        // A source may have ended between the set lookup and stop().
      }
    });
    this.sources.clear();
    this.idleWaiters.splice(0).forEach((resolve) => resolve());
    this.nextStartTime = this.context.currentTime;
  }

  async close(): Promise<void> {
    this.cancelAllFeedback();
    this.flush();
    if (this.context.state !== "closed") {
      await this.context.close();
    }
  }

  private contextIsClosed(): boolean {
    return this.context.state === "closed";
  }
}
