import { useCallback, useEffect, useRef, useState } from "react";

import {
  executeTodoTool,
  loadTodos,
  type Todo,
  type TodoToolName,
} from "../../store/todos";
import { isAuthenticationExpiredError } from "../../api/errors";
import { turnIndexOf } from "../latency";
import { VoiceClient } from "../../voice/client";
import type { ServerEvent, TurnMetricsEvent } from "../../voice/protocol";

export type CallStatus = "idle" | "connecting" | "active" | "ended" | "denied";

export type AgentStateName =
  | "listening"
  | "user_speaking"
  | "thinking"
  | "speaking"
  | "interrupted";

export type TimedTurnMetrics = {
  metric: TurnMetricsEvent;
  atSeconds: number;
};

export type TranscriptEntry = {
  who: "user" | "agent" | "system";
  text: string;
  languageCode: string | null;
  atSeconds: number;
  interrupted: boolean;
};

export type VoiceSessionState = {
  callStatus: CallStatus;
  endReason: string | null;
  agentState: AgentStateName;
  transportStatus: "transmitting_speech" | "silence_not_transmitting" | null;
  sessionId: string | null;
  elapsedSeconds: number;
  sessionCostPaise: number;
  balancePaise: number | null;
  lowBalance: boolean;
  userText: string;
  agentText: string;
  agentTurnInterrupted: boolean;
  languageCode: string | null;
  languageFlash: boolean;
  log: TranscriptEntry[];
  metrics: TimedTurnMetrics[];
  todos: Todo[];
  agentTodoToast: string;
  muted: boolean;
  error: string;
};

const INITIAL_STATE: VoiceSessionState = {
  callStatus: "idle",
  endReason: null,
  agentState: "listening",
  transportStatus: null,
  sessionId: null,
  elapsedSeconds: 0,
  sessionCostPaise: 0,
  balancePaise: null,
  lowBalance: false,
  userText: "",
  agentText: "",
  agentTurnInterrupted: false,
  languageCode: null,
  languageFlash: false,
  log: [],
  metrics: [],
  todos: [],
  agentTodoToast: "",
  muted: false,
  error: "",
};

function isPermissionError(message: string): boolean {
  return /notallowed|permission|denied/i.test(message);
}

export function useVoiceSession(
  token: string,
  onBalanceChange?: (balancePaise: number) => void,
  onAuthenticationExpired?: () => void,
) {
  const [state, setState] = useState<VoiceSessionState>(INITIAL_STATE);
  const clientRef = useRef<VoiceClient | null>(null);
  // Incremented on every start attempt and on teardown. Awaits inside start()
  // re-check it so overlapping attempts (React StrictMode double effects,
  // rapid retries) collapse to exactly one live client and one session.
  const attemptRef = useRef(0);
  const cleanupRef = useRef<Promise<void>>(Promise.resolve());
  const elapsedRef = useRef(0);
  const todosBeforeRef = useRef<Todo[]>([]);
  const toastTimerRef = useRef<number | null>(null);
  const flashTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setState((current) => ({ ...current, todos: loadTodos() }));
    return () => {
      attemptRef.current += 1;
      const client = clientRef.current;
      clientRef.current = null;
      void client?.stop();
      if (toastTimerRef.current != null) window.clearTimeout(toastTimerRef.current);
      if (flashTimerRef.current != null) window.clearTimeout(flashTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (state.callStatus !== "active") return;
    const interval = window.setInterval(() => {
      elapsedRef.current += 1;
      setState((current) => ({ ...current, elapsedSeconds: elapsedRef.current }));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [state.callStatus]);

  const showAgentTodoToast = useCallback((message: string) => {
    setState((current) => ({ ...current, agentTodoToast: message }));
    if (toastTimerRef.current != null) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => {
      setState((current) => ({ ...current, agentTodoToast: "" }));
    }, 3600);
  }, []);

  const retireClient = useCallback((client: VoiceClient) => {
    if (clientRef.current === client) clientRef.current = null;
    const cleanup = client.stop().catch(() => undefined);
    cleanupRef.current = Promise.allSettled([cleanupRef.current, cleanup]).then(() => undefined);
  }, []);

  // Authentication can expire because of a parallel HTTP request while a
  // previously-authorized voice socket is still active. Token loss must stop
  // that socket and microphone so a hidden session cannot keep billing.
  useEffect(() => {
    if (token) return;
    attemptRef.current += 1;
    const client = clientRef.current;
    clientRef.current = null;
    if (client) retireClient(client);
  }, [token, retireClient]);

  const start = useCallback(async () => {
    if (clientRef.current) return;
    const attempt = ++attemptRef.current;
    await cleanupRef.current;
    if (attempt !== attemptRef.current || clientRef.current) return;
    elapsedRef.current = 0;
    todosBeforeRef.current = loadTodos();
    setState((current) => ({
      ...INITIAL_STATE,
      todos: current.todos,
      balancePaise: current.balancePaise,
      callStatus: "connecting",
    }));

    // Resolve the mic permission BEFORE opening the WebSocket: the server
    // starts billing the moment the session socket connects, so the call
    // must not connect while the permission prompt is still pending.
    try {
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((track) => track.stop());
    } catch (error) {
      if (attempt !== attemptRef.current) return;
      if (isAuthenticationExpiredError(error)) {
        onAuthenticationExpired?.();
        return;
      }
      const message = String(error);
      setState((current) => ({
        ...current,
        callStatus: isPermissionError(message) ? "denied" : "ended",
        endReason: isPermissionError(message) ? null : "error",
        error: isPermissionError(message) ? "" : message,
      }));
      return;
    }
    if (attempt !== attemptRef.current || clientRef.current) return;

    // Ignore events from any client that is no longer the tracked one, so a
    // superseded session can never fight the live one over UI state.
    let self: VoiceClient | null = null;
    const live = () => self != null && clientRef.current === self;

    const client = new VoiceClient(token, {
      onState: (value) => {
        if (!live()) return;
        if (value === "disconnected" || value.startsWith("ended")) {
          setState((current) => ({
            ...current,
            callStatus: "ended",
            endReason:
              current.endReason ??
              (value.includes("balance") ? "balance_exhausted" : "disconnected"),
          }));
          if (self != null) retireClient(self);
        }
      },
      onReady: (event) => {
        if (!live()) return;
        setState((current) => ({
          ...current,
          callStatus: "active",
          sessionId: event.session_id,
          balancePaise: event.balance_paise,
        }));
      },
      onAgentState: (event: Extract<ServerEvent, { type: "agent_state" }>) => {
        if (!live()) return;
        setState((current) => ({
          ...current,
          agentState: event.state,
          transportStatus: event.transport_status ?? current.transportStatus,
          agentTurnInterrupted:
            event.state === "interrupted" ? true : current.agentTurnInterrupted,
          log:
            event.state === "interrupted"
              ? markLastAgentInterrupted(current.log)
              : current.log,
        }));
      },
      onTranscript: (text, languageCode) => {
        if (!live()) return;
        const lang = languageCode ?? null;
        setState((current) => {
          const flash = lang != null && lang !== current.languageCode;
          if (flash) {
            if (flashTimerRef.current != null) window.clearTimeout(flashTimerRef.current);
            flashTimerRef.current = window.setTimeout(() => {
              setState((inner) => ({ ...inner, languageFlash: false }));
            }, 700);
          }
          return {
            ...current,
            userText: text,
            agentText: "",
            agentTurnInterrupted: false,
            languageCode: lang ?? current.languageCode,
            languageFlash: flash || current.languageFlash,
            log: [
              ...current.log,
              {
                who: "user" as const,
                text,
                languageCode: lang,
                atSeconds: elapsedRef.current,
                interrupted: false,
              },
            ],
          };
        });
      },
      onAgentText: (text) => {
        if (!live()) return;
        setState((current) => ({
          ...current,
          agentText: current.agentText ? `${current.agentText} ${text}` : text,
          log: [
            ...current.log,
            {
              who: "agent" as const,
              text,
              languageCode: null,
              atSeconds: elapsedRef.current,
              interrupted: false,
            },
          ],
        }));
      },
      onMetrics: (metric) => {
        if (!live()) return;
        setState((current) => {
          // The server re-sends turn_metrics for a turn once barge-in
          // timings are known, so upsert by turn_id instead of appending.
          const existing = current.metrics.find(
            (entry) => entry.metric.turn_id === metric.turn_id,
          );
          const merged = [
            { metric, atSeconds: existing?.atSeconds ?? elapsedRef.current },
            ...current.metrics.filter(
              (entry) => entry.metric.turn_id !== metric.turn_id,
            ),
          ]
            .sort(
              (a, b) => turnIndexOf(b.metric.turn_id) - turnIndexOf(a.metric.turn_id),
            )
            .slice(0, 24);
          return { ...current, metrics: merged };
        });
      },
      onInterrupted: (message) => {
        if (!live()) return;
        setState((current) => ({
          ...current,
          log: [
            ...current.log,
            {
              who: "system" as const,
              text: message,
              languageCode: null,
              atSeconds: elapsedRef.current,
              interrupted: false,
            },
          ],
        }));
      },
      onTodosChanged: (todos) => {
        if (!live()) return;
        const before = todosBeforeRef.current;
        todosBeforeRef.current = todos;
        const added = todos.find((todo) => !before.some((item) => item.id === todo.id));
        if (added) showAgentTodoToast(`Agent added: ${added.text}`);
        else if (todos.length < before.length) showAgentTodoToast("Agent updated your todos");
        else if (todos.some((todo) => todo.completed !== before.find((item) => item.id === todo.id)?.completed)) {
          showAgentTodoToast("Agent completed a todo");
        }
        setState((current) => ({ ...current, todos }));
      },
      onBilling: (billing) => {
        if (!live()) return;
        elapsedRef.current = Math.max(elapsedRef.current, billing.seconds);
        onBalanceChange?.(billing.balance_paise);
        setState((current) => ({
          ...current,
          elapsedSeconds: elapsedRef.current,
          sessionCostPaise: billing.session_cost_paise,
          balancePaise: billing.balance_paise,
          lowBalance: billing.low_balance,
          endReason: billing.terminated_reason ?? current.endReason,
        }));
      },
      onCallEnded: (event) => {
        if (!live()) return;
        setState((current) => ({
          ...current,
          callStatus: "ended",
          endReason: event.reason,
        }));
      },
      onError: (message) => {
        if (!live()) return;
        setState((current) => ({ ...current, error: message }));
      },
      onAuthenticationExpired: () => {
        if (live()) onAuthenticationExpired?.();
      },
    });
    self = client;

    clientRef.current = client;
    try {
      await client.start();
    } catch (error) {
      if (clientRef.current === client) clientRef.current = null;
      await client.stop().catch(() => undefined);
      if (attempt !== attemptRef.current) return;
      const message = String(error);
      setState((current) => ({
        ...current,
        callStatus: isPermissionError(message) ? "denied" : "ended",
        endReason: isPermissionError(message) ? null : "error",
        error: isPermissionError(message) ? "" : message,
      }));
    }
  }, [token, onBalanceChange, onAuthenticationExpired, retireClient, showAgentTodoToast]);

  const stop = useCallback(async () => {
    attemptRef.current += 1;
    const client = clientRef.current;
    clientRef.current = null;
    if (client) retireClient(client);
    await cleanupRef.current;
    setState((current) => ({
      ...current,
      callStatus: current.callStatus === "active" || current.callStatus === "connecting"
        ? "ended"
        : current.callStatus,
      endReason: current.endReason ?? "user",
      muted: false,
    }));
  }, [retireClient]);

  const setMuted = useCallback((muted: boolean) => {
    clientRef.current?.setMuted(muted);
    setState((current) => ({ ...current, muted }));
  }, []);

  const runTodoTool = useCallback(
    (name: TodoToolName, args: Record<string, unknown>) => {
      try {
        executeTodoTool(name, args);
      } catch {
        // Manual edits fail soft; the panel simply re-renders from storage.
      }
      const todos = loadTodos();
      todosBeforeRef.current = todos;
      setState((current) => ({ ...current, todos }));
    },
    [],
  );

  const reset = useCallback(async () => {
    const attempt = ++attemptRef.current;
    const client = clientRef.current;
    if (client) retireClient(client);
    await cleanupRef.current;
    if (attempt !== attemptRef.current) return;
    elapsedRef.current = 0;
    setState((current) => ({
      ...INITIAL_STATE,
      todos: current.todos,
      balancePaise: current.balancePaise,
    }));
  }, [retireClient]);

  return { state, start, stop, reset, setMuted, runTodoTool };
}

function markLastAgentInterrupted(log: TranscriptEntry[]): TranscriptEntry[] {
  const lastAgentIndex = log.map((entry) => entry.who).lastIndexOf("agent");
  if (lastAgentIndex < 0) return log;
  return log.map((entry, index) =>
    index === lastAgentIndex ? { ...entry, interrupted: true } : entry,
  );
}
