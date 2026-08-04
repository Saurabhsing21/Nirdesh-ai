import { useEffect, useState } from "react";

import { formatDuration, formatRupees } from "../format";
import { e2eColor, turnE2e } from "../latency";
import type { useVoiceSession } from "../hooks/useVoiceSession";
import { LatencyPanel } from "../components/LatencyPanel";
import { TranscriptDrawer } from "../components/TranscriptDrawer";
import { TodosPanel } from "../components/TodosPanel";

type CallPageProps = {
  session: ReturnType<typeof useVoiceSession>;
  goWallet: () => void;
  walletBalancePaise: number | null;
};

const WAVE_BARS = Array.from({ length: 28 }, (_, i) => ({
  hue: (262 - i * 3.3).toFixed(0),
  height: Math.min(
    Math.max(Math.round(64 + Math.sin(i * 0.9) * 22 + Math.sin(i * 0.37 + 1.3) * 30), 16),
    118,
  ),
}));

const ENDED_COPY: Record<string, [string, string]> = {
  user: ["Call ended", "You hung up."],
  balance_exhausted: [
    "Balance exhausted",
    "Your wallet reached ₹0.00, so the call was cut off automatically. Top up to keep talking.",
  ],
  error: [
    "Connection error",
    "Something went wrong in the voice pipeline. You were only charged for connected time.",
  ],
  disconnected: [
    "Connection lost",
    "The voice channel closed unexpectedly. You were only charged for connected time.",
  ],
};

const COACH_STEPS = [
  "Just speak — the agent is always listening, and it detects your language automatically.",
  "Speak over the agent any time — it stops instantly and listens to you.",
  "Your todos live here. Say “add buy milk to my list” and watch the agent update them.",
];

export function CallPage({ session, goWallet, walletBalancePaise }: CallPageProps) {
  const { state, start, stop, setMuted, runTodoTool } = session;
  const [todosOpen, setTodosOpen] = useState(true);
  // Always open on load; collapses only when clicked.
  const [latOpen, setLatOpen] = useState(true);
  const [logOpen, setLogOpen] = useState(false);
  const [coach, setCoach] = useState(-1);

  const status = state.callStatus;
  const muted = state.muted;
  const agent = state.agentState;

  useEffect(() => {
    if (status !== "active") return;
    let coached = true;
    try {
      coached = !!localStorage.getItem("nirdeshai_coached");
    } catch {
      /* storage unavailable */
    }
    if (!coached) setCoach(0);
  }, [status]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const tag = ((event.target as HTMLElement | null)?.tagName ?? "").toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      if ((event.key === "m" || event.key === "M") && status === "active") {
        setMuted(!muted);
      }
      if (event.key === "Escape") {
        if (logOpen) setLogOpen(false);
        else if (status === "active" || status === "connecting") void stop();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [status, muted, logOpen, setMuted, stop]);

  function finishCoach() {
    try {
      localStorage.setItem("nirdeshai_coached", "1");
    } catch {
      /* storage unavailable */
    }
    setCoach(-1);
  }

  const waveAnim = muted
    ? "waveMuted 3s ease-in-out infinite"
    : agent === "speaking"
      ? "waveSpeak 0.85s ease-in-out infinite"
      : agent === "user_speaking" || agent === "interrupted"
        ? "waveSpeak 1.15s ease-in-out infinite"
        : agent === "thinking"
          ? "waveThink 1.4s ease-in-out infinite"
          : "waveListen 2.6s ease-in-out infinite";
  const waveStep =
    agent === "speaking" || agent === "user_speaking" || agent === "interrupted"
      ? 0.05
      : agent === "thinking"
        ? 0.07
        : 0.11;
  const silentIdle =
    !muted &&
    state.transportStatus === "silence_not_transmitting" &&
    (agent === "listening" || agent === "user_speaking");

  const stateLabel = muted
    ? "Muted"
    : agent === "interrupted"
      ? "Interrupted"
      : agent === "user_speaking"
        ? "You're speaking"
        : agent === "speaking"
          ? "Speaking"
          : agent === "thinking"
            ? "Thinking…"
            : "Listening…";
  const stateLabelColor = agent === "interrupted" && !muted ? "#9A6A0B" : "#6B6B66";

  const balance = state.balancePaise ?? walletBalancePaise;
  let balPillBg = "#E8F3EC";
  let balPillFg = "#1F7A46";
  const balanceLow = state.lowBalance || (balance != null && balance < 100);
  const balanceCritical = balance != null && balance < 25;
  if (balanceCritical) {
    balPillBg = "#FBEAEA";
    balPillFg = "#B3352E";
  } else if (balanceLow) {
    balPillBg = "#FCF3E0";
    balPillFg = "#9A6A0B";
  }

  const latestTurn = state.metrics[0] ?? null;
  const latestE2e = latestTurn ? turnE2e(latestTurn.metric) : null;

  const endedReason = state.endReason ?? "user";
  const [endedTitle, endedSubBase] = ENDED_COPY[endedReason] ?? ENDED_COPY.user;
  const endedSub =
    endedReason === "user"
      ? `${endedSubBase} ${formatDuration(state.elapsedSeconds)} · ${formatRupees(state.sessionCostPaise)} charged to your wallet.`
      : endedSubBase;

  const sessionLabel = state.sessionId ? `session ${state.sessionId.slice(0, 8)}` : "";
  const showSampleChip =
    status === "active" && !state.userText && !state.agentText && !muted;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 24px",
          borderBottom: "1px solid #E5E5E1",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600 }}>
            {status === "active" || status === "connecting" ? "Live call" : "Call"}
          </div>
          <div
            style={{
              fontSize: 11.5,
              fontFamily: "ui-monospace,'SF Mono',monospace",
              color: "#A6A6A0",
            }}
          >
            {sessionLabel}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            type="button"
            onClick={() => setLogOpen(true)}
            className="hovBorder"
            style={{
              border: "1px solid #E5E5E1",
              background: "#FFFFFF",
              borderRadius: 999,
              padding: "4px 12px",
              fontSize: 12,
              fontWeight: 500,
              color: "#6B6B66",
            }}
          >
            Transcript
          </button>
          <button
            type="button"
            onClick={() => setLatOpen(!latOpen)}
            className="hovBorder"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 7,
              border: `1px solid ${latOpen ? "#B9B9B2" : "#E5E5E1"}`,
              background: latOpen ? "#F7F7F5" : "#FFFFFF",
              borderRadius: 999,
              padding: "4px 12px",
              fontSize: 12,
              fontWeight: 500,
              color: latOpen ? "#111110" : "#6B6B66",
            }}
          >
            Latency
            {latestE2e != null && (
              <span
                style={{
                  fontSize: 11,
                  fontFamily: "ui-monospace,'SF Mono',monospace",
                  fontWeight: 600,
                  color: e2eColor(latestE2e),
                }}
              >
                {Math.round(latestE2e)} ms
              </span>
            )}
          </button>
          {state.languageCode && status === "active" && (
            <span
              style={{
                fontSize: 11.5,
                fontFamily: "ui-monospace,'SF Mono',monospace",
                border: "1px solid #E5E5E1",
                background: "#FFFFFF",
                borderRadius: 999,
                padding: "4px 10px",
                color: "#111110",
                animation: state.languageFlash ? "langFlip 0.55s ease" : "none",
              }}
            >
              {state.languageCode}
            </span>
          )}
          <span style={{ fontSize: 13, fontVariantNumeric: "tabular-nums", color: "#111110" }}>
            {formatDuration(state.elapsedSeconds)}
          </span>
          <span style={{ fontSize: 13, fontVariantNumeric: "tabular-nums", color: "#6B6B66" }}>
            −{formatRupees(state.sessionCostPaise)}
          </span>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12.5,
              fontWeight: 500,
              fontVariantNumeric: "tabular-nums",
              borderRadius: 999,
              padding: "5px 12px",
              background: balPillBg,
              color: balPillFg,
            }}
          >
            {balance == null ? "—" : formatRupees(balance)}
            {(balanceCritical || balanceLow) && (
              <button
                type="button"
                onClick={goWallet}
                style={{
                  border: "none",
                  background: "none",
                  color: "inherit",
                  fontSize: 12,
                  fontWeight: 600,
                  textDecoration: "underline",
                  padding: 0,
                }}
              >
                Top up
              </button>
            )}
          </span>
        </div>
      </header>

      <div style={{ flex: 1, display: "flex", minHeight: 0, position: "relative" }}>
        {latOpen ? (
          <LatencyPanel turns={state.metrics} onCollapse={() => setLatOpen(false)} />
        ) : (
          <button
            type="button"
            onClick={() => setLatOpen(true)}
            className="hovBgSoft"
            style={{
              alignSelf: "flex-start",
              margin: "16px 0 0 16px",
              border: "1px solid #E5E5E1",
              background: "#FFFFFF",
              borderRadius: 999,
              padding: "6px 14px",
              fontSize: 12.5,
              color: "#6B6B66",
            }}
          >
            Latency ›
          </button>
        )}

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
            minWidth: 0,
          }}
        >
          {status === "idle" && (
            <>
              <div
                style={{ width: 140, height: 140, borderRadius: "50%", background: "#E2E2DD" }}
              />
              <div
                style={{ marginTop: 26, fontSize: 19, fontWeight: 600, letterSpacing: "-0.01em" }}
              >
                Ready when you are
              </div>
              <div
                style={{
                  marginTop: 8,
                  fontSize: 13.5,
                  color: "#6B6B66",
                  maxWidth: 380,
                  textAlign: "center",
                  lineHeight: 1.55,
                }}
              >
                Calls are billed per second from your wallet
                {balance != null ? ` (${formatRupees(balance)} available)` : ""}. Your browser
                will ask for microphone access when you start.
              </div>
              <button
                type="button"
                onClick={() => void start()}
                className="hovDark"
                style={{
                  marginTop: 24,
                  border: "none",
                  borderRadius: 999,
                  background: "#111110",
                  color: "#FFFFFF",
                  fontSize: 13.5,
                  fontWeight: 500,
                  padding: "10px 22px",
                }}
              >
                Start call
              </button>
            </>
          )}

          {status === "connecting" && (
            <>
              <div
                style={{
                  width: 176,
                  height: 176,
                  borderRadius: "50%",
                  background: "#E8E8E4",
                  animation: "orbBreathe 1.5s ease-in-out infinite",
                }}
              />
              <div
                style={{
                  marginTop: 24,
                  fontSize: 12,
                  fontWeight: 500,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: "#6B6B66",
                }}
              >
                Connecting…
              </div>
              <div style={{ marginTop: 8, fontSize: 12.5, color: "#A6A6A0" }}>
                Requesting microphone &amp; opening a secure channel
              </div>
            </>
          )}

          {status === "active" && (
            <>
              <div
                style={{
                  height: 220,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 5, height: 130 }}>
                  {WAVE_BARS.map((bar, index) => (
                    <div
                      key={index}
                      style={{
                        width: 6,
                        height: bar.height,
                        borderRadius: 3,
                        background: muted ? "#D5D5D0" : `oklch(0.62 0.17 ${bar.hue})`,
                        opacity: silentIdle ? 0.55 : 1,
                        transformOrigin: "center",
                        animation: waveAnim,
                        animationDelay: `${(-(index * waveStep)).toFixed(2)}s`,
                      }}
                    />
                  ))}
                </div>
              </div>
              <div
                style={{
                  marginTop: 20,
                  fontSize: 12,
                  fontWeight: 500,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: stateLabelColor,
                }}
              >
                {stateLabel}
              </div>
              {state.transportStatus != null && !muted && (
                <span
                  style={{
                    marginTop: 10,
                    fontSize: 11,
                    fontFamily: "ui-monospace,'SF Mono',monospace",
                    border: "1px solid #E5E5E1",
                    background: "#FFFFFF",
                    borderRadius: 999,
                    padding: "3px 10px",
                    color:
                      state.transportStatus === "transmitting_speech" ? "#1F7A46" : "#6B6B66",
                  }}
                >
                  {state.transportStatus === "transmitting_speech"
                    ? "transmitting speech"
                    : "silence — not transmitting"}
                </span>
              )}

              <div
                style={{
                  width: 560,
                  maxWidth: "82%",
                  marginTop: 26,
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                  minHeight: 74,
                }}
              >
                <div
                  style={{
                    alignSelf: "flex-end",
                    textAlign: "right",
                    fontSize: 15,
                    lineHeight: 1.55,
                    maxWidth: "86%",
                    color: "#6B6B66",
                  }}
                >
                  {state.userText}
                </div>
                <div
                  style={{
                    alignSelf: "flex-start",
                    textAlign: "left",
                    fontSize: 15,
                    lineHeight: 1.55,
                    maxWidth: "86%",
                    color: "#111110",
                  }}
                >
                  {state.agentText}
                  {state.agentTurnInterrupted && (
                    <div
                      style={{
                        marginTop: 6,
                        fontSize: 11.5,
                        color: "#9A6A0B",
                        borderLeft: "2px solid #EED9A8",
                        paddingLeft: 8,
                      }}
                    >
                      ⏸ interrupted — user started speaking
                    </div>
                  )}
                </div>
              </div>

              <div style={{ marginTop: 30, display: "flex", alignItems: "center", gap: 20 }}>
                <button
                  type="button"
                  onClick={() => setMuted(!muted)}
                  title="Mute microphone"
                  style={{
                    width: 52,
                    height: 52,
                    borderRadius: "50%",
                    border: `1px solid ${muted ? "#111110" : "#E5E5E1"}`,
                    background: muted ? "#111110" : "#FFFFFF",
                    color: muted ? "#FFFFFF" : "#111110",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    transition: "background .15s",
                  }}
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 16 16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  >
                    <rect x="6" y="1.5" width="4" height="7.5" rx="2" />
                    <path d="M3.5 7.5 a4.5 4.5 0 0 0 9 0" />
                    <line x1="8" y1="12.5" x2="8" y2="14.5" />
                    <line x1="2.5" y1="2" x2="13.5" y2="14" opacity={muted ? 1 : 0} />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={() => void stop()}
                  title="End call"
                  className="hovHangup"
                  style={{
                    width: 62,
                    height: 62,
                    borderRadius: "50%",
                    border: "none",
                    background: "#DC2626",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: "0 14px 28px -12px rgba(220,38,38,0.55)",
                  }}
                >
                  <svg width="22" height="22" viewBox="0 0 16 16">
                    <rect x="2.5" y="6.5" width="11" height="3" rx="1.5" fill="#FFFFFF" />
                  </svg>
                </button>
              </div>

              {muted && (
                <button
                  type="button"
                  onClick={() => setMuted(false)}
                  className="hovDark"
                  style={{
                    marginTop: 16,
                    border: "none",
                    borderRadius: 999,
                    background: "#111110",
                    color: "#FFFFFF",
                    padding: "8px 20px",
                    fontSize: 12.5,
                    fontWeight: 500,
                    animation: "fadeUp .25s ease",
                  }}
                >
                  Tap to talk
                </button>
              )}

              <div
                style={{
                  marginTop: 18,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 14,
                  flexWrap: "wrap",
                  fontSize: 12.5,
                  color: "#A6A6A0",
                }}
              >
                <span>Just start speaking to interrupt the agent.</span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  <span
                    style={{
                      border: "1px solid #E5E5E1",
                      background: "#FFFFFF",
                      borderRadius: 5,
                      padding: "1px 6px",
                      fontSize: 10.5,
                      fontFamily: "ui-monospace,'SF Mono',monospace",
                      color: "#6B6B66",
                    }}
                  >
                    M
                  </span>
                  mute
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  <span
                    style={{
                      border: "1px solid #E5E5E1",
                      background: "#FFFFFF",
                      borderRadius: 5,
                      padding: "1px 6px",
                      fontSize: 10.5,
                      fontFamily: "ui-monospace,'SF Mono',monospace",
                      color: "#6B6B66",
                    }}
                  >
                    Esc
                  </span>
                  end call
                </span>
              </div>

              {showSampleChip && (
                <div
                  style={{
                    marginTop: 14,
                    border: "1px solid #D8DEF9",
                    background: "#EEF2FE",
                    color: "#3A57D4",
                    borderRadius: 999,
                    padding: "7px 16px",
                    fontSize: 12.5,
                    fontWeight: 500,
                    animation: "fadeUp .3s ease",
                  }}
                >
                  Try: “What will the weather be in Bengaluru tomorrow?”
                </div>
              )}
            </>
          )}

          {status === "ended" && (
            <>
              <div
                style={{ width: 140, height: 140, borderRadius: "50%", background: "#E2E2DD" }}
              />
              <div style={{ marginTop: 26, fontSize: 19, fontWeight: 600, letterSpacing: "-0.01em" }}>
                {endedTitle}
              </div>
              <div
                style={{
                  marginTop: 8,
                  fontSize: 13.5,
                  color: "#6B6B66",
                  maxWidth: 380,
                  textAlign: "center",
                  lineHeight: 1.55,
                }}
              >
                {endedSub}
              </div>
              {state.error && (
                <div
                  style={{
                    marginTop: 10,
                    fontSize: 11.5,
                    fontFamily: "ui-monospace,'SF Mono',monospace",
                    color: "#B3352E",
                    maxWidth: 420,
                    textAlign: "center",
                  }}
                >
                  {state.error}
                </div>
              )}
              <div style={{ marginTop: 24, display: "flex", gap: 10 }}>
                <button
                  type="button"
                  onClick={() => void start()}
                  className="hovDark"
                  style={{
                    border: "none",
                    borderRadius: 999,
                    background: "#111110",
                    color: "#FFFFFF",
                    fontSize: 13.5,
                    fontWeight: 500,
                    padding: "10px 22px",
                  }}
                >
                  Start a new call
                </button>
                {endedReason === "balance_exhausted" && (
                  <button
                    type="button"
                    onClick={goWallet}
                    className="hovBgSoft"
                    style={{
                      border: "1px solid #E5E5E1",
                      borderRadius: 999,
                      background: "#FFFFFF",
                      color: "#111110",
                      fontSize: 13.5,
                      fontWeight: 500,
                      padding: "10px 22px",
                    }}
                  >
                    Top up wallet
                  </button>
                )}
              </div>
            </>
          )}

          {status === "denied" && (
            <div
              style={{
                background: "#FFFFFF",
                border: "1px solid #E5E5E1",
                borderRadius: 16,
                padding: "32px 36px",
                maxWidth: 400,
                textAlign: "center",
              }}
            >
              <div
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: "50%",
                  background: "#F7F7F5",
                  border: "1px solid #E5E5E1",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  margin: "0 auto",
                  color: "#6B6B66",
                }}
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                >
                  <rect x="6" y="1.5" width="4" height="7.5" rx="2" />
                  <path d="M3.5 7.5 a4.5 4.5 0 0 0 9 0" />
                  <line x1="8" y1="12.5" x2="8" y2="14.5" />
                  <line x1="2.5" y1="2" x2="13.5" y2="14" />
                </svg>
              </div>
              <div style={{ marginTop: 18, fontSize: 16, fontWeight: 600 }}>
                Microphone access needed
              </div>
              <div style={{ marginTop: 8, fontSize: 13, color: "#6B6B66", lineHeight: 1.6 }}>
                Your browser blocked the microphone, so the agent can't hear you. Allow mic
                access in the address bar, then try again.
              </div>
              <button
                type="button"
                onClick={() => void start()}
                className="hovDark"
                style={{
                  marginTop: 20,
                  border: "none",
                  borderRadius: 999,
                  background: "#111110",
                  color: "#FFFFFF",
                  fontSize: 13,
                  fontWeight: 500,
                  padding: "9px 20px",
                }}
              >
                Try again
              </button>
            </div>
          )}
        </div>

        {todosOpen ? (
          <TodosPanel
            todos={state.todos}
            agentToast={state.agentTodoToast}
            onRunTool={runTodoTool}
            onCollapse={() => setTodosOpen(false)}
          />
        ) : (
          <button
            type="button"
            onClick={() => setTodosOpen(true)}
            className="hovBgSoft"
            style={{
              alignSelf: "flex-start",
              margin: "16px 16px 0 0",
              border: "1px solid #E5E5E1",
              background: "#FFFFFF",
              borderRadius: 999,
              padding: "6px 14px",
              fontSize: 12.5,
              color: "#6B6B66",
            }}
          >
            ‹ Todos
          </button>
        )}

        {coach >= 0 && status === "active" && (
          <div
            style={{
              position: "absolute",
              ...(coach === 0
                ? { left: "50%", top: "54%", transform: "translateX(-50%)" }
                : coach === 1
                  ? { left: "50%", bottom: 130, transform: "translateX(-50%)" }
                  : { right: 306, top: 84 }),
              zIndex: 55,
              background: "#111110",
              color: "#FFFFFF",
              borderRadius: 12,
              padding: "14px 16px",
              width: 252,
              boxShadow: "0 20px 40px -18px rgba(17,17,16,0.5)",
              animation: "fadeUp .25s ease",
            }}
          >
            <div style={{ fontSize: 12.5, lineHeight: 1.55 }}>{COACH_STEPS[coach]}</div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginTop: 12,
              }}
            >
              <span style={{ fontSize: 11, opacity: 0.55 }}>{coach + 1} of 3</span>
              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                {coach < 2 && (
                  <button
                    type="button"
                    onClick={finishCoach}
                    style={{
                      border: "none",
                      background: "none",
                      color: "#FFFFFF",
                      opacity: 0.6,
                      fontSize: 12,
                      padding: 0,
                    }}
                  >
                    Skip
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => (coach >= 2 ? finishCoach() : setCoach(coach + 1))}
                  style={{
                    border: "none",
                    borderRadius: 999,
                    background: "#FFFFFF",
                    color: "#111110",
                    fontSize: 12,
                    fontWeight: 600,
                    padding: "5px 14px",
                  }}
                >
                  {coach >= 2 ? "Got it" : "Next"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {logOpen && (
        <TranscriptDrawer
          sessionLabel={sessionLabel}
          log={state.log}
          onClose={() => setLogOpen(false)}
        />
      )}
    </div>
  );
}
