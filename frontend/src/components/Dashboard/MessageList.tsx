import { forwardRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { COLORS } from "./constants";
import type { Message } from "./types";

type MessageListProps = {
  loadingMessages: boolean;
  messages: Message[];
};

const MessageList = forwardRef<HTMLDivElement, MessageListProps>(function MessageList(
  { loadingMessages, messages },
  scrollRef
) {
  return (
    <div ref={scrollRef} className="sb-scroll sb-msglist" style={{ flex: 1, overflowY: "auto", padding: "24px 28px", minHeight: 0 }}>
      {loadingMessages && (
        <div style={{ textAlign: "center", color: COLORS.muted, fontSize: 13, paddingTop: 40 }}>
          Loading session…
        </div>
      )}
      {!loadingMessages && messages.length === 0 && (
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
              <div style={{ alignSelf: "flex-end", maxWidth: "78%", minWidth: 0 }}>
                <div
                  style={{
                    background: COLORS.raised,
                    border: `1px solid ${COLORS.hairline}`,
                    borderRadius: "12px 12px 3px 12px",
                    padding: "10px 14px",
                    fontSize: 14,
                    lineHeight: 1.5,
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {m.content}
                </div>
              </div>
            ) : (
              <div style={{ alignSelf: "flex-start", maxWidth: "82%", minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                  <span style={{ width: 6, height: 6, borderRadius: 999, background: m.agent?.color }} />
                  <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: m.agent?.color, letterSpacing: 0.4 }}>
                    {m.agent?.name.toUpperCase()}
                  </span>
                </div>
                <div
                  className="sb-bubble"
                  style={{
                    background: COLORS.panel,
                    border: `1px solid ${COLORS.hairline}`,
                    borderRadius: "3px 12px 12px 12px",
                    padding: "12px 14px",
                    fontSize: 14,
                    lineHeight: 1.6,
                    minWidth: 0,
                    maxWidth: "100%",
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                  }}
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
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
  );
});

export default MessageList;
