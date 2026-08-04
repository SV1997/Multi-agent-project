export default function GlobalStyles() {
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
