import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Bot, User } from "lucide-react";
import { api } from "../api";

interface Msg {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

const SUGGESTIONS = [
  "Combien de fiches au total ?",
  "Quelle est la réf produit de la fiche 1 ?",
  "Quel opérateur a fait le plus d'opérations ?",
  "Y a-t-il des contrôles non conformes ?",
];

export default function ChatThread({ compact = false }: { compact?: boolean }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [msgs]);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    const history = msgs.map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: question }, { role: "assistant", content: "", streaming: true }]);
    setInput("");
    setBusy(true);
    try {
      await api.chatStream(question, history, (chunk) => {
        setMsgs((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + chunk };
          return copy;
        });
      });
    } catch (e) {
      setMsgs((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", content: `Erreur : ${e instanceof Error ? e.message : e}` };
        return copy;
      });
    } finally {
      setMsgs((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, streaming: false } : x)));
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-1 pb-3">
        {msgs.length === 0 && (
          <div className="animate-scale-in mt-4 text-center">
            {!compact && (
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-brand text-white shadow-glow">
                <Sparkles size={30} />
              </div>
            )}
            <h2 className={`${compact ? "mt-1 text-base" : "mt-4 text-2xl"} font-bold tracking-tight text-slate-800`}>
              Assistant Traçabilité
            </h2>
            <p className={`mx-auto mt-1.5 max-w-md text-slate-500 ${compact ? "text-xs" : "text-sm"}`}>
              Interrogez toute votre base de fiches en langage naturel.
            </p>
            <div className={`mx-auto mt-5 grid max-w-xl gap-2.5 ${compact ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2"}`}>
              {(compact ? SUGGESTIONS.slice(0, 3) : SUGGESTIONS).map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="card group flex items-center gap-2 px-3.5 py-2.5 text-left text-[13px] text-slate-600 transition-all hover:-translate-y-0.5 hover:border-agilink-300 hover:text-agilink-700 hover:shadow-soft"
                >
                  <Sparkles size={14} className="shrink-0 text-agilink-400 group-hover:text-agilink-600" />
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {msgs.map((m, i) => (
          <div key={i} className={`flex animate-fade-in gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <div
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl shadow-soft ${
                m.role === "user" ? "bg-brand text-white" : "bg-white text-agilink-600 ring-1 ring-slate-200"
              }`}
            >
              {m.role === "user" ? <User size={15} /> : <Bot size={15} />}
            </div>
            <div className={`max-w-[84%] ${m.role === "user" ? "text-right" : ""}`}>
              <div
                className={`inline-block whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-[13.5px] leading-relaxed ${
                  m.role === "user" ? "bg-brand text-white shadow-soft" : "card text-slate-700"
                }`}
              >
                {m.role === "assistant" && m.streaming && !m.content ? (
                  <span className="inline-flex gap-1 py-1">
                    {[0, 1, 2].map((d) => (
                      <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-agilink-300" style={{ animationDelay: `${d * 0.15}s` }} />
                    ))}
                  </span>
                ) : (
                  <span className={m.streaming ? "caret" : ""}>{m.content}</span>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="mt-1 flex items-center gap-2 rounded-2xl border border-slate-200/70 bg-white p-1.5 shadow-soft"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Posez votre question…"
          className="flex-1 bg-transparent px-3 py-2 text-sm focus:outline-none"
        />
        <button
          type="submit"
          disabled={!input.trim() || busy}
          className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-white shadow-soft transition hover:opacity-90 disabled:opacity-40"
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}
