import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft, Cpu, Clock, Hash, FileSpreadsheet, FileText, FileDown,
  Pencil, Check, X, ShieldCheck, Loader2,
} from "lucide-react";
import { api, type FicheDetail as Detail, type Extraction, type OperationRow, type ControlRow } from "../api";
import { ConfidenceBadge, StatutBadge, FieldCell, Spinner, fmtDateTime } from "../ui";

const OP_COLS = ["#", "Opération", "Appl.", "Date", "Qté", "Début", "Fin", "Outillage", "Matricule"];
const inputCls =
  "w-full min-w-[64px] rounded-md border border-slate-300 bg-white px-2 py-1.5 text-[13px] text-slate-700 focus:border-agilink-500 focus:outline-none focus:ring-1 focus:ring-agilink-500";

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

export default function FicheDetail() {
  const { id } = useParams();
  const [d, setD] = useState<Detail | null>(null);
  const [draft, setDraft] = useState<Extraction | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => id && api.fiche(Number(id)).then(setD).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, [id]); // eslint-disable-line

  if (err) return <div className="text-rose-600">Erreur: {err}</div>;
  if (!d) return <Spinner />;

  const editing = draft !== null;
  const ex = editing ? draft! : d.extraction;
  const validated = d.statut === "valide";

  // --- editing helpers ---
  const setHeader = (k: string, value: unknown) =>
    setDraft((p) => p && { ...p, header: { ...p.header, [k]: { ...(p.header as any)[k], value, confidence: 1, source: "human" } } });

  const setOp = (i: number, field: string, patch: object) =>
    setDraft((p) => p && {
      ...p,
      operations: p.operations.map((o, idx) =>
        idx === i ? { ...o, [field]: { ...(o as any)[field], ...patch, confidence: 1, source: "human" } } : o
      ) as any,
    });

  const setCtrl = (i: number, field: string, patch: object) =>
    setDraft((p) => p && {
      ...p,
      controls: p.controls.map((c, idx) =>
        idx === i ? { ...c, [field]: { ...(c as any)[field], ...patch, confidence: 1, source: "human" } } : c
      ) as any,
    });

  async function save(doValidate: boolean) {
    if (!draft) return;
    setSaving(true);
    try {
      await api.updateFiche(d!.fiche_id, draft, doValidate);
      setDraft(null);
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  }

  const p1 = ex?.operations.map((o, i) => ({ o, i })).filter((x) => x.o.partie === "1") ?? [];
  const p2 = ex?.operations.map((o, i) => ({ o, i })).filter((x) => x.o.partie === "2") ?? [];
  const headerRef = ex?.header.ref_produit.value ?? d.product.ref_produit;

  return (
    <div className="animate-fade-in space-y-5">
      <Link to="/historique" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-agilink-600">
        <ArrowLeft size={16} /> Retour à l'historique
      </Link>

      {/* Summary bar */}
      <div className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-slate-800">{String(headerRef)}</h2>
              <StatutBadge statut={d.statut} />
              {!validated && <ConfidenceBadge value={d.overall_confidence} />}
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {d.product.designation || "Sans désignation"} · OF {d.work_order.n_of} · Qté {ex?.header.qte.value ?? d.work_order.quantite ?? "—"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            {!editing ? (
              <div className="flex items-center gap-2">
                <button onClick={() => setDraft(clone(d!.extraction!))} className="inline-flex items-center gap-1.5 rounded-lg border border-agilink-200 bg-agilink-50 px-3 py-1.5 text-xs font-semibold text-agilink-700 hover:bg-agilink-100">
                  <Pencil size={14} /> Modifier
                </button>
                <a href={api.exportUrl(d.fiche_id, "xlsx")} className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-100"><FileSpreadsheet size={14} /> Excel</a>
                <a href={api.exportUrl(d.fiche_id, "pdf")} className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100"><FileText size={14} /> PDF</a>
                <a href={api.exportUrl(d.fiche_id, "csv")} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100"><FileDown size={14} /> CSV</a>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button onClick={() => setDraft(null)} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50"><X size={14} /> Annuler</button>
                <button onClick={() => save(false)} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">Enregistrer</button>
                <button onClick={() => save(true)} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-soft hover:bg-emerald-700">
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />} Valider
                </button>
              </div>
            )}
            {!editing && (
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span className="flex items-center gap-1"><Clock size={13} /> {fmtDateTime(d.date_creation)}</span>
                {ex?.meta && <span className="flex items-center gap-1"><Cpu size={13} /> {ex.meta.model_name.split("/").pop()}</span>}
                {ex?.meta?.processing_ms && <span className="flex items-center gap-1"><Hash size={13} /> {(ex.meta.processing_ms / 1000).toFixed(1)} s</span>}
              </div>
            )}
          </div>
        </div>
        {validated && !editing && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">
            <ShieldCheck size={15} /> Fiche validée et confirmée par un opérateur — données fiables.
          </div>
        )}
        {editing && (
          <div className="mt-3 rounded-lg bg-agilink-50 px-3 py-2 text-xs text-agilink-700">
            Mode édition : corrigez les valeurs lues, puis <b>Valider</b> pour confirmer la fiche.
          </div>
        )}
      </div>

      {/* Scan + data */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <div className="card p-3 xl:sticky xl:top-0 xl:self-start">
          <div className="mb-2 px-2 text-sm font-semibold text-slate-700">Document scanné</div>
          {d.scan ? (
            <a href={api.scanUrl(d.fiche_id)} target="_blank" rel="noreferrer">
              <img src={api.scanUrl(d.fiche_id)} alt="Fiche scannée" className="w-full rounded-lg border border-slate-100" />
            </a>
          ) : <div className="py-16 text-center text-slate-400">Aucun scan disponible</div>}
        </div>

        <div className="space-y-5">
          {ex ? (
            <>
              <div className="card p-4">
                <div className="mb-3 text-sm font-semibold text-slate-700">En-tête</div>
                <div className="grid grid-cols-2 gap-2">
                  {([["ref_produit", "Réf. Produit"], ["n_of", "N° OF"], ["qte", "Quantité"], ["annotation_serie", "Annotation série"]] as const).map(([k, lbl]) => (
                    <div key={k} className="rounded-lg bg-slate-50 px-3 py-2">
                      <div className="text-[11px] uppercase tracking-wide text-slate-400">{lbl}</div>
                      {editing ? (
                        <input className={inputCls} value={String((ex.header as any)[k]?.value ?? "")} onChange={(e) => setHeader(k, e.target.value)} />
                      ) : (
                        <div className="mt-0.5 font-semibold text-slate-800"><FieldCell value={(ex.header as any)[k]?.value} confidence={(ex.header as any)[k]?.confidence} /></div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="card space-y-4 p-4">
                {[{ title: "Opérations — Partie 1", rows: p1 }, { title: "Opérations — Partie 2", rows: p2 }].map(({ title, rows }) => (
                  <div key={title}>
                    <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-agilink-700">{title}</h3>
                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                      <table className={`w-full text-xs ${editing ? "min-w-[760px]" : ""}`}>
                        <thead className="bg-slate-50 text-slate-400">
                          <tr>{OP_COLS.map((c) => <th key={c} className="px-2 py-2 text-left font-medium">{c}</th>)}</tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {rows.map(({ o, i }) => <OpRow key={i} o={o} idx={i} editing={editing} setOp={setOp} />)}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}

                <div>
                  <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-agilink-700">Contrôles</h3>
                  <div className="overflow-hidden rounded-lg border border-slate-200">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 text-slate-400">
                        <tr>{["Contrôle", "Résultat", "Matricule"].map((c) => <th key={c} className="px-2 py-2 text-left font-medium">{c}</th>)}</tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {ex.controls.map((c, i) => <CtrlRow key={i} c={c} idx={i} editing={editing} setCtrl={setCtrl} />)}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {!editing && !validated && d.validation?.length > 0 && (
                <div className="card p-4">
                  <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
                    <span className="text-amber-500">⚠</span> Contrôles de cohérence — {d.validation.length} point(s) à vérifier
                  </h3>
                  <ul className="space-y-1.5">
                    {d.validation.map((v, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs">
                        <span className={`mt-0.5 inline-flex shrink-0 rounded px-1.5 py-0.5 font-semibold ${v.level === "error" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}`}>{v.level === "error" ? "Erreur" : "Alerte"}</span>
                        <span className="text-slate-600">{v.message}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : <div className="card p-8 text-center text-slate-400">Aucune donnée d'extraction.</div>}
        </div>
      </div>
    </div>
  );
}

function applSel(v: boolean | null) {
  return v === true ? "Oui" : v === false ? "Non" : "—";
}

function OpRow({ o, idx, editing, setOp }: { o: OperationRow; idx: number; editing: boolean; setOp: (i: number, f: string, p: object) => void }) {
  if (!editing) {
    const blank = o.applicable.value === null && !o.matricule_operateur.value && !o.date_op.raw_text;
    return (
      <tr className={blank ? "text-slate-300" : "hover:bg-slate-50"}>
        <td className="px-2 py-1.5 tabular-nums text-slate-400">{o.ordre}</td>
        <td className="px-2 py-1.5 text-slate-600">{o.nom_operation}</td>
        <td className="px-2 py-1.5"><FieldCell value={o.applicable.value} confidence={o.applicable.confidence} /></td>
        <td className="px-2 py-1.5"><FieldCell value={o.date_op.value} confidence={o.date_op.confidence} raw={o.date_op.raw_text} /></td>
        <td className="px-2 py-1.5 tabular-nums"><FieldCell value={o.qte_realisee.value} confidence={o.qte_realisee.confidence} /></td>
        <td className="px-2 py-1.5 tabular-nums"><FieldCell value={o.heure_debut.value} confidence={o.heure_debut.confidence} /></td>
        <td className="px-2 py-1.5 tabular-nums"><FieldCell value={o.heure_fin.value} confidence={o.heure_fin.confidence} /></td>
        <td className="px-2 py-1.5"><FieldCell value={o.outillage.value} confidence={o.outillage.confidence} /></td>
        <td className="px-2 py-1.5 font-medium"><FieldCell value={o.matricule_operateur.value} confidence={o.matricule_operateur.confidence} /></td>
      </tr>
    );
  }
  const i = (cls = inputCls) => cls;
  return (
    <tr>
      <td className="px-2 py-1 tabular-nums text-slate-400">{o.ordre}</td>
      <td className="px-2 py-1 text-slate-600">{o.nom_operation}</td>
      <td className="px-2 py-1">
        <select className={i()} value={applSel(o.applicable.value)} onChange={(e) => setOp(idx, "applicable", { value: e.target.value === "Oui" ? true : e.target.value === "Non" ? false : null })}>
          <option>—</option><option>Oui</option><option>Non</option>
        </select>
      </td>
      <td className="px-2 py-1"><input className={i()} value={o.date_op.raw_text ?? (o.date_op.value as any) ?? ""} onChange={(e) => setOp(idx, "date_op", { value: null, raw_text: e.target.value })} /></td>
      <td className="px-2 py-1"><input className={i()} value={(o.qte_realisee.value as any) ?? ""} onChange={(e) => setOp(idx, "qte_realisee", { value: e.target.value === "" ? null : Number(e.target.value) })} /></td>
      <td className="px-2 py-1"><input className={i()} value={(o.heure_debut.value as any) ?? ""} onChange={(e) => setOp(idx, "heure_debut", { value: e.target.value || null })} /></td>
      <td className="px-2 py-1"><input className={i()} value={(o.heure_fin.value as any) ?? ""} onChange={(e) => setOp(idx, "heure_fin", { value: e.target.value || null })} /></td>
      <td className="px-2 py-1"><input className={i()} value={(o.outillage.value as any) ?? ""} onChange={(e) => setOp(idx, "outillage", { value: e.target.value || null })} /></td>
      <td className="px-2 py-1"><input className={i()} value={(o.matricule_operateur.value as any) ?? ""} onChange={(e) => setOp(idx, "matricule_operateur", { value: e.target.value || null })} /></td>
    </tr>
  );
}

function CtrlRow({ c, idx, editing, setCtrl }: { c: ControlRow; idx: number; editing: boolean; setCtrl: (i: number, f: string, p: object) => void }) {
  const resTxt = c.resultat.value === true ? "Conforme" : c.resultat.value === false ? "Non conforme" : "—";
  if (!editing) {
    return (
      <tr className="hover:bg-slate-50">
        <td className="px-2 py-1.5 text-slate-600">{c.nom_operation}</td>
        <td className="px-2 py-1.5">{c.resultat.value === null ? <span className="text-slate-300">—</span> : <span className={`rounded px-1.5 py-0.5 font-medium ${c.resultat.value ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>{resTxt}</span>}</td>
        <td className="px-2 py-1.5 font-medium"><FieldCell value={c.matricule_operateur.value} confidence={c.matricule_operateur.confidence} /></td>
      </tr>
    );
  }
  return (
    <tr>
      <td className="px-2 py-1 text-slate-600">{c.nom_operation}</td>
      <td className="px-2 py-1">
        <select className={inputCls} value={resTxt} onChange={(e) => setCtrl(idx, "resultat", { value: e.target.value === "Conforme" ? true : e.target.value === "Non conforme" ? false : null })}>
          <option>—</option><option>Conforme</option><option>Non conforme</option>
        </select>
      </td>
      <td className="px-2 py-1"><input className={inputCls} value={(c.matricule_operateur.value as any) ?? ""} onChange={(e) => setCtrl(idx, "matricule_operateur", { value: e.target.value || null })} /></td>
    </tr>
  );
}
