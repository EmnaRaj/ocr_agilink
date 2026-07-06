import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Bot, User, Database } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChat, type Msg, type Step } from "../ChatContext";

const SUGGESTIONS = [
  "Combien de fiches au total ?",
  "Quelle est la réf produit de la fiche 1 ?",
  "Quel opérateur a fait le plus d'opérations ?",
  "Y a-t-il des contrôles non conformes ?",
];

function ReasoningPanel({ text, active }: { text: string; active: boolean }) {
  // Auto-expands while the model is actively reasoning (streaming, no answer yet),
  // then auto-collapses once the answer begins. Still manually toggleable afterwards.
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(active), [active]);
  if (!text.trim()) return null;
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className="mb-1.5 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[12px] text-slate-500 ring-1 ring-slate-200/70"
    >
      <summary className="flex cursor-pointer select-none items-center gap-1.5 font-medium text-slate-500">
        Raisonnement
        {active && (
          <span className="inline-flex gap-0.5">
            {[0, 1, 2].map((d) => (
              <span key={d} className="h-1 w-1 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${d * 0.15}s` }} />
            ))}
          </span>
        )}
      </summary>
      <div className="md mt-1 leading-snug text-slate-500">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    </details>
  );
}

// Human-readable description of what each tool actually pulled (the "source").
const SOURCE_LABEL: Record<string, string> = {
  get_overview: "Statistiques globales — KPIs, charge par opérateur, conformité",
  get_referential: "Référentiel — opérateurs et outils connus",
  list_review_queue: "File de revue — fiches à contrôler",
  search_fiches: "Recherche de fiches",
  get_fiche: "Détail d'une fiche",
  describe_schema: "Schéma des vues analytiques",
  run_sql: "Requête SQL sur les vues analytiques",
};

function argsSummary(args?: Record<string, unknown> | string): string {
  if (!args) return "";
  if (typeof args === "string") return args;
  const parts = Object.entries(args).map(([k, v]) => `${k}=${v}`);
  return parts.join(", ");
}

function SourcesPanel({ steps }: { steps: Step[] }) {
  if (!steps.length) return null;
  return (
    <details className="mb-1.5 rounded-lg bg-agilink-50/60 px-2.5 py-1.5 text-[12px] text-agilink-800 ring-1 ring-agilink-200/60">
      <summary className="flex cursor-pointer select-none items-center gap-1.5 font-medium text-agilink-700">
        <Database size={12} /> Sources · {steps.length}
      </summary>
      <ul className="mt-1.5 space-y-2">
        {steps.map((s, i) => {
          const argStr = argsSummary(s.args);
          return (
            <li key={i} className="leading-snug">
              <div className="font-medium text-agilink-800">
                {SOURCE_LABEL[s.tool] || s.tool}
                {typeof s.rows === "number" && <span className="text-slate-400"> · {s.rows} ligne(s)</span>}
              </div>
              <div className="text-[11px] text-slate-400">
                <span className="font-mono">{s.tool}</span>
                {argStr && <span> · {argStr}</span>}
              </div>
              {s.error && <div className="text-[11px] text-rose-500">{s.error}</div>}
              {s.sql && (
                <pre className="mt-0.5 overflow-x-auto rounded bg-white/70 p-1.5 text-[11px] text-slate-600 ring-1 ring-slate-200/70">
                  {s.sql}
                </pre>
              )}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function AssistantBubble({ m }: { m: Msg }) {
  if (m.streaming && !m.content && !m.reasoning && !(m.steps && m.steps.length)) {
    return (
      <span className="inline-flex gap-1 py-1">
        {[0, 1, 2].map((d) => (
          <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-agilink-300" style={{ animationDelay: `${d * 0.15}s` }} />
        ))}
      </span>
    );
  }
  return (
    <div>
      <ReasoningPanel text={m.reasoning || ""} active={!!m.streaming && !m.content} />
      {m.content && (
        <div className="md">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
        </div>
      )}
      <SourcesPanel steps={m.steps || []} />
    </div>
  );
}

export default function ChatThread({ compact = false }: { compact?: boolean }) {
  const { msgs, busy, ask } = useChat();
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [msgs]);

  function submit(question: string) {
    if (!question.trim() || busy) return;
    setInput("");
    ask(question);
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
                  onClick={() => submit(s)}
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
                className={`rounded-2xl px-3.5 py-2 text-[13.5px] leading-relaxed ${
                  m.role === "user"
                    ? "inline-block whitespace-pre-wrap bg-brand text-white shadow-soft"
                    : "block card text-slate-700"
                }`}
              >
                {m.role === "user" ? <span>{m.content}</span> : <AssistantBubble m={m} />}
              </div>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
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
