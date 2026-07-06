import { createContext, useContext, useState, type ReactNode } from "react";
import { api, type ChatEvent } from "./api";

// One shared chat, lifted to the app root so it survives navigation (the floating
// bubble and the /assistant page render the SAME conversation) and only resets on a
// full reload — matching the stateless design.

export interface Step {
  tool: string;
  args?: Record<string, unknown> | string;
  sql?: string;
  rows?: number;
  error?: string;
}

export interface Msg {
  role: "user" | "assistant";
  content: string; // answer (Markdown)
  reasoning?: string; // model thinking tokens (reasoning models)
  steps?: Step[]; // tools / SQL the agent used (sources)
  streaming?: boolean;
}

interface ChatState {
  msgs: Msg[];
  busy: boolean;
  ask: (q: string) => void;
  reset: () => void;
}

const Ctx = createContext<ChatState | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);

  const patchLast = (fn: (m: Msg) => Msg) =>
    setMsgs((m) => {
      const c = [...m];
      c[c.length - 1] = fn(c[c.length - 1]);
      return c;
    });

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    const history = msgs.map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [
      ...m,
      { role: "user", content: question },
      { role: "assistant", content: "", reasoning: "", steps: [], streaming: true },
    ]);
    setBusy(true);
    try {
      await api.chatStream(question, history, (ev: ChatEvent) => {
        if (ev.t === "text") patchLast((m) => ({ ...m, content: m.content + ev.d }));
        else if (ev.t === "reason") patchLast((m) => ({ ...m, reasoning: (m.reasoning || "") + ev.d }));
        else if (ev.t === "step") patchLast((m) => ({ ...m, steps: [...(m.steps || []), ev] }));
        else if (ev.t === "error") patchLast((m) => ({ ...m, content: m.content + ev.d }));
      });
    } catch (e) {
      patchLast((m) => ({ ...m, content: `Erreur : ${e instanceof Error ? e.message : e}` }));
    } finally {
      patchLast((m) => ({ ...m, streaming: false }));
      setBusy(false);
    }
  }

  const reset = () => setMsgs([]);

  return <Ctx.Provider value={{ msgs, busy, ask, reset }}>{children}</Ctx.Provider>;
}

export function useChat(): ChatState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useChat must be used within ChatProvider");
  return c;
}
