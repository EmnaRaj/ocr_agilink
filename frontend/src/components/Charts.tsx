import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
  PieChart, Pie, AreaChart, Area,
} from "recharts";
import type { ReactNode } from "react";
import type { Analytics } from "../api";

const PALETTE = ["#0e5b75", "#2f9bbd", "#10b981", "#f59e0b", "#a855f7", "#0ea5e9", "#f43f5e", "#84cc16"];
const STATUT_COLORS: Record<string, string> = { Extrait: "#0ea5e9", "En revue": "#f59e0b", Validé: "#10b981" };
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

/* ── SVG radial gauge for a single percentage ──────────────────────────── */
export function Gauge({ value, color }: { value: number; color: string }) {
  const r = 40;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.max(0, Math.min(100, value)) / 100);
  return (
    <div className="relative h-[112px] w-[112px]">
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#eef2f6" strokeWidth="9" />
        <circle
          cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={off}
          style={{ transition: "stroke-dashoffset .9s cubic-bezier(.2,.7,.2,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-2xl font-bold tabular-nums text-slate-800">{value}%</span>
      </div>
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

export function StatutDonut({ a }: { a: Analytics }) {
  return <Donut title="Statut des fiches" subtitle="Répartition par état" data={a.by_statut}
    color={(n, i) => STATUT_COLORS[n] ?? PALETTE[i]} centerSub="fiches" />;
}

export function ConformityDonut({ a }: { a: Analytics }) {
  return <Donut title="Conformité des contrôles" subtitle={`${a.kpis.conformity_pct}% conformes`} data={a.conformity}
    color={(n, i) => CONF_COLORS[n] ?? PALETTE[i]} centerSub="contrôles" />;
}

export function CoverageDonut({ a }: { a: Analytics }) {
  return <Donut title="Couverture de la gamme" subtitle={`${a.kpis.coverage_pct}% renseignées`} data={a.operation_coverage}
    color={(n) => (n === "Réalisées" ? "#0e5b75" : "#e2e8f0")} centerSub="opérations" />;
}

/* ── Bars ──────────────────────────────────────────────────────────────── */
export function OperatorBar({ a }: { a: Analytics }) {
  return (
    <ChartCard title="Charge par opérateur" subtitle="Opérations par matricule">
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

export function ProductBar({ a }: { a: Analytics }) {
  return (
    <ChartCard title="Volume par référence" subtitle="Quantités cumulées">
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

export function ActivityArea({ a }: { a: Analytics }) {
  return (
    <ChartCard title="Activité de numérisation" subtitle="Fiches scannées par jour">
      {a.fiches_by_day.length === 0 ? <NoData h={220} /> : (
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={a.fiches_by_day} margin={{ left: -16, right: 8, top: 8 }}>
            <defs>
              <linearGradient id="actGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#0e5b75" stopOpacity={0.22} />
                <stop offset="95%" stopColor="#0e5b75" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip />} />
            <Area type="monotone" dataKey="count" name="Fiches" stroke="#0e5b75" strokeWidth={2.5} fill="url(#actGrad)" dot={{ r: 3, fill: "#0e5b75" }} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

/* ── Top tools horizontal mini-bars ────────────────────────────────────── */
export function TopToolsList({ a }: { a: Analytics }) {
  const max = Math.max(1, ...a.top_tools.map((t) => t.count));
  return (
    <ChartCard title="Outillages les plus utilisés" subtitle="Fréquence d'apparition">
      {a.top_tools.length === 0 ? <NoData h={200} /> : (
        <ul className="space-y-3">
          {a.top_tools.map((t, i) => (
            <li key={i}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="truncate pr-2 text-slate-600">{t.name}</span>
                <span className="font-semibold tabular-nums text-slate-700">{t.count}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full" style={{ width: `${(100 * t.count) / max}%`, background: PALETTE[i % PALETTE.length] }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </ChartCard>
  );
}
