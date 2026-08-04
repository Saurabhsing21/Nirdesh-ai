const CAPTURE_MAGIC = [0x41, 0x44, 0x53, 0x48] as const;
const CAPTURE_VERSION = 1;
const CAPTURE_HEADER_BYTES = 21;

export function encodeCaptureFrame(
  captureSeq: number,
  captureTimeMs: number,
  pcm: ArrayBuffer,
): ArrayBuffer {
  const message = new ArrayBuffer(CAPTURE_HEADER_BYTES + pcm.byteLength);
  const view = new DataView(message);
  CAPTURE_MAGIC.forEach((byte, index) => view.setUint8(index, byte));
  view.setUint8(4, CAPTURE_VERSION);
  view.setBigUint64(5, BigInt(captureSeq), false);
  view.setFloat64(13, captureTimeMs, false);
  new Uint8Array(message, CAPTURE_HEADER_BYTES).set(new Uint8Array(pcm));
  return message;
}

export type ServerEvent =
  | {
      type: "ready";
      session_id: string;
      balance_paise: number;
      price_per_minute_paise: number;
      tts_sample_rate_hz: number;
      endpointing_strategy: "local_vad" | "sarvam";
      vad_model?: string;
      capabilities?: string[];
    }
  | {
      type: "billing";
      session_id: string;
      seconds: number;
      cost_paise: number;
      session_cost_paise: number;
      charged_paise: number;
      balance_paise: number;
      low_balance: boolean;
      warning: "low_balance" | null;
      final: boolean;
      terminated_reason: "balance_exhausted" | null;
    }
  | {
      type: "agent_state";
      state: "listening" | "user_speaking" | "thinking" | "speaking" | "interrupted";
      transmitting?: boolean;
      transport_status?: "transmitting_speech" | "silence_not_transmitting";
      detail?: string;
    }
  | {
      type: "final_transcript";
      turn_id: string;
      text: string;
      language_code?: string | null;
      language_probability?: number | null;
    }
  | { type: "agent_text"; text: string; turn_id: string }
  | {
      type: "audio_start";
      turn_id: string;
      last_speech_capture_seq: number;
      last_speech_capture_time_ms: number;
      speech_anchor_source?: string;
    }
  | {
      type: "response_cue";
      turn_id: string;
      cue_id: string;
      cue_key: "neutral_ack";
      language_code: string;
      delay_ms: number;
      last_speech_capture_time_ms: number;
    }
  | {
      type: "response_cue_cancel";
      turn_id: string;
      cue_id: string;
      reason: "answer_started" | "call_ended" | "new_user_speech" | "turn_cancelled";
    }
  | { type: "turn_complete"; turn_id: string }
  | { type: "interrupt"; turn_id: string; reason: "barge_in" }
  | {
      type: "interrupt_resolved";
      turn_id: string;
      barge_in_stop_ack_ms: number | null;
      played_audio_ms: number;
      tts_socket_teardown_status: "closed_and_discarded" | "already_closed";
    }
  | {
      type: "tool_request";
      call_id: string;
      name: "todo_add" | "todo_list" | "todo_complete" | "todo_delete";
      arguments: Record<string, unknown>;
    }
  | TurnMetricsEvent
  | { type: "call_ended"; reason: string }
  | { type: "error"; code?: string; message: string; balance_paise?: number };

export type TurnMetricsEvent = {
  type: "turn_metrics";
  turn_id: string;
  endpointing_strategy: "local_vad" | "sarvam";
  stages: Record<string, number | null>;
  derived: Record<string, number | null>;
  dimensions: Record<string, unknown>;
  tool_spans: Array<{
    name: string;
    call_id: string;
    duration_ms: number;
    outcome: string;
  }>;
  missing_timestamps: string[];
};

export function parseServerEvent(message: string): ServerEvent {
  const parsed = JSON.parse(message) as unknown;
  if (typeof parsed !== "object" || parsed == null || !("type" in parsed)) {
    throw new Error("Invalid voice server event");
  }
  const event = parsed as Record<string, unknown>;
  if (event.type === "response_cue") {
    if (
      typeof event.turn_id !== "string" ||
      typeof event.cue_id !== "string" ||
      event.cue_key !== "neutral_ack" ||
      typeof event.language_code !== "string" ||
      typeof event.delay_ms !== "number" ||
      !Number.isFinite(event.delay_ms) ||
      event.delay_ms < 0 ||
      typeof event.last_speech_capture_time_ms !== "number" ||
      !Number.isFinite(event.last_speech_capture_time_ms)
    ) {
      throw new Error("Invalid response cue event");
    }
  }
  if (
    event.type === "response_cue_cancel" &&
    (typeof event.turn_id !== "string" || typeof event.cue_id !== "string")
  ) {
    throw new Error("Invalid response cue cancellation");
  }
  return event as ServerEvent;
}
