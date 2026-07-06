import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
  PieChart, Pie, Legend,
} from "recharts";
import type { ReactNode } from "react";
import type { Analytics } from "../api";

const PALETTE = ["#0e5b75", "#2f9bbd", "#10b981", "#f59e0b", "#a855f7", "#0ea5e9", "#f43f5e", "#84cc16"];
const FUNNEL_COLORS: Record<string, string> = { Extrait: "#0ea5e9", "En revue": "#f59e0b", Validé: "#10b981" };
const CONF_COLORS: Record<string, string> = { Conforme: "#10b981", "Non conforme": "#f43f5e", "Non renseigné": "#cbd5e1" };

function Tip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-soft">
      {label && <p className="mb-1 font-semibold text-slate-700">{label}</p>}
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color ?? p.payload?.fill ?? p.fill }} className="font-medium">
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  );
}

export function ChartCard({ title, subtitle, action, children, className = "" }: {
  title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <div className={`card animate-fade-in p-5 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-2">
        <div>
          <h3 className="panel-title">{title}</h3>
          {subtitle && <p className="panel-sub mt-0.5">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

const NoData = ({ h = 180 }: { h?: number }) => (
  <div className="flex items-center justify-center text-sm text-slate-300" style={{ height: h }}>
    Pas encore de données
  </div>
);

/* ── SVG radial gauge for a single percentage (null → dash) ─────────────── */
export function Gauge({ value, color, label }: { value: number | null; color: string; label: string }) {
  const r = 40;
  const c = 2 * Math.PI * r;
  const v = value ?? 0;
  const off = c * (1 - Math.max(0, Math.min(100, v)) / 100);
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-[112px] w-[112px]">
        {value === null ? (
          <div className="flex h-full w-full items-center justify-center text-2xl font-bold text-slate-300">—</div>
        ) : (
          <>
            <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
              <circle cx="50" cy="50" r={r} fill="none" stroke="#eef2f6" strokeWidth="9" />
              <circle
                cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
                strokeDasharray={c} strokeDashoffset={off}
                style={{ transition: "stroke-dashoffset .9s cubic-bezier(.2,.7,.2,1)" }}
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-2xl font-bold tabular-nums text-slate-800">{v}%</span>
            </div>
          </>
        )}
      </div>
      <span className="text-xs font-medium text-slate-500">{label}</span>
    </div>
  );
}

/* ── Generic donut with center total + side legend ─────────────────────── */
function Donut({
  title, subtitle, data, color, center, centerSub,
}: {
  title: string; subtitle?: string;
  data: { name: string; value: number }[];
  color: (name: string, i: number) => string;
  center?: string | number; centerSub?: string;
}) {
  const shown = data.filter((d) => d.value > 0);
  const total = shown.reduce((s, d) => s + d.value, 0);
  return (
    <ChartCard title={title} subtitle={subtitle}>
      {total === 0 ? <NoData /> : (
        <div className="flex items-center gap-4">
          <div className="relative h-[150px] w-[150px] shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={shown} dataKey="value" nameKey="name" innerRadius={50} outerRadius={70} paddingAngle={2} stroke="none">
                  {shown.map((d, i) => <Cell key={i} fill={color(d.name, i)} />)}
                </Pie>
                <Tooltip content={<Tip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold tabular-nums text-slate-800">{center ?? total}</span>
              {centerSub && <span className="text-[10px] uppercase tracking-wide text-slate-400">{centerSub}</span>}
            </div>
          </div>
          <ul className="flex-1 space-y-2">
            {shown.map((d, i) => (
              <li key={i} className="flex items-center justify-between gap-2 text-xs">
                <span className="flex items-center gap-2 text-slate-600">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: color(d.name, i) }} />
                  {d.name}
                </span>
                <span className="font-semibold tabular-nums text-slate-700">
                  {d.value} <span className="text-slate-400">· {Math.round((100 * d.value) / total)}%</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </ChartCard>
  );
}

/* ── Generic horizontal mini-bar list ──────────────────────────────────── */
function MiniBarList({
  title, subtitle, rows, h = 200,
}: {
  title: string; subtitle?: string; h?: number;
  rows: { label: string; value: number; display: ReactNode }[];
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ChartCard title={title} subtitle={subtitle}>
      {rows.length === 0 ? <NoData h={h} /> : (
        <ul className="space-y-3">
          {rows.map((r, i) => (
            <li key={i}>
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className="truncate pr-2 text-slate-600">{r.label}</span>
                <span className="shrink-0 font-semibold tabular-nums text-slate-700">{r.display}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full" style={{ width: `${(100 * r.value) / max}%`, background: PALETTE[i % PALETTE.length] }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </ChartCard>
  );
}

/* ── 1. Conformity & defects ───────────────────────────────────────────── */
export function ConformityDonut({ a }: { a: Analytics }) {
  return <Donut title="Conformité des contrôles"
    subtitle={a.kpis.conformity_pct != null ? `${a.kpis.conformity_pct}% conformes` : "Aucun contrôle renseigné"}
    data={a.conformity} color={(n, i) => CONF_COLORS[n] ?? PALETTE[i]} centerSub="contrôles" />;
}

export function ControlResultsByType({ a }: { a: Analytics }) {
  return (
    <ChartCard title="Résultats par type de contrôle" subtitle="Conforme · non conforme · non renseigné">
      {a.control_results_by_type.length === 0 ? <NoData h={220} /> : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={a.control_results_by_type} margin={{ left: -16, right: 8, top: 8 }} barCategoryGap="28%">
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis dataKey="type" tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} interval={0} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip />} cursor={{ fill: "#f8fafc" }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="ok" name="Conforme" stackId="s" fill="#10b981" radius={[0, 0, 0, 0]} maxBarSize={54} />
            <Bar dataKey="ko" name="Non conforme" stackId="s" fill="#f43f5e" maxBarSize={54} />
            <Bar dataKey="na" name="Non renseigné" stackId="s" fill="#cbd5e1" radius={[6, 6, 0, 0]} maxBarSize={54} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

export function NonConformitiesByProduct({ a }: { a: Analytics }) {
  return <MiniBarList title="Non-conformités par référence" subtitle="Contrôles en échec"
    rows={a.non_conformities_by_product.map((p) => ({ label: p.ref, value: p.count, display: p.count }))} />;
}

/* ── 2. Operation flow & bottlenecks ───────────────────────────────────── */
export function CoverageDonut({ a }: { a: Analytics }) {
  const done = a.operation_coverage.find((d) => d.name === "Réalisées")?.value ?? 0;
  const total = a.operation_coverage.reduce((s, d) => s + d.value, 0);
  const pct = total ? Math.round((100 * done) / total) : 0;
  return <Donut title="Couverture de la gamme" subtitle={`${pct}% des opérations renseignées`}
    data={a.operation_coverage} color={(n) => (n === "Réalisées" ? "#0e5b75" : "#e2e8f0")} centerSub="opérations" />;
}

export function CoverageByOperationList({ a }: { a: Analytics }) {
  return <MiniBarList title="Taux de réalisation par opération" subtitle="Part des fiches où l'opération est renseignée" h={260}
    rows={a.coverage_by_operation.slice(0, 10).map((o) => ({
      label: o.name, value: o.pct,
      display: <>{o.pct}% <span className="text-slate-400">· {o.applied}/{o.total}</span></>,
    }))} />;
}

export function CycleTimeList({ a }: { a: Analytics }) {
  return <MiniBarList title="Goulots d'étranglement" subtitle="Temps de cycle moyen par opération (début → fin)"
    rows={a.cycle_time_by_operation.map((t) => ({
      label: t.name, value: t.avg_minutes,
      display: <>{t.avg_minutes} min <span className="text-slate-400">· {t.n} relevés</span></>,
    }))} />;
}

export function TimelineBar({ a }: { a: Analytics }) {
  return (
    <ChartCard title="Opérations par jour" subtitle="Selon la date d'opération relevée">
      {a.timeline.length === 0 ? <NoData h={260} /> : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={a.timeline} margin={{ left: -16, right: 8, top: 8 }} barCategoryGap="22%">
            <defs>
              <linearGradient id="opGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2f9bbd" />
                <stop offset="100%" stopColor="#0e5b75" />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip />} cursor={{ fill: "#f8fafc" }} />
            <Bar dataKey="operations" name="Opérations" fill="url(#opGrad)" radius={[6, 6, 0, 0]} maxBarSize={56} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

/* ── 3. Operator performance ───────────────────────────────────────────── */
export function OperatorBar({ a }: { a: Analytics }) {
  return (
    <ChartCard title="Charge par opérateur" subtitle="Opérations relevées par matricule">
      {a.operator_workload.length === 0 ? <NoData h={220} /> : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={a.operator_workload} margin={{ left: -16, right: 8, top: 8 }} barCategoryGap="28%">
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis dataKey="matricule" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip />} cursor={{ fill: "#f8fafc" }} />
            <Bar dataKey="operations" name="Opérations" radius={[6, 6, 0, 0]} maxBarSize={48}>
              {a.operator_workload.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

export function OperatorCycleList({ a }: { a: Analytics }) {
  return <MiniBarList title="Temps de cycle moyen par opérateur" subtitle="Minutes moyennes (début → fin)"
    rows={a.operator_cycle_time.map((o) => ({
      label: `Matricule ${o.name}`, value: o.avg_minutes,
      display: <>{o.avg_minutes} min <span className="text-slate-400">· {o.n} relevés</span></>,
    }))} />;
}

/* ── 4. Quantity & traceability ────────────────────────────────────────── */
export function ProductBar({ a }: { a: Analytics }) {
  return (
    <ChartCard title="Volume par référence" subtitle="Quantités commandées cumulées">
      {a.product_volumes.length === 0 ? <NoData h={220} /> : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={a.product_volumes} layout="vertical" margin={{ left: 8, right: 16, top: 4 }} barCategoryGap="30%">
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="ref" tick={{ fontSize: 10, fill: "#64748b" }} width={86} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip />} cursor={{ fill: "#f8fafc" }} />
            <Bar dataKey="qty" name="Quantité" radius={[0, 6, 6, 0]} maxBarSize={28}>
              {a.product_volumes.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

export function SerialsByProductList({ a }: { a: Analytics }) {
  return <MiniBarList title="Numéros de série tracés" subtitle="Par référence produit"
    rows={a.serials_by_product.map((p) => ({ label: p.ref, value: p.serials, display: p.serials }))} />;
}

export function TopToolsList({ a }: { a: Analytics }) {
  return <MiniBarList title="Outillages les plus utilisés" subtitle="Fréquence d'apparition"
    rows={a.top_tools.map((t) => ({ label: t.name, value: t.count, display: t.count }))} />;
}

/* ── Process funnel (the one file-level figure kept) ────────────────────── */
export function ReviewFunnelDonut({ a }: { a: Analytics }) {
  return <Donut title="File de revue" subtitle="Avancement du traitement des fiches" data={a.review_funnel}
    color={(n, i) => FUNNEL_COLORS[n] ?? PALETTE[i]} centerSub="fiches" />;
}
