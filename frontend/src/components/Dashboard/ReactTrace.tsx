import { useState } from "react";
import { CheckCircle2, ChevronDown, XCircle } from "lucide-react";
import { COLORS } from "./constants";
import type { ReactStep } from "../../custom_hooks/useChatStream";

type ReactTraceProps = {
  steps: ReactStep[];
  isStreaming: boolean;
  agentColor?: string;
};

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args).map(([key, value]) => `${key}: ${JSON.stringify(value)}`);
  const joined = entries.join(", ");
  return joined.length > 90 ? `${joined.slice(0, 90)}…` : joined;
}

function isErrorObservation(observation: string | null): boolean {
  return !!observation && observation.trim().toUpperCase().startsWith("ERROR");
}

export default function ReactTrace({ steps, isStreaming, agentColor }: ReactTraceProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (steps.length === 0) return null;

  const accent = agentColor ?? COLORS.signal;
  const running = isStreaming && steps.some((s) => s.observation === null);
  const doneCount = steps.filter((s) => s.observation !== null).length;

  return (
    <div
      className="sb-msg"
      style={{
        background: COLORS.panel,
        border: `1px solid ${COLORS.hairline}`,
        borderRadius: 10,
        padding: "10px 12px",
        marginBottom: 4,
      }}
    >
      <button
        onClick={() => setCollapsed((c) => !c)}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          width: "100%",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: 0,
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 10,
          color: COLORS.faint,
          letterSpacing: 1.1,
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: 999,
              background: running ? accent : COLORS.muted,
              animation: running ? "pulseDot 1.4s infinite" : "none",
              flexShrink: 0,
            }}
          />
          {running ? "THINKING" : "AGENT STEPS"}
          <span style={{ color: COLORS.faint }}>
            {doneCount}/{steps.length}
          </span>
        </span>
        <ChevronDown
          size={13}
          color={COLORS.faint}
          style={{ transform: collapsed ? "rotate(-90deg)" : "none", transition: "transform 0.15s ease" }}
        />
      </button>

      {!collapsed && (
        <div style={{ display: "flex", flexDirection: "column", marginTop: 10 }}>
          {steps.map((step, i) => {
            const isRunning = step.observation === null;
            const isError = isErrorObservation(step.observation);
            const dotColor = isRunning ? accent : isError ? COLORS.error : accent;

            return (
              <div key={step.call_id} style={{ display: "flex", gap: 10 }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <div
                    style={{
                      width: 16,
                      height: 16,
                      borderRadius: 999,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      background: isRunning ? "transparent" : dotColor,
                      border: `1.5px solid ${dotColor}`,
                      animation: isRunning ? "pulseDot 1.4s infinite" : "none",
                      flexShrink: 0,
                      marginTop: 2,
                    }}
                  >
                    {!isRunning && !isError && <CheckCircle2 size={10} color={COLORS.ink} strokeWidth={3} />}
                    {!isRunning && isError && <XCircle size={10} color={COLORS.ink} strokeWidth={3} />}
                  </div>
                  {i < steps.length - 1 && (
                    <div style={{ width: 1.5, flex: 1, minHeight: 18, background: isRunning ? COLORS.hairline : dotColor }} />
                  )}
                </div>

                <div style={{ paddingBottom: 14, minWidth: 0, flex: 1 }}>
                  {step.thought && (
                    <div
                      style={{
                        fontFamily: "'Inter', sans-serif",
                        fontSize: 11.5,
                        fontStyle: "italic",
                        color: COLORS.muted,
                        marginBottom: 3,
                        overflowWrap: "anywhere",
                      }}
                    >
                      {step.thought}
                    </div>
                  )}

                  <div
                    style={{
                      fontFamily: "'IBM Plex Mono', monospace",
                      fontSize: 12,
                      color: COLORS.paper,
                      overflowWrap: "anywhere",
                    }}
                  >
                    <span style={{ color: accent, fontWeight: 500 }}>{step.action.tool}</span>
                    <span style={{ color: COLORS.faint }}>({formatArgs(step.action.args)})</span>
                  </div>

                  {isRunning ? (
                    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: accent, marginTop: 4 }}>
                      {isStreaming ? "running…" : "no result"}
                    </div>
                  ) : (
                    <div
                      style={{
                        marginTop: 5,
                        padding: "5px 8px",
                        borderRadius: 6,
                        background: isError ? `${COLORS.error}17` : COLORS.raised,
                        border: `1px solid ${isError ? `${COLORS.error}40` : COLORS.hairline}`,
                        fontFamily: "'IBM Plex Mono', monospace",
                        fontSize: 11,
                        color: isError ? COLORS.error : COLORS.muted,
                        overflowWrap: "anywhere",
                      }}
                    >
                      {step.observation}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
