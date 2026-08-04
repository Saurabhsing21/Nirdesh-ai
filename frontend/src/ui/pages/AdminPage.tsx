// STATIC DEMO PAGE — pixel-faithful to the design with hardcoded data.
// No backend calls; agreed to ship as a visual demo only.
import { useState } from "react";

type ServiceTile = {
  name: string;
  status: "ok" | "warn" | "down";
  uptime: string;
  checked: string;
  seed: number;
};

const TILES: ServiceTile[] = [
  { name: "Sarvam STT", status: "ok", uptime: "99.98%", checked: "12 s ago", seed: 1 },
  { name: "Sarvam LLM", status: "ok", uptime: "99.95%", checked: "8 s ago", seed: 2 },
  { name: "Sarvam TTS", status: "ok", uptime: "99.91%", checked: "12 s ago", seed: 3 },
  { name: "Exa search", status: "ok", uptime: "99.24%", checked: "31 s ago", seed: 4 },
  { name: "Resend email", status: "ok", uptime: "100%", checked: "2 m ago", seed: 5 },
];

const LATENCY_ROWS = [
  { name: "Endpoint detection", target: 700, p50: 640, p95: 710, approx: true },
  { name: "STT finalize", target: 300, p50: 180, p95: 290, approx: false },
  { name: "LLM first sentence", target: 800, p50: 520, p95: 880, approx: false },
  { name: "TTS first chunk", target: 300, p50: 210, p95: 280, approx: false },
  { name: "End-to-end", target: 1500, p50: 1160, p95: 1490, approx: false },
];

const OPS = [
  { value: "42", label: "Active sessions", sub: "live now" },
  { value: "58", label: "WebSocket connections", sub: "of 1,000 max" },
  { value: "0.4%", label: "Error rate", sub: "last 15 min" },
  { value: "3.2/min", label: "Barge-in events", sub: "interruptions" },
  { value: "61%", label: "Silence dropped by VAD", sub: "bandwidth saved" },
];

const ERRORS = [
  {
    id: 1,
    t: "09:32:11",
    svc: "tts",
    msg: "TTS websocket closed mid-stream (1006)",
    detail:
      "session=s_1051 · speaker=anushka · lang=hi-IN\nBulbulClient.stream() -> ConnectionClosedError(1006)\nretried=1 · recovered=yes · audio gap=180ms",
  },
  {
    id: 2,
    t: "08:57:40",
    svc: "exa",
    msg: "web_search timed out after 4000 ms",
    detail:
      'session=s_1049 · query="ipl final score"\nExaClient.search() -> TimeoutError(4000ms)\nagent continued without tool result',
  },
  {
    id: 3,
    t: "07:14:03",
    svc: "stt",
    msg: "Flush returned empty transcript",
    detail:
      "session=s_1046 · lang=auto\nSarvamSTT.flush() -> empty payload after 2 retries\nturn discarded · user re-prompted",
  },
  {
    id: 4,
    t: "Jul 11 23:02",
    svc: "billing",
    msg: "Ledger write retried (SQLITE_BUSY)",
    detail: "session=s_1041 · debit=-3 paise\nretry 2 of 3 succeeded · no data loss",
  },
];

const ALERTS = [
  {
    id: 1,
    t: "09:32 IST",
    sev: "warn" as const,
    msg: "TTS p95 first-chunk latency 480 ms above the 300 ms budget",
    resolved: false,
  },
  {
    id: 2,
    t: "06:10 IST",
    sev: "crit" as const,
    msg: "Exa search error rate hit 12% over 5 min",
    resolved: true,
  },
  {
    id: 3,
    t: "Jul 11, 22:47",
    sev: "warn" as const,
    msg: "WebSocket connections neared limit (950/1000)",
    resolved: true,
  },
];

function sparkFor(seed: number): string {
  const points: string[] = [];
  for (let j = 0; j < 16; j++) {
    const v = 6 + Math.sin(seed * 7 + j * 0.9) * 2 + Math.sin(j * 0.45 + seed) * 1.6;
    const y = Math.min(Math.max(17 - v, 2), 18);
    points.push(`${((j * 80) / 15).toFixed(1)},${y.toFixed(1)}`);
  }
  return points.join(" ");
}

export function AdminPage() {
  const [range, setRange] = useState("24h");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [alerts, setAlerts] = useState(ALERTS);

  const seg = (value: string, label: string) => (
    <button
      key={value}
      type="button"
      onClick={() => setRange(value)}
      style={{
        border: "none",
        borderRadius: 999,
        padding: "6px 14px",
        fontSize: 12.5,
        fontWeight: 500,
        background: range === value ? "#FFFFFF" : "transparent",
        color: range === value ? "#111110" : "#6B6B66",
      }}
    >
      {label}
    </button>
  );

  const SCALE = 2000;

  return (
    <div style={{ padding: 40, maxWidth: 1120, margin: "0 auto", boxSizing: "border-box" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500, letterSpacing: "-0.02em" }}>
            Operations
          </h1>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11.5,
              fontWeight: 500,
              color: "#1F7A46",
              background: "#E8F3EC",
              borderRadius: 999,
              padding: "4px 11px",
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "#22A45D",
                animation: "blinkDot 1.4s infinite",
              }}
            />
            static demo · sample data
          </span>
        </div>
        <div
          style={{
            display: "inline-flex",
            background: "#EFEFEB",
            borderRadius: 999,
            padding: 3,
            gap: 2,
          }}
        >
          {seg("1h", "1 h")}
          {seg("24h", "24 h")}
          {seg("7d", "7 d")}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginTop: 22 }}>
        {TILES.map((tile) => (
          <div
            key={tile.name}
            style={{
              background: "#FFFFFF",
              border: "1px solid #E5E5E1",
              borderRadius: 14,
              padding: 16,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "#22A45D",
                  flexShrink: 0,
                }}
              />
              <span style={{ fontSize: 12.5, fontWeight: 600, whiteSpace: "nowrap" }}>
                {tile.name}
              </span>
            </div>
            <div style={{ fontSize: 12, fontWeight: 500, marginTop: 8, color: "#1F7A46" }}>
              Operational
            </div>
            <div
              style={{
                fontSize: 19,
                fontWeight: 500,
                marginTop: 8,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {tile.uptime}
              <span style={{ fontSize: 11, color: "#A6A6A0", fontWeight: 400 }}> uptime</span>
            </div>
            <div style={{ fontSize: 11, color: "#A6A6A0", marginTop: 4 }}>
              checked {tile.checked}
            </div>
            <svg
              viewBox="0 0 80 20"
              preserveAspectRatio="none"
              style={{ width: "100%", height: 20, marginTop: 10, display: "block" }}
            >
              <polyline
                points={sparkFor(tile.seed)}
                fill="none"
                stroke="#4A6CF7"
                strokeWidth="1.5"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </svg>
          </div>
        ))}
      </div>

      <div
        style={{
          background: "#FFFFFF",
          border: "1px solid #E5E5E1",
          borderRadius: 14,
          marginTop: 14,
          padding: "22px 24px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div style={{ fontSize: 13.5, fontWeight: 600 }}>Latency budget</div>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 11, color: "#6B6B66" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 10, height: 6, background: "#111110", borderRadius: 2 }} />
              p50
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 10, height: 6, background: "#4A6CF7", borderRadius: 2 }} />
              p95
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 2, height: 10, background: "#111110" }} />
              target
            </span>
            <span>end of speech → first audio ≤ 1.5 s</span>
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          {LATENCY_ROWS.map((row) => {
            const over = row.p95 > row.target;
            return (
              <div
                key={row.name}
                style={{
                  display: "grid",
                  gridTemplateColumns: "170px 1fr 230px",
                  gap: 16,
                  alignItems: "center",
                  padding: "11px 0",
                  borderBottom: "1px solid #F4F4F0",
                }}
              >
                <div style={{ fontSize: 13 }}>{row.name}</div>
                <div style={{ position: "relative", height: 26, background: "#F7F7F5", borderRadius: 6 }}>
                  <div
                    style={{
                      position: "absolute",
                      left: 0,
                      top: 4,
                      height: 8,
                      width: `${((row.p50 / SCALE) * 100).toFixed(1)}%`,
                      background: "#111110",
                      borderRadius: "0 4px 4px 0",
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      left: 0,
                      bottom: 4,
                      height: 8,
                      width: `${(Math.min(row.p95 / SCALE, 1) * 100).toFixed(1)}%`,
                      background: over ? "#D97706" : "#4A6CF7",
                      borderRadius: "0 4px 4px 0",
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      top: -2,
                      bottom: -2,
                      left: `${((row.target / SCALE) * 100).toFixed(1)}%`,
                      width: 2,
                      background: "#111110",
                    }}
                  />
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "#6B6B66",
                    fontVariantNumeric: "tabular-nums",
                    whiteSpace: "nowrap",
                  }}
                >
                  p50 {row.p50} ms · p95{" "}
                  <span style={{ fontWeight: 600, color: over ? "#9A6A0B" : "#111110" }}>
                    {row.p95} ms
                  </span>{" "}
                  · target {row.approx ? "~" : "≤"}
                  {row.target} ms
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginTop: 14 }}>
        {OPS.map((op) => (
          <div
            key={op.label}
            style={{
              background: "#FFFFFF",
              border: "1px solid #E5E5E1",
              borderRadius: 14,
              padding: 16,
            }}
          >
            <div
              style={{
                fontSize: 22,
                fontWeight: 500,
                fontVariantNumeric: "tabular-nums",
                letterSpacing: "-0.02em",
              }}
            >
              {op.value}
            </div>
            <div style={{ fontSize: 12, color: "#6B6B66", marginTop: 5 }}>{op.label}</div>
            <div style={{ fontSize: 11, color: "#A6A6A0", marginTop: 2 }}>{op.sub}</div>
          </div>
        ))}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.25fr 1fr",
          gap: 14,
          marginTop: 14,
          alignItems: "start",
        }}
      >
        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #E5E5E1",
            borderRadius: 14,
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "18px 20px 10px", fontSize: 13.5, fontWeight: 600 }}>
            Recent errors
          </div>
          {ERRORS.map((error) => (
            <div key={error.id} style={{ borderBottom: "1px solid #F4F4F0" }}>
              <div
                onClick={() => setExpanded(expanded === error.id ? null : error.id)}
                className="hovRow"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "11px 20px",
                  cursor: "pointer",
                }}
              >
                <span
                  style={{
                    fontSize: 11.5,
                    fontFamily: "ui-monospace,'SF Mono',monospace",
                    color: "#A6A6A0",
                    whiteSpace: "nowrap",
                  }}
                >
                  {error.t}
                </span>
                <span
                  style={{
                    fontSize: 10.5,
                    fontFamily: "ui-monospace,'SF Mono',monospace",
                    border: "1px solid #E5E5E1",
                    background: "#F7F7F5",
                    borderRadius: 5,
                    padding: "2px 7px",
                    color: "#6B6B66",
                  }}
                >
                  {error.svc}
                </span>
                <span
                  style={{
                    flex: 1,
                    fontSize: 12.5,
                    minWidth: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {error.msg}
                </span>
                <span style={{ fontSize: 10, color: "#A6A6A0" }}>
                  {expanded === error.id ? "▾" : "▸"}
                </span>
              </div>
              {expanded === error.id && (
                <pre
                  style={{
                    margin: "0 20px 14px",
                    padding: "12px 14px",
                    background: "#F7F7F5",
                    borderRadius: 8,
                    fontFamily: "ui-monospace,'SF Mono',monospace",
                    fontSize: 11.5,
                    lineHeight: 1.6,
                    color: "#4A4A46",
                    whiteSpace: "pre-wrap",
                    overflowX: "auto",
                  }}
                >
                  {error.detail}
                </pre>
              )}
            </div>
          ))}
        </div>

        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #E5E5E1",
            borderRadius: 14,
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "18px 20px 10px", fontSize: 13.5, fontWeight: 600 }}>Alerts</div>
          {alerts.map((alert) => (
            <div
              key={alert.id}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                padding: "12px 20px",
                borderBottom: "1px solid #F4F4F0",
              }}
            >
              <span
                style={{
                  fontSize: 10.5,
                  fontWeight: 600,
                  letterSpacing: "0.04em",
                  borderRadius: 5,
                  padding: "2.5px 7px",
                  background: alert.sev === "warn" ? "#FCF3E0" : "#FBEAEA",
                  color: alert.sev === "warn" ? "#9A6A0B" : "#B3352E",
                  flexShrink: 0,
                  marginTop: 1,
                }}
              >
                {alert.sev === "warn" ? "WARN" : "CRIT"}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>{alert.msg}</div>
                <div
                  style={{
                    fontSize: 11,
                    fontFamily: "ui-monospace,'SF Mono',monospace",
                    color: "#A6A6A0",
                    marginTop: 3,
                  }}
                >
                  {alert.t}
                </div>
              </div>
              <button
                type="button"
                onClick={() =>
                  setAlerts(
                    alerts.map((item) =>
                      item.id === alert.id ? { ...item, resolved: !item.resolved } : item,
                    ),
                  )
                }
                style={{
                  border: `1px solid ${alert.resolved ? "#E5E5E1" : "#F0C4C0"}`,
                  background: alert.resolved ? "#F1F1ED" : "#FFFFFF",
                  color: alert.resolved ? "#8A8A85" : "#B3352E",
                  borderRadius: 999,
                  padding: "3px 10px",
                  fontSize: 11,
                  fontWeight: 500,
                  flexShrink: 0,
                }}
              >
                {alert.resolved ? "Resolved" : "Open"}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
