import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Scale, Users, Cpu, Code2, LifeBuoy, CheckCircle2, type LucideIcon } from "lucide-react";
import { useChatStream } from "../../custom_hooks/useChatStream";
const COLORS = {
  ink: "#0B0F17",
  panel: "#131A26",
  raised: "#1B2433",
  paper: "#E7E9EE",
  muted: "#7C8699",
  faint: "#4A5468",
  hairline: "#263047",
  signal: "#F2A93C",
};

type Agent = {
  id: string;
  name: string;
  color: string;
  icon: LucideIcon;
  desc: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent?: Agent;
  status?: "streaming" | "done";
  pendingReview?: boolean
};

const AGENTS: Agent[] = [
  { id: "legal_agent", name: "Legal", color: "#9B8CFF", icon: Scale, desc: "Contracts, policy, compliance" },
  { id: "hr_agent", name: "HR", color: "#FF8FA3", icon: Users, desc: "Benefits, leave, onboarding" },
  { id: "engineering_agent", name: "Engineering", color: "#58C4DC", icon: Cpu, desc: "Infra, architecture, incidents" },
  { id: "coding_agent", name: "Coding", color: "#8DD672", icon: Code2, desc: "Snippets, APIs, standards" },
  { id: "support_agent", name: "Support", color: "#F2A93C", icon: LifeBuoy, desc: "Tickets, how-tos, triage" },
];

const STAGES = [
  { id: "classify_domain", label: "Classifying" },
  { id: "check_authorization", label: "Permission check" },
  { id: "agent", label: "Routing" },
  { id: "retrieve", label: "Retrieving" },
  { id: "done", label: "Done" },
];


function mapNodeNameToStage(nodeName: string): string {
  const stageId: Record<string, string> = {
    "classify_domain": "classify_domain",
    "check_authorization": "check_authorization",
    "retrieve": "retrieve",
    "legal_agent": "agent",
    "hr_agent": "agent",
    "support_agent": "agent",
    "coding_agent": "agent",
    "engineering_agent": "agent"
  }



  return stageId[nodeName] ?? "";
}

function mapNodeNameToAgent(nodeName: string): Agent | null {

  return AGENTS.find((agent) => agent.id === nodeName) ?? null;
}

function fontStack() {
  return (
    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
      @keyframes blink { 0%, 49% { opacity: 1 } 50%, 100% { opacity: 0 } }
      @keyframes fadeUp { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: translateY(0) } }
      @keyframes pulseDot { 0% { box-shadow: 0 0 0 0 rgba(242,169,60,0.45) } 70% { box-shadow: 0 0 0 6px rgba(242,169,60,0) } 100% { box-shadow: 0 0 0 0 rgba(242,169,60,0) } }
      .sb-scroll::-webkit-scrollbar { width: 6px; }
      .sb-scroll::-webkit-scrollbar-thumb { background: #263047; border-radius: 3px; }
      .sb-msg { animation: fadeUp 0.28s ease-out; }
      .sb-input::placeholder { color: #4A5468; }
      .sb-input:focus { outline: none; }
    `}</style>
  );
}

export default function Dashboard() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [stage, setStage] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<Agent | null>(null);
  const [sources, setSources] = useState(0);
  const [isBusy, setIsBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const currentAssisstantIdRef = useRef<string | null>(null)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const { state, sendQuery } = useChatStream();

  // useEffect(() => {
  //   sendQuery("what is gdpr");
  // }, [sendQuery]);

  // useEffect(()=>{
  //   console.log(state.answerText);
  // },[state.answerText])


  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => () => timersRef.current.forEach(clearTimeout), []);

  useEffect(() => {
    if (state.currentStage) {
      setStage(mapNodeNameToStage(state.currentStage));
      const agent = mapNodeNameToAgent(state.currentStage);
      if (agent) setActiveAgent(agent)
    }

  },[state.currentStage])

  useEffect(() => {
    if (state.answerText && currentAssisstantIdRef.current) {
      setMessages((prev) => {
        return prev.map((m) => {
          return m.id === currentAssisstantIdRef.current ? { ...m, content: state.answerText, agent: activeAgent ?? undefined } : m
        })
      })
    }
  }, [state.answerText])

  useEffect(() => {
    if (!state.isStreaming && currentAssisstantIdRef.current) {
      setMessages((prev) => (
        prev.map((m) =>
          m.id === currentAssisstantIdRef.current ? { ...m, status: "done" } : m
        )
      ));
      setStage("done");
      setIsBusy(false)
      currentAssisstantIdRef.current = null
    }
  },[state.isStreaming])

  useEffect(() => {
    if (state.pausedReview && currentAssisstantIdRef.current) {
      setMessages((prev) => {
        return prev.map((m) => m.id === currentAssisstantIdRef.current ? { ...m, pendingReview: true } : m)
      })
    }
  }, [state.pausedReview])

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isBusy) return;

    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();
    currentAssisstantIdRef.current = assistantId
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: text },
      { id: assistantId, role: "assistant", content: "", status: "streaming" },
    ]);
    setInput("");
    setIsBusy(true);
    setActiveAgent(null);
    setSources(0);
    setStage(null);
    sendQuery(text)
    // --- Wiring note: replace this simulated sequence with the real
    // fetch()-based SSE reader (see useChatStream) hitting QUERY_STREAM,
    // and drive `stage` off actual astream_events from the orchestrator. ---
  }, [input, isBusy, sendQuery]);

  const stageIndex = STAGES.findIndex((s) => s.id === stage);

  return (
    <div
      style={{
        background: COLORS.ink,
        color: COLORS.paper,
        fontFamily: "'Inter', sans-serif",
        height: "100vh",
        display: "flex",
        overflow: "hidden",
      }}
    >
      {fontStack()}

      {/* LEFT RAIL */}
      <div
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
              SWITCHBOARD
            </div>
            <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: COLORS.muted, letterSpacing: 0.5 }}>
              MULTI-AGENT CONSOLE
            </div>
          </div>
        </div>

        <button
          disabled
          style={{
            background: COLORS.raised,
            border: `1px solid ${COLORS.hairline}`,
            color: COLORS.muted,
            fontFamily: "'Inter', sans-serif",
            fontSize: 13,
            fontWeight: 500,
            padding: "9px 12px",
            borderRadius: 8,
            marginBottom: 24,
            cursor: "not-allowed",
            textAlign: "left",
          }}
          title="Multiple sessions coming soon"
        >
          + New session
        </button>

        <div
          style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: 10,
            color: COLORS.faint,
            letterSpacing: 1,
            marginBottom: 12,
            paddingLeft: 4,
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
                  transition: "background 0.2s",
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
        {state.toolCalls.length > 0 && (
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: COLORS.faint, letterSpacing: 1 }}>
              TOOL CALLS
            </div>
            {state.toolCalls.map((tool, i) => (
              <div key={i} style={{ fontSize: 11, color: COLORS.signal, fontFamily: "'IBM Plex Mono', monospace" }}>
                🔧 {tool}
              </div>
            ))}
          </div>
        )}
        <div style={{ flex: 1 }} />

        <div
          style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: 10,
            color: COLORS.faint,
            letterSpacing: 0.4,
            paddingLeft: 4,
          }}
        >
          v0.1 · single session
        </div>
      </div>

      {/* CENTER — TRANSCRIPT */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
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

        <div ref={scrollRef} className="sb-scroll" style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
          {messages.length === 0 && (
            <div
              style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                textAlign: "center",
                color: COLORS.muted,
              }}
            >
              <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 17, color: COLORS.paper, marginBottom: 6 }}>
                No messages yet
              </div>
              <div style={{ fontSize: 13, maxWidth: 320, lineHeight: 1.5 }}>
                Ask something below. The supervisor routes it to a specialist and you'll see the path it takes on the right.
              </div>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 720, margin: "0 auto" }}>
            {messages.map((m) => (
              <div key={m.id} className="sb-msg" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {m.role === "user" ? (
                  <div style={{ alignSelf: "flex-end", maxWidth: "78%" }}>
                    <div
                      style={{
                        background: COLORS.raised,
                        border: `1px solid ${COLORS.hairline}`,
                        borderRadius: "12px 12px 3px 12px",
                        padding: "10px 14px",
                        fontSize: 14,
                        lineHeight: 1.5,
                      }}
                    >
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <div style={{ alignSelf: "flex-start", maxWidth: "82%" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                      <span style={{ width: 6, height: 6, borderRadius: 999, background: m.agent?.color }} />
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: m.agent?.color, letterSpacing: 0.4 }}>
                        {m.agent?.name.toUpperCase()}
                      </span>
                    </div>
                    <div
                      style={{
                        background: COLORS.panel,
                        border: `1px solid ${COLORS.hairline}`,
                        borderRadius: "3px 12px 12px 12px",
                        padding: "12px 14px",
                        fontSize: 14,
                        lineHeight: 1.6,
                      }}
                    >
                      {m.content}
                      {m.status === "streaming" && (
                        <span style={{ display: "inline-block", width: 7, height: 14, background: COLORS.signal, marginLeft: 2, verticalAlign: "middle", animation: "blink 1s step-start infinite" }} />
                      )}
                    </div>
                    {m.pendingReview && (
                      <div style={{ marginTop: 8, padding: "6px 10px", background: `${COLORS.signal}17`, border: `1px solid ${COLORS.signal}40`, borderRadius: 8, fontSize: 11, color: COLORS.signal, fontFamily: "'IBM Plex Mono', monospace" }}>
                        ⏳ Pending admin review before this answer is finalized
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div style={{ padding: "16px 28px 22px", borderTop: `1px solid ${COLORS.hairline}` }}>
          <div
            style={{
              maxWidth: 720,
              margin: "0 auto",
              display: "flex",
              alignItems: "flex-end",
              gap: 8,
              background: COLORS.raised,
              border: `1px solid ${COLORS.hairline}`,
              borderRadius: 12,
              padding: "8px 8px 8px 16px",
            }}
          >
            <textarea
              className="sb-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask Legal, HR, Engineering, Coding, or Support…"
              rows={1}
              style={{
                flex: 1,
                background: "transparent",
                border: "none",
                resize: "none",
                color: COLORS.paper,
                fontSize: 14,
                fontFamily: "'Inter', sans-serif",
                padding: "8px 0",
                maxHeight: 120,
              }}
            />
            <button
              onClick={handleSend}
              disabled={isBusy || !input.trim()}
              style={{
                background: isBusy || !input.trim() ? COLORS.hairline : COLORS.signal,
                border: "none",
                borderRadius: 9,
                width: 36,
                height: 36,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: isBusy || !input.trim() ? "not-allowed" : "pointer",
                flexShrink: 0,
              }}
            >
              <Send size={15} color={isBusy || !input.trim() ? COLORS.muted : COLORS.ink} />
            </button>
          </div>
        </div>
      </div>

      {/* RIGHT RAIL — ROUTING (SIGNATURE ELEMENT) */}
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
    </div>
  );
}