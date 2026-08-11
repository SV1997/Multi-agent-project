import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { jwtDecode } from "jwt-decode";
import { Menu, Radio } from "lucide-react";
import { useChatStream } from "../../custom_hooks/useChatStream";
import { fetchRequestGet, fetchRequestPost } from "../../common/NetworkOps";
import ApiObj from "../../common/ApiObj";
import { COLORS, STAGES } from "./constants";
import { mapNodeNameToStage, mapNodeNameToAgent } from "./helpers";
import type { Agent, Message, PendingReview, SessionSummary } from "./types";
import GlobalStyles from "./GlobalStyles";
import SessionSidebar from "./SessionSidebar";
import EmptySessionState from "./EmptySessionState";
import ConversationHeader from "./ConversationHeader";
import MessageList from "./MessageList";
import ChatComposer from "./ChatComposer";
import RoutingRail from "./RoutingRail";

export default function Dashboard() {
  const navigate = useNavigate();
  const { sessionId: activeSessionId } = useParams<{ sessionId?: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [stage, setStage] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<Agent | null>(null);
  const [sources, setSources] = useState(0);
  const [isBusy, setIsBusy] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [creatingSession, setCreatingSession] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [, setPendingReviews] = useState<PendingReview[]>([]);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const loadedSessionIdRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const currentAssisstantIdRef = useRef<string | null>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const reviewSourcesRef = useRef<EventSource[]>([]);

  const { state, sendQuery } = useChatStream();

  const isAdmin = useMemo(() => {
    const token = localStorage.getItem("accessToken");
    if (!token) return false;
    try {
      return jwtDecode<{ role: string }>(token).role === "admin";
    } catch {
      return false;
    }
  }, []);

  const handleNavigateAdminReview = useCallback(() => navigate("/adminReview"), [navigate]);
  const handleNavigateIngestion = useCallback(() => navigate("/ingestion"), [navigate]);

  const fetchSessions = useCallback(async () => {
    try {
      setSessionsLoading(true);
      const res: any = await fetchRequestGet(ApiObj.session.SESSION_LIST);
      setSessions(res ?? []);
    } catch (err) {
      console.error("Failed to load sessions", err);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const resetConversationState = () => {
    setMessages([]);
    setStage(null);
    setActiveAgent(null);
    setSources(0);
    setIsBusy(false);
    reviewSourcesRef.current.forEach((es) => es.close());
    reviewSourcesRef.current = [];
  };
  const subscribeToReview = (threadId: string, turnId: string) => {
    const accessToken = localStorage.getItem("accessToken")
    const es = new EventSource(
        `${ApiObj.baseUrl}${ApiObj.query.QUERY_NOTIFICATIONS(threadId)}?token=${accessToken}`,
        { withCredentials: true }
    )
    reviewSourcesRef.current.push(es)
    es.onmessage = (event) => {
        const parsed = JSON.parse(event.data)
        if (parsed.status === 'resolved') {
            setMessages(prev => prev.map(m =>
                m.turnId === turnId ? { ...m, content: parsed.result.answer, pendingReview: false, status: 'done' } : m
            ))
            es.close()
        }
    }
    es.onerror = () => es.close()
    return es  // return it so caller can close on unmount
}
  const fetchPendingReview = useCallback(async (sessionId: string) => {
    const reviews: any = await fetchRequestPost(ApiObj.query.QUERY_MY_PENDING_REVIEWS, { sessionId });
    const list: PendingReview[] = reviews ?? [];
    list.filter((review) => !review.resolved).forEach((review) => {
      subscribeToReview(review.threadId, review.turnId)
    })
    setPendingReviews(list);
    return list;
  }, []);

  const handleCreateSession = useCallback(async () => {
    if (creatingSession) return;
    try {
      setCreatingSession(true);
      const res: any = await fetchRequestPost(ApiObj.session.SESSION_CREATE);
      const newSession: SessionSummary = {
        id: res.sessionId,
        title: "New session",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      setSessions((prev) => [newSession, ...prev]);
      resetConversationState();
      loadedSessionIdRef.current = newSession.id;
      setMobileSidebarOpen(false);
      navigate(`/dashboard/${newSession.id}`);
    } catch (err) {
      console.error("Failed to create session", err);
    } finally {
      setCreatingSession(false);
    }
  }, [creatingSession, navigate]);

  const handleSelectSession = useCallback((sessionId: string) => {
    setMobileSidebarOpen(false);
    if (sessionId === activeSessionId) return;
    navigate(`/dashboard/${sessionId}`);
  }, [activeSessionId, navigate]);

  useEffect(() => {
    if (!activeSessionId) {
      loadedSessionIdRef.current = null;
      resetConversationState();
      return;
    }
    if (loadedSessionIdRef.current === activeSessionId) return;

    let cancelled = false;
    (async () => {
      try {
        setLoadingMessages(true);
        resetConversationState();
        const [res, reviews] = await Promise.all([
          fetchRequestGet(ApiObj.session.SESSION_MESSAGES(activeSessionId)) as Promise<any>,
          fetchPendingReview(activeSessionId),
        ]);
        if (cancelled) return;
        const pendingTurnIds = new Set(
          reviews.filter((r) => !r.resolved).map((r) => r.turnId)
        );
        const loaded: Message[] = (res ?? []).map((m: any) => ({
          id: m.id,
          role: m.role === "USER" ? "user" : "assistant",
          content: m.content,
          status: "done",
          turnId: m.turnId,
          pendingReview: pendingTurnIds.has(m.turnId),
        }));
        setMessages(loaded);
        loadedSessionIdRef.current = activeSessionId;
      } catch (err) {
        console.error("Failed to load session messages", err);
      } finally {
        if (!cancelled) setLoadingMessages(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeSessionId, fetchPendingReview]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => () => timersRef.current.forEach(clearTimeout), []);
  useEffect(() => () => reviewSourcesRef.current.forEach((es) => es.close()), []);

  useEffect(() => {
    if (state.currentStage) {
      setStage(mapNodeNameToStage(state.currentStage));
      const agent = mapNodeNameToAgent(state.currentStage);
      if (agent) setActiveAgent(agent);
    }
  }, [state.currentStage]);

  useEffect(() => {
    if (state.answerText && currentAssisstantIdRef.current) {
      setMessages((prev) => {
        return prev.map((m) => {
          return m.id === currentAssisstantIdRef.current ? { ...m, content: state.answerText, agent: activeAgent ?? undefined } : m;
        });
      });
    }
  }, [state.answerText]);

  useEffect(() => {
    if (!state.isStreaming && !state.pausedReview && currentAssisstantIdRef.current) {
      setMessages((prev) => (
        prev.map((m) =>
          m.id === currentAssisstantIdRef.current ? { ...m, status: "done" } : m
        )
      ));
      setStage("done");
      setIsBusy(false);
      currentAssisstantIdRef.current = null;
      fetchSessions();
    }
  }, [state.isStreaming, state.pausedReview, fetchSessions]);

  useEffect(() => {
    if (state.pausedReview && currentAssisstantIdRef.current) {
      const assistantId = currentAssisstantIdRef.current;
      const threadId = state.pausedReview.thread_id;
      setMessages((prev) => {
        return prev.map((m) => (m.id === assistantId ? { ...m, pendingReview: true } : m));
      });
      setStage("done");
      setIsBusy(false);
      currentAssisstantIdRef.current = null;
      fetchSessions();
      const accessToken = localStorage.getItem("accessToken");
      const es = new EventSource(
        `${ApiObj.baseUrl}${ApiObj.query.QUERY_NOTIFICATIONS(threadId)}?token=${accessToken}`,
        { withCredentials: true }
      );
      es.onmessage = (event) => {
        const parsed = JSON.parse(event.data);
        if (parsed.status === "resolved") {
          setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, content: parsed.result.answer, pendingReview: false, status: "done" } : m)));
          es.close();
        }
      };
      es.onerror = () => {
        es.close();
      };
      return () => {
        es.close();
      };
    }
  }, [state.pausedReview]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isBusy || !activeSessionId) return;

    const userId = crypto.randomUUID();
    const turnId = crypto.randomUUID();
    currentAssisstantIdRef.current = turnId;
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: text },
      { id: turnId, role: "assistant", content: "", status: "streaming" },
    ]);
    setInput("");
    setIsBusy(true);
    setActiveAgent(null);
    setSources(0);
    setStage(null);
    sendQuery(text, activeSessionId, turnId);
  }, [input, isBusy, sendQuery, activeSessionId]);

  const stageIndex = STAGES.findIndex((s) => s.id === stage);

  return (
    <div
      className="sb-shell"
      style={{
        background: COLORS.ink,
        color: COLORS.paper,
        fontFamily: "'Inter', sans-serif",
        height: "100vh",
        display: "flex",
        overflow: "hidden",
      }}
    >
      <GlobalStyles />

      <div
        className={`sb-backdrop${mobileSidebarOpen || mobileRailOpen ? " open" : ""}`}
        onClick={() => {
          setMobileSidebarOpen(false);
          setMobileRailOpen(false);
        }}
      />

      {/* MOBILE TOP BAR */}
      <div className="sb-mobile-bar">
        <button
          className="sb-mobile-toggle"
          onClick={() => setMobileSidebarOpen(true)}
          aria-label="Open sessions"
        >
          <Menu size={18} color={COLORS.paper} />
        </button>
        <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 14 }}>
          SWITCHBOARD
        </div>
        {activeSessionId ? (
          <button
            className="sb-mobile-toggle"
            onClick={() => setMobileRailOpen(true)}
            aria-label="Open routing status"
          >
            <Radio size={18} color={COLORS.paper} />
          </button>
        ) : (
          <span style={{ width: 34 }} />
        )}
      </div>

      <SessionSidebar
        className={`sb-sidebar${mobileSidebarOpen ? " open" : ""}`}
        onClose={() => setMobileSidebarOpen(false)}
        sessions={sessions}
        sessionsLoading={sessionsLoading}
        activeSessionId={activeSessionId}
        creatingSession={creatingSession}
        activeAgent={activeAgent}
        toolCalls={state.toolCalls}
        onCreateSession={handleCreateSession}
        onSelectSession={handleSelectSession}
        isAdmin={isAdmin}
        onNavigateAdminReview={handleNavigateAdminReview}
        onNavigateIngestion={handleNavigateIngestion}
      />

      {/* CENTER — TRANSCRIPT */}
      <div className="sb-center" style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {!activeSessionId ? (
          <EmptySessionState
            hasSessions={sessions.length > 0}
            creatingSession={creatingSession}
            onCreateSession={handleCreateSession}
          />
        ) : (
          <>
            <ConversationHeader messages={messages} activeAgent={activeAgent} />
            <MessageList ref={scrollRef} loadingMessages={loadingMessages} messages={messages} />
            <ChatComposer
              input={input}
              onInputChange={setInput}
              onSend={handleSend}
              isBusy={isBusy}
              loadingMessages={loadingMessages}
            />
          </>
        )}
      </div>

      <RoutingRail
        className={`sb-rail${mobileRailOpen ? " open" : ""}`}
        onClose={() => setMobileRailOpen(false)}
        stageIndex={stageIndex}
        isBusy={isBusy}
        activeAgent={activeAgent}
        sources={sources}
      />
    </div>
  );
}
