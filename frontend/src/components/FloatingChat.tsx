import { useState } from "react";
import { useLocation } from "react-router-dom";
import { Sparkles, X, Bot } from "lucide-react";
import ChatThread from "./ChatThread";

export default function FloatingChat() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();

  // The dedicated /assistant page already is the chat — no floating bubble there.
  if (pathname === "/assistant") return null;

  return (
    <>
      {open && (
        <div className="animate-scale-in fixed bottom-24 right-6 z-50 flex h-[560px] w-[min(400px,calc(100vw-3rem))] flex-col overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-50 shadow-glow">
          <header className="flex items-center gap-2.5 bg-brand px-4 py-3 text-white">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15">
              <Bot size={17} />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold">Assistant Traçabilité</p>
              <p className="text-[11px] text-white/70">Posez vos questions sur les données</p>
            </div>
            <button onClick={() => setOpen(false)} className="ml-auto rounded-lg p-1.5 hover:bg-white/15">
              <X size={18} />
            </button>
          </header>
          <div className="flex-1 overflow-hidden p-3">
            <ChatThread compact />
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Assistant"
        className="group fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-white shadow-glow transition-all hover:scale-105 active:scale-95"
      >
        {open ? <X size={24} /> : <Sparkles size={24} />}
        {!open && (
          <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-emerald-500 ring-2 ring-white/40" />
          </span>
        )}
      </button>
    </>
  );
}
