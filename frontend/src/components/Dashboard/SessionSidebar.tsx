import { useState } from "react";
import { Plus, MessageSquare, ShieldCheck, UploadCloud, X, Info } from "lucide-react";
import { COLORS, AGENTS } from "./constants";
import type { Agent, SessionSummary } from "./types";

type SessionSidebarProps = {
  sessions: SessionSummary[];
  sessionsLoading: boolean;
  activeSessionId?: string;
  creatingSession: boolean;
  activeAgent: Agent | null;
  toolCalls: string[];
  onCreateSession: () => void;
  onSelectSession: (sessionId: string) => void;
  isAdmin?: boolean;
  onNavigateAdminReview?: () => void;
  onNavigateIngestion?: () => void;
  className?: string;
  onClose?: () => void;
};

export default function SessionSidebar({
  sessions,
  sessionsLoading,
  activeSessionId,
  creatingSession,
  activeAgent,
  toolCalls,
  onCreateSession,
  onSelectSession,
  isAdmin,
  onNavigateAdminReview,
  onNavigateIngestion,
  className,
  onClose,
}: SessionSidebarProps) {
  const [aboutOpen, setAboutOpen] = useState(false);
  return (
    <div
      className={className}
      style={{
        width: 248,
        flexShrink: 0,
        borderRight: `1px solid ${COLORS.hairline}`,
        display: "flex",
        flexDirection: "column",
        padding: "20px 16px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28, paddingLeft: 4 }}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: COLORS.signal,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <div style={{ width: 10, height: 10, background: COLORS.ink, borderRadius: 2 }} />
        </div>
        <div>
          <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 15, letterSpacing: 0.3 }}>
            MULTI-AGENT-SYSTEM
          </div>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: COLORS.muted, letterSpacing: 0.5 }}>
            MULTI-AGENT CONSOLE
          </div>
        </div>
        {onClose && (
          <button
            className="sb-mobile-toggle sb-panel-close"
            onClick={onClose}
            aria-label="Close sessions"
            style={{ marginLeft: "auto", background: "transparent", border: "none", cursor: "pointer" }}
          >
            <X size={18} color={COLORS.muted} />
          </button>
        )}
      </div>

      <button
        onClick={onCreateSession}
        disabled={creatingSession}
        style={{
          background: COLORS.raised,
          border: `1px solid ${COLORS.hairline}`,
          color: COLORS.paper,
          fontFamily: "'Inter', sans-serif",
          fontSize: 13,
          fontWeight: 500,
          padding: "9px 12px",
          borderRadius: 8,
          marginBottom: 20,
          textAlign: "left",
          cursor: creatingSession ? "not-allowed" : "pointer",
          display: "flex",
          alignItems: "center",
          gap: 8,
          opacity: creatingSession ? 0.6 : 1,
        }}
      >
        <Plus size={14} color={COLORS.signal} />
        {creatingSession ? "Creating…" : "New session"}
      </button>

      <div
        style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 10,
          color: COLORS.faint,
          letterSpacing: 1,
          marginBottom: 10,
          paddingLeft: 4,
        }}
      >
        SESSIONS
      </div>

      <div className="sb-scroll" style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, overflowY: "auto", minHeight: 0, marginBottom: 16 }}>
        {sessionsLoading && (
          <div style={{ fontSize: 12, color: COLORS.muted, padding: "8px 8px" }}>Loading…</div>
        )}
        {!sessionsLoading && sessions.length === 0 && (
          <div style={{ fontSize: 12, color: COLORS.muted, padding: "8px 8px", lineHeight: 1.4 }}>
            No sessions yet. Start a new one to begin chatting.
          </div>
        )}
        {sessions.map((s) => {
          const isActive = s.id === activeSessionId;
          return (
            <button
              key={s.id}
              onClick={() => onSelectSession(s.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 8px",
                borderRadius: 8,
                border: "none",
                background: isActive ? COLORS.raised : "transparent",
                color: isActive ? COLORS.paper : COLORS.muted,
                fontFamily: "'Inter', sans-serif",
                fontSize: 12.5,
                textAlign: "left",
                cursor: "pointer",
                width: "100%",
              }}
            >
              <MessageSquare size={13} color={isActive ? COLORS.signal : COLORS.faint} style={{ flexShrink: 0 }} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</span>
            </button>
          );
        })}
      </div>

      <button
        onClick={() => setAboutOpen(true)}
        style={{
          background: "transparent",
          border: `1px solid ${COLORS.hairline}`,
          color: COLORS.muted,
          fontFamily: "'Inter', sans-serif",
          fontSize: 12.5,
          fontWeight: 500,
          padding: "8px 10px",
          borderRadius: 8,
          textAlign: "left",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexShrink: 0,
        }}
      >
        <Info size={13} color={COLORS.signal} />
        About specialists
        {activeAgent && (
          <span style={{ marginLeft: "auto", width: 6, height: 6, borderRadius: 999, background: activeAgent.color, flexShrink: 0 }} />
        )}
      </button>
      {toolCalls.length > 0 && (
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: COLORS.faint, letterSpacing: 1 }}>
            TOOL CALLS
          </div>
          {toolCalls.map((tool, i) => (
            <div key={i} style={{ fontSize: 11, color: COLORS.signal, fontFamily: "'IBM Plex Mono', monospace" }}>
              🔧 {tool}
            </div>
          ))}
        </div>
      )}

      {isAdmin && (
        <div style={{ marginTop: 16 }}>
          <div
            style={{
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: 10,
              color: COLORS.faint,
              letterSpacing: 1,
              marginBottom: 8,
              paddingLeft: 4,
            }}
          >
            ADMIN
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <button
              onClick={onNavigateAdminReview}
              style={{
                background: COLORS.raised,
                border: `1px solid ${COLORS.hairline}`,
                color: COLORS.paper,
                fontFamily: "'Inter', sans-serif",
                fontSize: 12.5,
                fontWeight: 500,
                padding: "8px 10px",
                borderRadius: 8,
                textAlign: "left",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <ShieldCheck size={13} color={COLORS.signal} />
              Admin review
            </button>
            <button
              onClick={onNavigateIngestion}
              style={{
                background: COLORS.raised,
                border: `1px solid ${COLORS.hairline}`,
                color: COLORS.paper,
                fontFamily: "'Inter', sans-serif",
                fontSize: 12.5,
                fontWeight: 500,
                padding: "8px 10px",
                borderRadius: 8,
                textAlign: "left",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <UploadCloud size={13} color={COLORS.signal} />
              Ingestion
            </button>
          </div>
        </div>
      )}

      <div
        style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 10,
          color: COLORS.faint,
          letterSpacing: 0.4,
          paddingLeft: 4,
          marginTop: 16,
        }}
      >
        v0.1 · {sessions.length} session{sessions.length === 1 ? "" : "s"}
      </div>

      {aboutOpen && (
        <div
          onClick={() => setAboutOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.55)",
            zIndex: 200,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "100%",
              maxWidth: 380,
              maxHeight: "80vh",
              overflowY: "auto",
              background: COLORS.panel,
              border: `1px solid ${COLORS.hairline}`,
              borderRadius: 12,
              padding: 20,
              boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
              <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 15 }}>
                About
              </div>
              <button
                onClick={() => setAboutOpen(false)}
                aria-label="Close about"
                style={{ background: "transparent", border: "none", cursor: "pointer", padding: 4 }}
              >
                <X size={18} color={COLORS.muted} />
              </button>
            </div>
            <div
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: 10,
                color: COLORS.faint,
                letterSpacing: 1,
                margin: "16px 0 10px",
              }}
            >
              SPECIALISTS
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {AGENTS.map((a) => {
                const Icon = a.icon;
                const isActive = activeAgent?.id === a.id;
                return (
                  <div
                    key={a.id}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 10,
                      padding: "9px 8px",
                      borderRadius: 8,
                      background: isActive ? COLORS.raised : "transparent",
                    }}
                  >
                    <div
                      style={{
                        width: 26,
                        height: 26,
                        borderRadius: 6,
                        background: `${a.color}1F`,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                        marginTop: 1,
                      }}
                    >
                      <Icon size={13} color={a.color} strokeWidth={2} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: COLORS.paper }}>{a.name}</div>
                      <div style={{ fontSize: 11, color: COLORS.muted, lineHeight: 1.3 }}>{a.desc}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
