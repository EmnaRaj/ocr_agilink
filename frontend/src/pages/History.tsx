import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, ChevronLeft, ChevronRight, Inbox, SlidersHorizontal } from "lucide-react";
import { api, type FicheListResponse } from "../api";
import { ConfidenceBadge, StatutBadge, Spinner, fmtDateTime } from "../ui";

const PAGE_SIZE = 15;

export default function History() {
  const [q, setQ] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [statut, setStatut] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<FicheListResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      api
        .fiches({
          q,
          statut,
          date_from: dateFrom ? `${dateFrom}T00:00:00` : undefined,
          date_to: dateTo ? `${dateTo}T23:59:59` : undefined,
          page,
          page_size: PAGE_SIZE,
        })
        .then(setData)
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q, dateFrom, dateTo, statut, page]);

  useEffect(() => setPage(1), [q, dateFrom, dateTo, statut]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Archives</p>
          <h2 className="text-xl font-bold tracking-tight text-slate-800">Historique des fiches</h2>
          <p className="mt-0.5 text-sm text-slate-400">
            {data ? `${data.total} fiche${data.total > 1 ? "s" : ""} enregistrée${data.total > 1 ? "s" : ""}` : "Chargement…"}
          </p>
        </div>
      </div>

      {/* Filter bar */}
      <div className="card p-4">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <SlidersHorizontal size={14} /> Filtres
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_auto_auto]">
          <div className="relative">
            <Search size={17} className="pointer-events-none absolute left-3.5 top-3 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Rechercher par réf. produit ou N° OF…"
              className="input pl-10"
            />
          </div>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input md:w-auto" title="Date début" />
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input md:w-auto" title="Date fin" />
          <select value={statut} onChange={(e) => setStatut(e.target.value)} className="input md:w-auto">
            <option value="">Tous les statuts</option>
            <option value="extrait">Extrait</option>
            <option value="en_revue">En revue</option>
            <option value="valide">Validé</option>
          </select>
        </div>
      </div>

      {/* Results */}
      <div className="card overflow-hidden">
        {loading && !data ? (
          <Spinner />
        ) : data && data.items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-slate-400">
            <Inbox size={32} />
            Aucune fiche ne correspond à ces critères.
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wider text-slate-400">
                  <th className="px-5 py-3 font-medium">Réf. Produit</th>
                  <th className="px-5 py-3 font-medium">Désignation</th>
                  <th className="px-5 py-3 font-medium">N° OF</th>
                  <th className="px-5 py-3 font-medium">Qté</th>
                  <th className="px-5 py-3 font-medium">Date</th>
                  <th className="px-5 py-3 font-medium">Confiance</th>
                  <th className="px-5 py-3 font-medium">Statut</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data?.items.map((f) => (
                  <tr key={f.fiche_id} className="transition-colors hover:bg-agilink-50/40">
                    <td className="px-5 py-3.5">
                      <Link to={`/fiches/${f.fiche_id}`} className="font-semibold text-agilink-700 hover:underline">
                        {f.ref_produit}
                      </Link>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500">{f.designation || "—"}</td>
                    <td className="px-5 py-3.5 text-slate-600">{f.n_of}</td>
                    <td className="px-5 py-3.5 tabular-nums text-slate-600">{f.quantite ?? "—"}</td>
                    <td className="px-5 py-3.5 text-slate-500">{fmtDateTime(f.date_creation)}</td>
                    <td className="px-5 py-3.5"><ConfidenceBadge value={f.overall_confidence} /></td>
                    <td className="px-5 py-3.5"><StatutBadge statut={f.statut} /></td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="flex items-center justify-between border-t border-slate-100 px-5 py-3 text-sm text-slate-500">
              <span>page {page}/{totalPages}</span>
              <div className="flex gap-1.5">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="rounded-lg border border-slate-200 p-1.5 transition hover:bg-slate-50 disabled:opacity-40">
                  <ChevronLeft size={16} />
                </button>
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="rounded-lg border border-slate-200 p-1.5 transition hover:bg-slate-50 disabled:opacity-40">
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
