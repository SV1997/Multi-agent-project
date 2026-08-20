import { Send } from "lucide-react";
import { COLORS } from "./constants";

type ChatComposerProps = {
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  isBusy: boolean;
  loadingMessages: boolean;
};

export default function ChatComposer({ input, onInputChange, onSend, isBusy, loadingMessages }: ChatComposerProps) {
  const disabled = isBusy || !input.trim() || loadingMessages;

  return (
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
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          disabled={loadingMessages}
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
          onClick={onSend}
          disabled={disabled}
          style={{
            background: disabled ? COLORS.hairline : COLORS.signal,
            border: "none",
            borderRadius: 9,
            width: 36,
            height: 36,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: disabled ? "not-allowed" : "pointer",
            flexShrink: 0,
          }}
        >
          <Send size={15} color={isBusy || !input.trim() ? COLORS.muted : COLORS.ink} />
        </button>
      </div>
    </div>
  );
}
