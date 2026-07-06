import { Sparkles, ShieldCheck } from "lucide-react";
import type { Statut } from "./api";

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const STATUT_LABEL: Record<Statut, string> = {
  extrait: "Extrait",
  en_revue: "En revue",
  valide: "Validé",
};
const STATUT_CLASS: Record<Statut, string> = {
  extrait: "badge-sky",
  en_revue: "badge-amber",
  valide: "badge-emerald",
};

export function StatutBadge({ statut, auto }: { statut: Statut; auto?: boolean }) {
  // Machine-validated is shown distinctly from human-confirmed: same "validated"
  // family, but a teal "Auto-validé" chip with a sparkle so a reviewer can tell
  // at a glance which sheets a person actually checked vs. which the system
  // passed on its own.
  if (statut === "valide" && auto) {
    return (
      <span className="badge border border-teal-200 bg-teal-50 text-teal-700">
        <Sparkles size={12} /> Auto-validé
      </span>
    );
  }
  if (statut === "valide") {
    return (
      <span className={`badge ${STATUT_CLASS.valide}`}>
        <ShieldCheck size={12} /> Validé
      </span>
    );
  }
  const dot = { extrait: "bg-sky-500", en_revue: "bg-amber-500", valide: "bg-emerald-500" }[statut];
  return (
    <span className={`badge ${STATUT_CLASS[statut]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {STATUT_LABEL[statut]}
    </span>
  );
}

/** Confidence chip: green ≥0.6, amber ≥0.3, red below, grey when null. */
export function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null || value === undefined)
    return <span className="text-slate-400 text-xs">—</span>;
  const pct = Math.round(value * 100);
  const cls = value >= 0.6 ? "badge-emerald" : value >= 0.3 ? "badge-amber" : "badge-rose";
  return <span className={`badge tabular-nums ${cls}`}>{pct}%</span>;
}

/** Inline cell value with a subtle confidence underline; flags low-confidence. */
export function FieldCell({
  value,
  confidence,
  raw,
}: {
  value: unknown;
  confidence?: number;
  raw?: string | null;
}) {
  const empty = value === null || value === undefined || value === "";
  if (empty && raw) {
    return (
      <span title={`lecture brute: ${raw} (à confirmer)`} className="text-slate-400 italic">
        {raw}
        <span className="ml-1 text-[10px] text-amber-500">⚠</span>
      </span>
    );
  }
  if (empty) return <span className="text-slate-300">—</span>;
  const low = confidence !== undefined && confidence < 0.6;
  return (
    <span
      className={low ? "text-amber-700" : "text-slate-800"}
      title={confidence !== undefined ? `confiance ${Math.round(confidence * 100)}%` : undefined}
    >
      {String(typeof value === "boolean" ? (value ? "Oui" : "Non") : value)}
      {low && <span className="ml-1 text-[10px] text-amber-500">⚠</span>}
    </span>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-16 text-agilink-600">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-agilink-200 border-t-agilink-600" />
    </div>
  );
}
