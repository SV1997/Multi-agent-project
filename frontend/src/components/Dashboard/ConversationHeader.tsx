import { COLORS } from "./constants";
import type { Agent, Message } from "./types";

type ConversationHeaderProps = {
  messages: Message[];
  activeAgent: Agent | null;
};

export default function ConversationHeader({ messages, activeAgent }: ConversationHeaderProps) {
  return (
    <div
      style={{
        padding: "16px 28px",
        borderBottom: `1px solid ${COLORS.hairline}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}
    >
      <div>
        <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 14 }}>
          Session
        </div>
        <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: COLORS.muted }}>
          {messages.length === 0 ? "not started" : `${messages.filter((m) => m.role === "user").length} queries asked`}
        </div>
      </div>
      {activeAgent && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "5px 10px",
            borderRadius: 999,
            background: `${activeAgent.color}17`,
            border: `1px solid ${activeAgent.color}40`,
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: 999, background: activeAgent.color }} />
          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: activeAgent.color }}>
            {activeAgent.name}
          </span>
        </div>
      )}
    </div>
  );
}
