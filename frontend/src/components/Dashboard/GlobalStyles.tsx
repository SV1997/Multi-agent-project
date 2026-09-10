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

      .sb-bubble { overflow-wrap: anywhere; word-break: break-word; }
      .sb-bubble > *:first-child { margin-top: 0; }
      .sb-bubble > *:last-child { margin-bottom: 0; }
      .sb-bubble img { max-width: 100%; height: auto; }
      .sb-bubble pre {
        max-width: 100%;
        overflow-x: auto;
        white-space: pre;
        box-sizing: border-box;
      }
      .sb-bubble code {
        overflow-wrap: anywhere;
        word-break: break-word;
        white-space: pre-wrap;
      }
      .sb-bubble pre code {
        white-space: pre;
        word-break: normal;
        overflow-wrap: normal;
      }
      .sb-bubble table {
        display: block;
        max-width: 100%;
        overflow-x: auto;
        border-collapse: collapse;
      }

      .sb-mobile-bar { display: none; }
      .sb-mobile-toggle { display: none; background: none; border: none; cursor: pointer; padding: 4px; }
      .sb-backdrop { display: none; }

      @media (max-width: 860px) {
        .sb-mobile-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 14px;
          border-bottom: 1px solid #263047;
          flex-shrink: 0;
        }
        .sb-mobile-toggle { display: inline-flex; align-items: center; justify-content: center; }
        .sb-shell { flex-direction: column !important; height: 100vh !important; height: 100dvh !important; }
        .sb-center { min-width: 0 !important; min-height: 0 !important; }

        .sb-sidebar, .sb-rail {
          position: fixed !important;
          top: 0;
          bottom: 0;
          width: 82vw !important;
          max-width: 300px;
          height: 100vh;
          height: 100dvh;
          z-index: 45;
          background: #0B0F17;
          box-shadow: 0 0 24px rgba(0,0,0,0.5);
          transition: transform 0.25s ease;
          overflow-y: auto;
          display: flex !important;
        }
        .sb-sidebar { left: 0; transform: translateX(-100%); }
        .sb-sidebar.open { transform: translateX(0); }
        .sb-rail { right: 0; transform: translateX(100%); }
        .sb-rail.open { transform: translateX(0); }

        .sb-backdrop.open {
          display: block;
          position: fixed;
          inset: 0;
          background: rgba(0,0,0,0.5);
          z-index: 40;
        }

        .sb-msglist {
          min-height: 0 !important;
          padding-bottom: 190px !important;
        }

        .sb-composer {
          position: fixed !important;
          left: 0;
          right: 0;
          bottom: 0;
          z-index: 35;
          background: #0B0F17;
        }
      }

      @media (max-width: 560px) {
        .sb-msg > div { max-width: 92% !important; }
        .sb-conv-header { padding: 12px 16px !important; }
        .sb-composer { padding: 12px 16px 16px !important; }
        .sb-msglist { padding: 16px !important; }
      }
    `}</style>
  );
}
