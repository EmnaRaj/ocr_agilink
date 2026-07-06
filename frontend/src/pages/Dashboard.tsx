import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ListChecks, ShieldCheck, Timer, TriangleAlert, Users, ScanLine, ArrowRight, ArrowUpRight, Database,
} from "lucide-react";
import { api, type Stats, type Analytics } from "../api";
import { ConfidenceBadge, StatutBadge, Spinner, fmtDateTime } from "../ui";
import {
  ChartCard, Gauge, ConformityDonut, ControlResultsByType, NonConformitiesByProduct,
  CoverageDonut, CoverageByOperationList, CycleTimeList, TimelineBar,
  OperatorBar, OperatorCycleList, ProductBar, SerialsByProductList, TopToolsList, ReviewFunnelDonut,
} from "../components/Charts";

function KpiTile({ icon: Icon, label, value, hint, tint, tone = "up" }: {
  icon: typeof ListChecks; label: string; value: string; hint?: string; tint: string;
  tone?: "up" | "warn" | "plain";
}) {
  const chip =
    tone === "warn" ? "badge-rose"
    : tone === "plain" ? "badge-slate"
    : "badge-emerald";
  return (
    <div className="card card-hover kpi-gradient group relative overflow-hidden p-5">
      <div className="flex items-start justify-between">
        <div className={`flex h-11 w-11 items-center justify-center rounded-2xl text-white shadow-soft ${tint}`}>
          <Icon size={19} />
        </div>
        {hint && (
          <span className={`badge ${chip}`}>
            {tone === "up" && <ArrowUpRight size={12} />} {hint}
          </span>
        )}
      </div>
      <p className="mt-4 text-[28px] font-bold leading-none tracking-tight text-slate-800 tabular-nums">{value}</p>
      <p className="mt-1.5 text-sm font-medium text-slate-400">{label}</p>
      <div className="pointer-events-none absolute -right-7 -bottom-9 h-24 w-24 rounded-full bg-agilink-500/[0.05] transition-transform duration-300 group-hover:scale-125" />
    </div>
  );
}

function SectionTitle({ index, children, hint }: { index: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="mt-3 flex items-center gap-3">
      <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-agilink-50 text-[11px] font-bold text-agilink-700 ring-1 ring-inset ring-agilink-100">
        {index}
      </span>
      <h3 className="text-[13px] font-bold uppercase tracking-[0.14em] text-slate-600">{children}</h3>
      {hint && <span className="hidden text-xs text-slate-400 md:inline">· {hint}</span>}
      <div className="ml-1 h-px flex-1 bg-gradient-to-r from-slate-200/80 to-transparent" />
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [a, setA] = useState<Analytics | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      Promise.all([api.stats(), api.analytics()]).then(([s, an]) => { setStats(s); setA(an); }).catch((e) => setErr(String(e)));
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  if (err) return <div className="text-rose-600">Erreur: {err}</div>;
  if (!stats || !a) return <Spinner />;
  const k = a.kpis;
  const today = new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  const done = a.operation_coverage.find((d) => d.name === "Réalisées")?.value ?? 0;
  const covTotal = a.operation_coverage.reduce((s, d) => s + d.value, 0);
  const coveragePct = covTotal ? Math.round((100 * done) / covTotal) : null;

  return (
    <div className="animate-fade-in space-y-5">
      {/* Page sub-header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Intelligence opérationnelle</p>
          <h2 className="text-xl font-bold tracking-tight text-slate-800">Analyse des données extraites</h2>
          <p className="mt-0.5 text-sm capitalize text-slate-400">{today}</p>
        </div>
        <Link to="/scanner" className="btn-primary">
          <ScanLine size={17} /> Scanner une fiche
        </Link>
      </div>

      {a.scope.validated === 0 ? (
        <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center text-slate-400">
          <Database size={36} className="text-slate-300" />
          <p className="max-w-md text-sm">
            Les indicateurs s'appuient sur les <strong>fiches validées</strong> — la donnée confirmée par un opérateur.
            Aucune fiche n'est encore validée&nbsp;: validez des fiches depuis l'
            <Link to="/historique" className="font-semibold text-agilink-600 hover:underline">historique</Link> pour
            alimenter l'analyse.
          </p>
          <span className="text-xs text-slate-400">{a.scope.total_fiches} fiche(s) en base, {a.review_funnel.find((f) => f.name === "En revue")?.value ?? 0} en attente de revue.</span>
        </div>
      ) : (
        <>
          {/* KPI tiles — extracted-data content, not file counts */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <KpiTile icon={ListChecks} label="Opérations réalisées" value={String(k.operations_done)} tint="bg-brand" />
            <KpiTile
              icon={ShieldCheck} label="Conformité contrôles"
              value={k.conformity_pct != null ? `${k.conformity_pct}%` : "—"}
              tint="bg-gradient-to-br from-emerald-500 to-teal-600"
            />
            <KpiTile
              icon={Timer} label="Temps de cycle moyen"
              value={k.cycle_time_minutes != null ? `${k.cycle_time_minutes} min` : "—"}
              hint={k.cycle_time_minutes != null ? `${k.cycle_time_coverage_pct}% des relevés` : undefined} tone="plain"
              tint="bg-gradient-to-br from-amber-500 to-orange-600"
            />
            <KpiTile
              icon={TriangleAlert} label="Non-conformités"
              value={String(k.non_conformities)}
              hint={k.flagged_rows ? `${k.flagged_rows} à revoir` : undefined} tone="warn"
              tint="bg-gradient-to-br from-rose-500 to-red-600"
            />
            <KpiTile icon={Users} label="Opérateurs actifs" value={String(k.operators)} tint="bg-gradient-to-br from-violet-500 to-purple-600" />
          </div>

          {/* Hero: quality gauges + throughput timeline */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ChartCard title="Indicateurs qualité" subtitle={`Basé sur ${a.scope.validated} fiche(s) validée(s) / ${a.scope.total_fiches}`}>
              <div className="flex flex-wrap items-center justify-around gap-y-3 py-3">
                <Gauge value={coveragePct} color="#0e5b75" label="Couverture" />
                <Gauge value={k.conformity_pct} color="#10b981" label="Conformité" />
                <Gauge value={k.automation_pct} color="#a855f7" label="Automatisation" />
              </div>
            </ChartCard>
            <div className="lg:col-span-2">
              <TimelineBar a={a} />
            </div>
          </div>

          {/* 1. Conformity & defects */}
          <SectionTitle index="1" hint="contrôles électriques, finaux et correspondance série">Conformité &amp; défauts</SectionTitle>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ConformityDonut a={a} />
            <ControlResultsByType a={a} />
            <NonConformitiesByProduct a={a} />
          </div>

          {/* 2. Operation flow & bottlenecks */}
          <SectionTitle index="2" hint="couverture de la gamme et temps de cycle">Flux opératoire &amp; goulots</SectionTitle>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <CoverageDonut a={a} />
            <CoverageByOperationList a={a} />
            <CycleTimeList a={a} />
          </div>

          {/* 3. Operator performance */}
          <SectionTitle index="3" hint="charge et cadence par matricule">Performance opérateurs</SectionTitle>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <OperatorBar a={a} />
            </div>
            <OperatorCycleList a={a} />
          </div>

          {/* 4. Quantity & traceability */}
          <SectionTitle index="4" hint="volumes, numéros de série et outillages">Quantité &amp; traçabilité</SectionTitle>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ProductBar a={a} />
            <SerialsByProductList a={a} />
            <TopToolsList a={a} />
          </div>
        </>
      )}

      {/* Process funnel + recent fiches */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ReviewFunnelDonut a={a} />
        <div className="card overflow-hidden lg:col-span-2">
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
    </div>
  );
}
