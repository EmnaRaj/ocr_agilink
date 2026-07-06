import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, ChevronLeft, ChevronRight, Inbox, SlidersHorizontal, FileSearch, Rows3, Table2 } from "lucide-react";
import { api, type OperationListResponse, type OperationMatrixResponse, type OperationMatrixCell } from "../api";
import { Spinner } from "../ui";

const PAGE_SIZE = 25;

const PARTIE_LABEL: Record<string, string> = { "1": "Partie 1", "2": "Partie 2", controle: "Contrôle" };
const PARTIE_BADGE: Record<string, { txt: string; cls: string }> = {
  "1": { txt: "P1", cls: "bg-sky-100 text-sky-700" },
  "2": { txt: "P2", cls: "bg-teal-100 text-teal-700" },
  controle: { txt: "C", cls: "bg-amber-100 text-amber-700" },
};

// Compact column headers for the matrix — the full names are very long.
const SHORT_OP: Record<string, string> = {
  "Dégainage": "Dégainage",
  "Soudure et/ou Auto-Soudeur": "Soudure",
  "Dénudage Fil": "Dénudage",
  "Sertissage": "Sertissage",
  "Enfichage": "Enfichage",
  "Rétention": "Rétention",
  "Serrage des raccords arrières": "Serrage raccords",
  "Serrage capots": "Serrage capots",
  "Serrage des colliers Band'it, Tinel-Lock,..": "Serrage colliers",
  "Raccordement reprise de blindage (nœud de frette)": "Reprise blindage",
  "Passage des gaines, tresses, marquages, accessoires, / Retreint": "Passage gaines",
  "Ajustement": "Ajustement",
  "Test électrique avant surmoulage": "Test élec.",
  "Potting / surmoulage": "Potting",
  "Finition (pièce moulée -marquage -gaine ..)": "Finition",
  "Contrôle électrique": "Ctrl élec.",
  "Contrôle final": "Ctrl final",
  "Le numéro de série sur le rapport de test électrique correspond au numéro de série du produit.": "Corresp. série",
};
const short = (nom: string) => SHORT_OP[nom] ?? (nom.length > 16 ? nom.slice(0, 15) + "…" : nom);

function ApplicableBadge({ applicable }: { applicable: boolean | null }) {
  if (applicable === null) return <span className="text-slate-300">—</span>;
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${applicable ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
      {applicable ? "Oui" : "Non"}
    </span>
  );
}

function MatrixCell({ c }: { c?: OperationMatrixCell }) {
  if (!c) return <span className="text-slate-300">—</span>;
  if (c.applicable === false) return <span className="text-slate-400">Non</span>;
  const times = c.heure_debut && c.heure_fin ? `${c.heure_debut}–${c.heure_fin}` : c.heure_debut || "";
  return (
    <span className="whitespace-nowrap text-slate-700" title={c.matricule ? `Matricule ${c.matricule}` : undefined}>
      <span className="font-medium text-emerald-700">Oui</span>
      {times && <span className="text-slate-400"> ({times})</span>}
    </span>
  );
}

function Pager({ page, totalPages, setPage }: { page: number; totalPages: number; setPage: (f: (p: number) => number) => void }) {
  return (
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
  );
}

export default function Operations() {
  const [view, setView] = useState<"list" | "matrix">("matrix");
  const [q, setQ] = useState("");
  const [nOf, setNOf] = useState("");
  const [matricule, setMatricule] = useState("");
  const [partie, setPartie] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OperationListResponse | null>(null);
  const [matrix, setMatrix] = useState<OperationMatrixResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      if (view === "list") {
        api.operations({ q, n_of: nOf, matricule, partie, page, page_size: PAGE_SIZE }).then(setData).finally(() => setLoading(false));
      } else {
        api.operationsMatrix({ q, n_of: nOf, page, page_size: PAGE_SIZE }).then(setMatrix).finally(() => setLoading(false));
      }
    }, 250);
    return () => clearTimeout(t);
  }, [view, q, nOf, matricule, partie, page]);

  useEffect(() => setPage(1), [view, q, nOf, matricule, partie]);

  const total = view === "list" ? data?.total : matrix?.total;
  const totalPages = total != null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : 1;

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Base de données</p>
          <h2 className="text-xl font-bold tracking-tight text-slate-800">
            {view === "matrix" ? "Données par fiche" : "Toutes les opérations"}
          </h2>
          <p className="mt-0.5 text-sm text-slate-400">
            {total != null
              ? view === "matrix"
                ? `${total} fiche${total > 1 ? "s" : ""} validée${total > 1 ? "s" : ""}`
                : `${total} opération${total > 1 ? "s" : ""} sur fiches validées`
              : "Chargement…"}
          </p>
        </div>
        {/* View toggle */}
        <div className="segmented">
          <button onClick={() => setView("matrix")} className={`seg-item ${view === "matrix" ? "seg-item-active" : ""}`}>
            <Table2 size={15} /> Par fiche
          </button>
          <button onClick={() => setView("list")} className={`seg-item ${view === "list" ? "seg-item-active" : ""}`}>
            <Rows3 size={15} /> Par opération
          </button>
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
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher par réf. produit ou N° OF…" className="input pl-10" />
          </div>
          <input value={nOf} onChange={(e) => setNOf(e.target.value)} placeholder="N° OF" className="input md:w-36" />
          {view === "list" && (
            <>
              <input value={matricule} onChange={(e) => setMatricule(e.target.value)} placeholder="Matricule opérateur" className="input md:w-40" />
              <select value={partie} onChange={(e) => setPartie(e.target.value)} className="input md:w-auto">
                <option value="">Toutes les parties</option>
                <option value="1">Partie 1</option>
                <option value="2">Partie 2</option>
                <option value="controle">Contrôle</option>
              </select>
            </>
          )}
        </div>
      </div>

      {/* Results */}
      <div className="card overflow-hidden">
        {loading && !data && !matrix ? (
          <Spinner />
        ) : view === "matrix" ? (
          !matrix || matrix.rows.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-16 text-slate-400">
              <Inbox size={32} /> Aucune fiche validée ne correspond à ces critères.
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wider text-slate-400">
                      <th className="sticky left-0 z-10 bg-white px-4 py-3 font-medium">Fiche</th>
                      {matrix.columns.map((col) => {
                        const b = PARTIE_BADGE[col.partie];
                        return (
                          <th key={col.key} className="border-l border-slate-50 px-3 py-2 font-medium align-bottom">
                            <div className="flex flex-col items-start gap-1">
                              <span className={`rounded px-1 text-[9px] font-bold ${b.cls}`}>{b.txt}</span>
                              <span title={col.nom_operation} className="whitespace-nowrap text-[11px] normal-case text-slate-500">{short(col.nom_operation)}</span>
                            </div>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {matrix.rows.map((r) => (
                      <tr key={r.fiche_id} className="transition-colors hover:bg-agilink-50/40">
                        <td className="sticky left-0 z-10 bg-white px-4 py-3 group-hover:bg-agilink-50/40">
                          <Link to={`/fiches/${r.fiche_id}`} className="font-semibold text-agilink-700 hover:underline">{r.ref_produit}</Link>
                          <div className="text-xs text-slate-400">OF {r.n_of} · Qté {r.qte ?? "—"}</div>
                        </td>
                        {matrix.columns.map((col) => (
                          <td key={col.key} className="border-l border-slate-50 px-3 py-3 text-xs">
                            <MatrixCell c={r.cells[col.key]} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager page={page} totalPages={totalPages} setPage={setPage} />
            </>
          )
        ) : !data || data.items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-slate-400">
            <Inbox size={32} /> Aucune opération ne correspond à ces critères.
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wider text-slate-400">
                  <th className="px-5 py-3 font-medium">Réf. Produit</th>
                  <th className="px-5 py-3 font-medium">N° OF</th>
                  <th className="px-5 py-3 font-medium">Opération</th>
                  <th className="px-5 py-3 font-medium">Appliquée</th>
                  <th className="px-5 py-3 font-medium">Date</th>
                  <th className="px-5 py-3 font-medium">Horaire</th>
                  <th className="px-5 py-3 font-medium">Qté</th>
                  <th className="px-5 py-3 font-medium">Outillage</th>
                  <th className="px-5 py-3 font-medium">Opérateur</th>
                  <th className="px-5 py-3 font-medium">Fiche</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data.items.map((o) => (
                  <tr key={o.operation_id} className="transition-colors hover:bg-agilink-50/40">
                    <td className="px-5 py-3.5">
                      <Link to={`/fiches/${o.fiche_id}`} className="font-semibold text-agilink-700 hover:underline">{o.ref_produit}</Link>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">{o.n_of}</td>
                    <td className="px-5 py-3.5">
                      <div className="text-slate-700">{o.nom_operation}</div>
                      <div className="text-xs text-slate-400">{PARTIE_LABEL[o.partie] ?? o.partie}</div>
                    </td>
                    <td className="px-5 py-3.5"><ApplicableBadge applicable={o.applicable} /></td>
                    <td className="px-5 py-3.5 text-slate-500">{o.date_op ?? "—"}</td>
                    <td className="px-5 py-3.5 tabular-nums text-slate-600">
                      {o.heure_debut && o.heure_fin ? `${o.heure_debut.slice(0, 5)}–${o.heure_fin.slice(0, 5)}` : o.heure_debut?.slice(0, 5) ?? "—"}
                    </td>
                    <td className="px-5 py-3.5 tabular-nums text-slate-600">{o.qte_realisee ?? "—"}</td>
                    <td className="px-5 py-3.5 text-slate-500">{o.outillage ?? "—"}</td>
                    <td className="px-5 py-3.5 text-slate-500">{o.matricule_operateur ?? "—"}</td>
                    <td className="px-5 py-3.5">
                      <Link to={`/fiches/${o.fiche_id}`} title="Ouvrir le tableau complet de cette fiche" className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-agilink-700 transition hover:border-agilink-300 hover:bg-agilink-50">
                        <FileSearch size={14} /> Voir
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={page} totalPages={totalPages} setPage={setPage} />
          </>
        )}
      </div>
    </div>
  );
}
