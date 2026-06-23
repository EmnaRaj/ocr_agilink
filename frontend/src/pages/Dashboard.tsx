import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  FileStack, ListChecks, Users, ShieldCheck, ScanLine, ArrowRight, ArrowUpRight,
} from "lucide-react";
import { api, type Stats, type Analytics } from "../api";
import { ConfidenceBadge, StatutBadge, Spinner, fmtDateTime } from "../ui";
import {
  ChartCard, Gauge, StatutDonut, OperatorBar, TimelineBar, ProductBar, ActivityArea, TopToolsList,
} from "../components/Charts";

function KpiTile({ icon: Icon, label, value, hint, tint }: {
  icon: typeof FileStack; label: string; value: string; hint?: string; tint: string;
}) {
  return (
    <div className="card card-hover group relative overflow-hidden p-5">
      <div className="flex items-start justify-between">
        <div className={`flex h-11 w-11 items-center justify-center rounded-xl text-white shadow-soft ${tint}`}>
          <Icon size={20} />
        </div>
        {hint && (
          <span className="chip bg-emerald-50 text-emerald-600">
            <ArrowUpRight size={12} /> {hint}
          </span>
        )}
      </div>
      <p className="mt-4 text-3xl font-bold tracking-tight text-slate-800 tabular-nums">{value}</p>
      <p className="mt-0.5 text-sm font-medium text-slate-400">{label}</p>
      <div className="pointer-events-none absolute -right-6 -bottom-8 h-24 w-24 rounded-full bg-agilink-500/[0.04] transition-transform duration-300 group-hover:scale-125" />
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [a, setA] = useState<Analytics | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.stats(), api.analytics()]).then(([s, an]) => { setStats(s); setA(an); }).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="text-rose-600">Erreur: {err}</div>;
  if (!stats || !a) return <Spinner />;
  const k = a.kpis;
  const today = new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="animate-fade-in space-y-5">
      {/* Page sub-header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Vue d'ensemble</p>
          <h2 className="text-xl font-bold tracking-tight text-slate-800">Synthèse de la traçabilité</h2>
          <p className="mt-0.5 text-sm capitalize text-slate-400">{today}</p>
        </div>
        <Link to="/scanner" className="btn-primary">
          <ScanLine size={17} /> Scanner une fiche
        </Link>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile icon={FileStack} label="Fiches traitées" value={String(k.fiches)} tint="bg-brand" />
        <KpiTile icon={ListChecks} label="Opérations relevées" value={String(k.operations)} tint="bg-gradient-to-br from-sky-500 to-sky-600" />
        <KpiTile icon={Users} label="Opérateurs actifs" value={String(k.operators)} tint="bg-gradient-to-br from-violet-500 to-purple-600" />
        <KpiTile icon={ShieldCheck} label="Fiches validées" value={`${k.validated}/${k.fiches}`} tint="bg-gradient-to-br from-emerald-500 to-teal-600" />
      </div>

      {/* Hero: quality gauges + featured timeline */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard title="Indicateurs qualité" subtitle="Couverture gamme & conformité contrôles">
          <div className="flex items-center justify-around py-3">
            <div className="flex flex-col items-center gap-2">
              <Gauge value={k.coverage_pct} color="#0e5b75" />
              <span className="text-xs font-medium text-slate-500">Couverture</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Gauge value={k.conformity_pct} color="#10b981" />
              <span className="text-xs font-medium text-slate-500">Conformité</span>
            </div>
          </div>
        </ChartCard>
        <div className="lg:col-span-2">
          <TimelineBar a={a} />
        </div>
      </div>

      {/* Distribution row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <StatutDonut a={a} />
        <OperatorBar a={a} />
        <ProductBar a={a} />
      </div>

      {/* Activity + tools */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ActivityArea a={a} />
        </div>
        <TopToolsList a={a} />
      </div>

      {/* Recent fiches */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div>
            <h3 className="panel-title">Fiches récentes</h3>
            <p className="panel-sub">Dernières fiches numérisées</p>
          </div>
          <Link to="/historique" className="flex items-center gap-1 text-sm font-semibold text-agilink-600 transition-all hover:gap-2">
            Tout l'historique <ArrowRight size={15} />
          </Link>
        </div>
        {stats.recent.length === 0 ? (
          <div className="px-6 py-14 text-center text-slate-400">
            Aucune fiche pour l'instant. <Link to="/scanner" className="font-semibold text-agilink-600 hover:underline">Scanner une fiche</Link>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-slate-400">
                <th className="px-6 py-3 font-medium">Réf. Produit</th>
                <th className="px-6 py-3 font-medium">N° OF</th>
                <th className="px-6 py-3 font-medium">Date</th>
                <th className="px-6 py-3 font-medium">Confiance</th>
                <th className="px-6 py-3 font-medium">Statut</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {stats.recent.map((f) => (
                <tr key={f.fiche_id} className="transition-colors hover:bg-agilink-50/40">
                  <td className="px-6 py-3.5">
                    <Link to={`/fiches/${f.fiche_id}`} className="font-semibold text-agilink-700 hover:underline">{f.ref_produit}</Link>
                  </td>
                  <td className="px-6 py-3.5 text-slate-600">{f.n_of}</td>
                  <td className="px-6 py-3.5 text-slate-500">{fmtDateTime(f.date_creation)}</td>
                  <td className="px-6 py-3.5"><ConfidenceBadge value={f.overall_confidence} /></td>
                  <td className="px-6 py-3.5"><StatutBadge statut={f.statut} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
