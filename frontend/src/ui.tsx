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
  extrait: "bg-sky-100 text-sky-700",
  en_revue: "bg-amber-100 text-amber-700",
  valide: "bg-emerald-100 text-emerald-700",
};

export function StatutBadge({ statut }: { statut: Statut }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUT_CLASS[statut]}`}>
      {STATUT_LABEL[statut]}
    </span>
  );
}

/** Confidence chip: green ≥0.6, amber ≥0.3, red below, grey when null. */
export function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null || value === undefined)
    return <span className="text-slate-400 text-xs">—</span>;
  const pct = Math.round(value * 100);
  const cls =
    value >= 0.6
      ? "bg-emerald-100 text-emerald-700"
      : value >= 0.3
      ? "bg-amber-100 text-amber-700"
      : "bg-rose-100 text-rose-700";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${cls}`}>
      {pct}%
    </span>
  );
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
