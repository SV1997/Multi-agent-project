import { Plus } from "lucide-react";
import { COLORS } from "./constants";

type EmptySessionStateProps = {
  hasSessions: boolean;
  creatingSession: boolean;
  onCreateSession: () => void;
};

export default function EmptySessionState({ hasSessions, creatingSession, onCreateSession }: EmptySessionStateProps) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: 24,
      }}
    >
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: 12,
          background: `${COLORS.signal}17`,
          border: `1px solid ${COLORS.signal}40`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: 18,
        }}
      >
        <Plus size={22} color={COLORS.signal} />
      </div>
      <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 20, color: COLORS.paper, marginBottom: 8 }}>
        Start a new session
      </div>
      <div style={{ fontSize: 13.5, color: COLORS.muted, maxWidth: 340, lineHeight: 1.6, marginBottom: 24 }}>
        {hasSessions
          ? "Pick a previous session from the sidebar, or start a fresh one to ask the supervisor a new question."
          : "Create a session to start chatting with Legal, HR, Engineering, Coding, or Support."}
      </div>
      <button
        onClick={onCreateSession}
        disabled={creatingSession}
        style={{
          background: COLORS.signal,
          border: "none",
          color: COLORS.ink,
          fontFamily: "'Inter', sans-serif",
          fontSize: 14,
          fontWeight: 600,
          padding: "10px 20px",
          borderRadius: 9,
          cursor: creatingSession ? "not-allowed" : "pointer",
          opacity: creatingSession ? 0.7 : 1,
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <Plus size={16} />
        {creatingSession ? "Creating…" : "New session"}
      </button>
    </div>
  );
}
