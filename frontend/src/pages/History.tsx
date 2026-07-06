import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, ChevronLeft, ChevronRight, Inbox, SlidersHorizontal, Trash2, Archive, ArchiveRestore, X } from "lucide-react";
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
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [showArchived, setShowArchived] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      api
        .fiches({
          q,
          statut,
          date_from: dateFrom ? `${dateFrom}T00:00:00` : undefined,
          date_to: dateTo ? `${dateTo}T23:59:59` : undefined,
          archived: showArchived ? "true" : undefined,
          page,
          page_size: PAGE_SIZE,
        })
        .then(setData)
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q, dateFrom, dateTo, statut, page, showArchived, refresh]);

  useEffect(() => { setPage(1); setSelected(new Set()); }, [q, dateFrom, dateTo, statut, showArchived]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const items = data?.items ?? [];
  const allSelected = items.length > 0 && items.every((f) => selected.has(f.fiche_id));

  function toggle(id: number) {
    setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function toggleAll() {
    setSelected((s) => (allSelected ? new Set() : new Set(items.map((f) => f.fiche_id))));
  }

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try { await fn(); setSelected(new Set()); setRefresh((r) => r + 1); }
    catch (e) { alert(String(e instanceof Error ? e.message : e)); }
    setBusy(false);
  }

  const ids = [...selected];

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Archives</p>
          <h2 className="text-xl font-bold tracking-tight text-slate-800">Historique des fiches</h2>
          <p className="mt-0.5 text-sm text-slate-400">
            {data ? `${data.total} fiche${data.total > 1 ? "s" : ""} ${showArchived ? "archivée" : "enregistrée"}${data.total > 1 ? "s" : ""}` : "Chargement…"}
          </p>
        </div>
        <button
          onClick={() => setShowArchived((v) => !v)}
          className={`btn-ghost ${showArchived ? "text-brand ring-1 ring-brand/20" : ""}`}
        >
          {showArchived ? <><ArchiveRestore size={16} /> Voir les actives</> : <><Archive size={16} /> Voir les archives</>}
        </button>
      </div>

      {/* Filter bar */}
      <div className="card p-4">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <SlidersHorizontal size={14} /> Filtres
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_auto_auto]">
          <div className="relative">
            <Search size={17} className="pointer-events-none absolute left-3.5 top-3 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher par réf. produit ou N° OF…" className="input pl-10" />
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

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-brand/5 px-4 py-3 ring-1 ring-brand/10">
          <span className="flex items-center gap-2 text-sm font-semibold text-brand">
            <button onClick={() => setSelected(new Set())} className="rounded-md p-0.5 hover:bg-brand/10"><X size={15} /></button>
            {selected.size} sélectionnée{selected.size > 1 ? "s" : ""}
          </span>
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => run(() => api.bulkArchiveFiches(ids, !showArchived))} className="btn-soft btn-sm">
              {showArchived ? <><ArchiveRestore size={15} /> Restaurer</> : <><Archive size={15} /> Archiver</>}
            </button>
            <button disabled={busy} onClick={() => { if (confirm(`Supprimer définitivement ${selected.size} fiche(s) ?`)) run(() => api.bulkDeleteFiches(ids)); }} className="btn-danger btn-sm">
              <Trash2 size={15} /> Supprimer
            </button>
          </div>
        </div>
      )}

      {/* Results */}
      <div className="card overflow-hidden">
        {loading && !data ? (
          <Spinner />
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-slate-400">
            <Inbox size={32} />
            {showArchived ? "Aucune fiche archivée." : "Aucune fiche ne correspond à ces critères."}
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wider text-slate-400">
                  <th className="w-10 px-4 py-3">
                    <input type="checkbox" checked={allSelected} onChange={toggleAll} className="h-4 w-4 cursor-pointer rounded border-slate-300 text-brand focus:ring-brand/30" />
                  </th>
                  <th className="px-5 py-3 font-medium">Réf. Produit</th>
                  <th className="px-5 py-3 font-medium">Désignation</th>
                  <th className="px-5 py-3 font-medium">N° OF</th>
                  <th className="px-5 py-3 font-medium">Qté</th>
                  <th className="px-5 py-3 font-medium">Date</th>
                  <th className="px-5 py-3 font-medium">Confiance</th>
                  <th className="px-5 py-3 font-medium">Statut</th>
                  <th className="w-12 px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {items.map((f) => (
                  <tr key={f.fiche_id} className={`transition-colors hover:bg-agilink-50/40 ${selected.has(f.fiche_id) ? "bg-brand/5" : ""}`}>
                    <td className="px-4 py-3.5">
                      <input type="checkbox" checked={selected.has(f.fiche_id)} onChange={() => toggle(f.fiche_id)} className="h-4 w-4 cursor-pointer rounded border-slate-300 text-brand focus:ring-brand/30" />
                    </td>
                    <td className="px-5 py-3.5">
                      <Link to={`/fiches/${f.fiche_id}`} className="font-semibold text-agilink-700 hover:underline">{f.ref_produit}</Link>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500">{f.designation || "—"}</td>
                    <td className="px-5 py-3.5 text-slate-600">{f.n_of}</td>
                    <td className="px-5 py-3.5 tabular-nums text-slate-600">{f.quantite ?? "—"}</td>
                    <td className="px-5 py-3.5 text-slate-500">{fmtDateTime(f.date_creation)}</td>
                    <td className="px-5 py-3.5"><ConfidenceBadge value={f.overall_confidence} /></td>
                    <td className="px-5 py-3.5"><StatutBadge statut={f.statut} auto={f.auto_validated} /></td>
                    <td className="px-4 py-3.5">
                      <button
                        title="Supprimer cette fiche"
                        disabled={busy}
                        onClick={() => { if (confirm(`Supprimer la fiche ${f.ref_produit} ?`)) run(() => api.deleteFiche(f.fiche_id)); }}
                        className="rounded-lg p-1.5 text-slate-300 transition hover:bg-rose-50 hover:text-rose-500"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
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
