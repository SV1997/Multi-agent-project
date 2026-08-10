import { CheckCircle2 } from "lucide-react";
import { COLORS, STAGES } from "./constants";
import type { Agent } from "./types";

type RoutingRailProps = {
  stageIndex: number;
  isBusy: boolean;
  activeAgent: Agent | null;
  sources: number;
};

export default function RoutingRail({ stageIndex, isBusy, activeAgent, sources }: RoutingRailProps) {
  return (
    <div
      style={{
        width: 280,
        flexShrink: 0,
        borderLeft: `1px solid ${COLORS.hairline}`,
        padding: "20px 18px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 10,
          color: COLORS.faint,
          letterSpacing: 1.2,
          marginBottom: 16,
        }}
      >
        ROUTING
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {STAGES.map((s, i) => {
          const isCurrent = stageIndex === i && isBusy;
          const isPast = stageIndex >= i;
          return (
            <div key={s.id} style={{ display: "flex", gap: 10, position: "relative" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <div
                  style={{
                    width: 16,
                    height: 16,
                    borderRadius: 999,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: isPast ? (activeAgent ? `${activeAgent.color}` : COLORS.signal) : "transparent",
                    border: `1.5px solid ${isPast ? (activeAgent ? activeAgent.color : COLORS.signal) : COLORS.hairline}`,
                    animation: isCurrent ? "pulseDot 1.4s infinite" : "none",
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                >
                  {isPast && !isCurrent && <CheckCircle2 size={10} color={COLORS.ink} strokeWidth={3} />}
                </div>
                {i < STAGES.length - 1 && (
                  <div style={{ width: 1.5, flex: 1, minHeight: 22, background: isPast && stageIndex > i ? (activeAgent ? activeAgent.color : COLORS.signal) : COLORS.hairline }} />
                )}
              </div>
              <div style={{ paddingBottom: 20 }}>
                <div
                  style={{
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: 12,
                    color: isPast ? COLORS.paper : COLORS.faint,
                    fontWeight: isCurrent ? 500 : 400,
                  }}
                >
                  {s.label}
                </div>
                {s.id === "routed" && isPast && activeAgent && (
                  <div style={{ fontSize: 11, color: activeAgent.color, marginTop: 2, fontFamily: "'IBM Plex Mono', monospace" }}>
                    → {activeAgent.name} agent
                  </div>
                )}
                {s.id === "retrieving" && isPast && sources > 0 && (
                  <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 2, fontFamily: "'IBM Plex Mono', monospace" }}>
                    {sources} passages · Pinecone
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ flex: 1 }} />

      <div
        style={{
          borderTop: `1px solid ${COLORS.hairline}`,
          paddingTop: 14,
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 10.5,
          color: COLORS.faint,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>supervisor</span>
        <span style={{ color: isBusy ? COLORS.signal : COLORS.muted }}>{isBusy ? "active" : "idle"}</span>
      </div>
    </div>
  );
}
