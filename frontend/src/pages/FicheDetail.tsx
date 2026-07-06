import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useParams, useNavigate, useBlocker, Link } from "react-router-dom";
import {
  ArrowLeft, Cpu, Clock, Hash, FileSpreadsheet, FileText, FileDown,
  Pencil, Check, X, ShieldCheck, Loader2, AlertTriangle, Trash2, Sparkles,
} from "lucide-react";
import { api, type FicheDetail as Detail, type Extraction, type OperationRow, type ControlRow, type ValidationIssue } from "../api";
import { ConfidenceBadge, StatutBadge, FieldCell, Spinner, fmtDateTime } from "../ui";

const OP_COLS = ["#", "Opération", "Appl.", "Date", "Qté", "Début", "Fin", "Outillage", "Matricule"];
const inputCls =
  "w-full min-w-[64px] rounded-md border border-slate-300 bg-white px-2 py-1.5 text-[13px] text-slate-700 focus:border-agilink-500 focus:outline-none focus:ring-1 focus:ring-agilink-500";
const inputHighlightCls = "ring-2 ring-amber-400 border-amber-400";
const cellHighlightCls = "bg-amber-100 ring-1 ring-inset ring-amber-400 rounded";

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

// Mirrors the backend's ValidationIssue.location format (validation.py):
// `${partie}·${nom_operation.slice(0, 24)}` — lets a row find "is this me?"
// without the backend needing to send any extra id.
const rowLoc = (partie: string, nom: string) => `${partie}·${nom.slice(0, 24)}`;

// A hovered/clicked alert resolves to one of these. `loc` is null for a
// header-scope issue (matched by `field` against the en-tête grid key).
type Target = { scope: string; loc: string | null; field: string };
const issueTarget = (v: ValidationIssue): Target => ({
  scope: v.scope,
  loc: v.scope === "header" ? null : v.location,
  field: v.field,
});
const sameTarget = (a: Target | null, b: Target) =>
  !!a && a.scope === b.scope && a.loc === b.loc && a.field === b.field;

// Fields where the same value is expected to repeat across rows (mirrors the
// backend's matricule/qte consistency checks) — correcting one is very likely
// meant to apply to the others sharing the same misread value.
const BULK_FIELDS: Record<string, string> = {
  matricule_operateur: "Matricule Opérateur",
  qte_realisee: "Qté réalisée",
};
type BulkMatch = { scope: "operation" | "control"; idx: number; label: string };
type BulkPrompt = { field: string; fieldLabel: string; oldValue: string; newValue: string; matches: BulkMatch[] };

export default function FicheDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [d, setD] = useState<Detail | null>(null);
  const [draft, setDraft] = useState<Extraction | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Alert ↔ field linking: hover previews, click pins (and scrolls to) the
  // field a "Contrôle de cohérence" alert refers to.
  const [hover, setHover] = useState<Target | null>(null);
  const [pinned, setPinned] = useState<Target | null>(null);
  const active = pinned ?? hover;
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const registerRow = (loc: string, el: HTMLTableRowElement | null) => {
    if (el) rowRefs.current.set(loc, el);
  };

  // Bulk-correction prompt: editing a matricule/qté cell that other rows
  // currently share offers to fix them together instead of cell by cell.
  const [bulk, setBulk] = useState<BulkPrompt | null>(null);
  const [bulkChecked, setBulkChecked] = useState<Set<number>>(new Set());

  // Computed before any early return — hooks below (useBlocker, useEffect)
  // must run on every render regardless of loading state.
  const editing = draft !== null;

  // In-app navigation (sidebar links, "Retour", browser back) while editing:
  // ask save/discard/stay instead of silently losing the draft. Requires the
  // data router set up in App.tsx.
  const blocker = useBlocker(editing);
  // Closing the tab / refreshing / typing a new URL bypasses the router
  // entirely, so it needs the browser's own unload guard too.
  useEffect(() => {
    if (!editing) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [editing]);

  const load = () => id && api.fiche(Number(id)).then(setD).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, [id]); // eslint-disable-line

  const [resolving, setResolving] = useState<string | null>(null);
  const alertKey = (v: ValidationIssue) => [v.scope, v.location, v.field, v.code].join("|");
  async function resolveAlert(key: string, resolved: boolean) {
    if (!d) return;
    setResolving(key);
    try { await api.resolveAlert(d.fiche_id, key, resolved); await load(); }
    catch (e) { setErr(String(e instanceof Error ? e.message : e)); }
    setResolving(null);
  }

  if (err) return <div className="text-rose-600">Erreur: {err}</div>;
  if (!d) return <Spinner />;

  const ex = editing ? draft! : d.extraction;
  const validated = d.statut === "valide";
  const autoValidated = ((d.extraction?.meta as { auto_validated?: boolean } | undefined)?.auto_validated) === true;

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

  // Double-clicking any value while just viewing (not yet in "Modifier" mode)
  // jumps straight into full edit mode — same as clicking "Modifier" — and
  // pins/highlights that value so it's easy to spot among all the now-active
  // inputs.
  function enterEditAt(scope: string, loc: string | null, field: string) {
    if (!editing) setDraft(clone(d!.extraction!));
    setPinned({ scope, loc, field });
  }

  // Other rows (operations + controls, excluding the one just edited) that
  // currently hold `oldValue` for `field` — candidates to fix in the same pass.
  function findDuplicates(field: string, oldValue: string, exclude: { scope: "operation" | "control"; idx: number }): BulkMatch[] {
    if (!draft) return [];
    const matches: BulkMatch[] = [];
    draft.operations.forEach((o, idx) => {
      if (exclude.scope === "operation" && idx === exclude.idx) return;
      const v = (o as any)[field]?.value;
      if (v !== null && v !== undefined && String(v) === oldValue) {
        matches.push({ scope: "operation", idx, label: `Partie ${o.partie} · ${o.nom_operation}` });
      }
    });
    draft.controls.forEach((c, idx) => {
      if (exclude.scope === "control" && idx === exclude.idx) return;
      const v = (c as any)[field]?.value;
      if (v !== null && v !== undefined && String(v) === oldValue) {
        matches.push({ scope: "control", idx, label: `Contrôle · ${c.nom_operation}` });
      }
    });
    return matches;
  }

  // Called once the user actually LEAVES a matricule/qté cell (onBlur), never
  // mid-keystroke — comparing the value when the cell was focused to its
  // final value, so the prompt can't fire while someone's still typing.
  // For fields expected to repeat (matricule, qté), offers to apply the same
  // correction to other rows sharing the old (likely also-misread) value,
  // instead of forcing a cell-by-cell fix.
  function checkBulkOnBlur(scope: "operation" | "control", idx: number, field: string, valueOnFocus: string | null, finalValue: unknown) {
    if (
      !BULK_FIELDS[field] ||
      valueOnFocus === null || valueOnFocus === "" ||
      finalValue === null || finalValue === "" ||
      String(finalValue) === valueOnFocus
    ) return;
    const matches = findDuplicates(field, valueOnFocus, { scope, idx });
    if (matches.length > 0) {
      setBulk({ field, fieldLabel: BULK_FIELDS[field], oldValue: valueOnFocus, newValue: String(finalValue), matches });
      setBulkChecked(new Set(matches.map((_, i) => i)));
    }
  }

  function applyBulk() {
    if (!bulk) return;
    bulk.matches.forEach((m, i) => {
      if (!bulkChecked.has(i)) return;
      const value = bulk.field === "qte_realisee" ? Number(bulk.newValue) : bulk.newValue;
      if (m.scope === "operation") setOp(m.idx, bulk.field, { value });
      else setCtrl(m.idx, bulk.field, { value });
    });
    setBulk(null);
  }

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

  // Validate straight from the read-only view when the extraction is already
  // correct — no reason to force a detour through "Modifier" just to reach
  // the "Valider" button when nothing actually needs changing.
  async function validateDirectly() {
    if (!d?.extraction) return;
    setSaving(true);
    try {
      await api.updateFiche(d.fiche_id, d.extraction, true);
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  }

  // Resolve the "unsaved changes" prompt triggered by useBlocker.
  async function saveAndLeave() {
    if (!draft) { blocker.proceed?.(); return; }
    setSaving(true);
    try {
      await api.updateFiche(d!.fiche_id, draft, false);
      setDraft(null);
      blocker.proceed?.();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  }
  function discardAndLeave() {
    setDraft(null);
    blocker.proceed?.();
  }

  async function confirmedDelete() {
    setDeleting(true);
    try {
      await api.deleteFiche(d!.fiche_id);
      // Clear the draft (exits editing) before navigating so useBlocker
      // doesn't intercept this navigation as an "unsaved changes" attempt —
      // the fiche itself is gone, there's nothing left to save.
      setDraft(null);
      navigate("/historique", { replace: true });
    } catch (e) {
      setErr(String(e));
      setDeleting(false);
      setConfirmDelete(false);
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
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-xl font-bold text-slate-800">{String(headerRef)}</h2>
              <StatutBadge statut={d.statut} auto={autoValidated} />
              {!validated && <ConfidenceBadge value={d.overall_confidence} />}
              {d.scan && d.scan.n_pages > 1 && (
                <span className="chip bg-slate-100 text-slate-600">Page {d.scan.page_index + 1} / {d.scan.n_pages}</span>
              )}
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {d.product.designation || "Sans désignation"} · OF {d.work_order.n_of} · Qté {ex?.header.qte.value ?? d.work_order.quantite ?? "—"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <ActionButtons
              editing={editing} saving={saving} fiche={d} validated={validated}
              onModify={() => setDraft(clone(d!.extraction!))}
              onCancel={() => setDraft(null)}
              onSave={() => save(false)}
              onValidate={() => save(true)}
              onValidateDirect={validateDirectly}
              onDeleteClick={() => setConfirmDelete(true)}
            />
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
          autoValidated ? (
            <div className="mt-3 flex items-center gap-2 rounded-lg bg-teal-50 px-3 py-2 text-xs font-medium text-teal-700">
              <Sparkles size={15} />
              Validée automatiquement par le système (règles de cohérence satisfaites) — non confirmée par un opérateur.
            </div>
          ) : (
            <div className="mt-3 flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">
              <ShieldCheck size={15} />
              Fiche validée et confirmée par un opérateur — données fiables.
            </div>
          )
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
          <div className="mb-2 px-2 text-sm font-semibold text-slate-700">
            Document scanné{d.scan && d.scan.n_pages > 1 ? ` — page ${d.scan.page_index + 1}` : ""}
          </div>
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
                  {([["ref_produit", "Réf. Produit"], ["n_of", "N° OF"], ["qte", "Quantité"], ["annotation_serie", "Annotation série"]] as const).map(([k, lbl]) => {
                    const isHit = active?.scope === "header" && active.field === k;
                    return (
                      <div
                        key={k}
                        className={`rounded-lg px-3 py-2 transition-colors ${!editing ? "cursor-text" : ""} ${isHit ? cellHighlightCls : "bg-slate-50"}`}
                        onDoubleClick={!editing ? () => enterEditAt("header", null, k) : undefined}
                        title={!editing ? "Double-cliquer pour modifier" : undefined}
                      >
                        <div className="text-[11px] uppercase tracking-wide text-slate-400">{lbl}</div>
                        {editing ? (
                          <input
                            className={`${inputCls} ${isHit ? inputHighlightCls : ""}`}
                            value={String((ex.header as any)[k]?.value ?? "")}
                            onChange={(e) => setHeader(k, e.target.value)}
                            onKeyDown={commitOnEnter}
                          />
                        ) : (
                          <div className="mt-0.5 font-semibold text-slate-800"><FieldCell value={(ex.header as any)[k]?.value} confidence={(ex.header as any)[k]?.confidence} /></div>
                        )}
                      </div>
                    );
                  })}
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
                          {rows.map(({ o, i }) => (
                            <OpRow key={i} o={o} idx={i} editing={editing} setOp={setOp} onFieldBlur={checkBulkOnBlur} active={active} registerRow={registerRow} enterEditAt={enterEditAt} />
                          ))}
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
                        {ex.controls.map((c, i) => (
                          <CtrlRow key={i} c={c} idx={i} editing={editing} setCtrl={setCtrl} onFieldBlur={checkBulkOnBlur} active={active} registerRow={registerRow} enterEditAt={enterEditAt} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {d.validation?.length > 0 && (() => {
                const resolvedSet = new Set<string>(((d.extraction?.meta as { resolved_alerts?: string[] } | undefined)?.resolved_alerts) || []);
                const warnings = d.validation.filter((v) => v.level !== "error");
                const errors = d.validation.filter((v) => v.level === "error");
                const doneCount = warnings.filter((v) => resolvedSet.has(alertKey(v))).length;
                const allDone = errors.length === 0 && doneCount === warnings.length;
                return (
                <div className="card p-4">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                      <span className={allDone ? "text-emerald-500" : "text-amber-500"}>{allDone ? "✓" : "⚠"}</span>
                      Contrôles de cohérence — <span className="tabular-nums">{doneCount}/{warnings.length}</span> vérifié{doneCount > 1 ? "s" : ""}
                      {errors.length > 0 && <span className="font-bold text-rose-600"> · {errors.length} à corriger</span>}
                    </h3>
                    {!allDone && !validated && doneCount < warnings.length && (
                      <button
                        disabled={resolving !== null}
                        onClick={() => warnings.forEach((v) => { const k = alertKey(v); if (!resolvedSet.has(k)) resolveAlert(k, true); })}
                        className="shrink-0 rounded-lg bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-100 hover:bg-emerald-100 disabled:opacity-40"
                      >
                        Tout confirmer
                      </button>
                    )}
                  </div>
                  {allDone ? (
                    <p className="mb-2 flex items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 py-1.5 text-[11px] font-medium text-emerald-700">
                      <ShieldCheck size={13} /> Toutes les alertes ont été vérifiées — fiche validée.
                    </p>
                  ) : errors.length > 0 ? (
                    <p className="mb-2 rounded-lg bg-rose-50 px-2.5 py-1.5 text-[11px] font-medium text-rose-600">Une erreur bloque la validation — <b>corrigez le champ</b> (bouton Modifier) : l'alerte disparaît dès que la donnée est saisie, et la fiche se valide.</p>
                  ) : (
                    <p className="mb-2 text-[11px] text-slate-400">Vérifiez chaque alerte — <b>Confirmer</b> si la lecture est correcte, <b>Ignorer</b> sinon. Quand tout est vérifié, la fiche est validée.</p>
                  )}
                  <ul className="space-y-1.5">
                    {d.validation.map((v, i) => {
                      const key = alertKey(v);
                      const t = issueTarget(v);
                      const isActive = sameTarget(active, t);
                      const isError = v.level === "error";
                      const done = !isError && resolvedSet.has(key);
                      const busy = resolving === key;
                      return (
                        <li
                          key={i}
                          onMouseEnter={() => setHover(t)}
                          onMouseLeave={() => setHover(null)}
                          onClick={() => {
                            setPinned((p) => (sameTarget(p, t) ? null : t));
                            if (t.loc) rowRefs.current.get(t.loc)?.scrollIntoView({ behavior: "smooth", block: "center" });
                          }}
                          className={`flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 text-xs transition-colors ${done ? "opacity-55" : ""} ${isActive ? (isError ? "bg-rose-50 ring-1 ring-rose-300" : "bg-amber-50 ring-1 ring-amber-300") : "hover:bg-slate-50"}`}
                        >
                          <span className={`mt-0.5 inline-flex shrink-0 rounded px-1.5 py-0.5 font-semibold ${isError ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}`}>{isError ? "Erreur" : "Alerte"}</span>
                          <span className={`flex-1 ${done ? "text-slate-400 line-through" : "text-slate-600"}`}>{v.message}</span>
                          {!validated && (
                            <span className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
                              {isError ? (
                                <button disabled={editing} onClick={() => setDraft(clone(d.extraction!))} className="rounded-md bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-600 ring-1 ring-inset ring-rose-100 hover:bg-rose-100 disabled:opacity-40" title="Corriger le champ concerné">
                                  À corriger
                                </button>
                              ) : done ? (
                                <button disabled={busy} onClick={() => resolveAlert(key, false)} className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium text-emerald-600 hover:bg-emerald-50" title="Rouvrir cette alerte">
                                  {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Vérifié
                                </button>
                              ) : (
                                <>
                                  <button disabled={busy} onClick={() => resolveAlert(key, true)} className="rounded-md bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-100 hover:bg-emerald-100 disabled:opacity-40" title="La lecture est correcte">
                                    Confirmer
                                  </button>
                                  <button disabled={busy} onClick={() => resolveAlert(key, true)} className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-500 hover:bg-slate-200 disabled:opacity-40" title="Ignorer cette alerte">
                                    Ignorer
                                  </button>
                                </>
                              )}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
                );
              })()}

              {/* Mirrors the top action bar — avoids scrolling back up after
                  reading through a long operations table to validate/save. */}
              <div className="card flex justify-end p-4">
                <ActionButtons
                  editing={editing} saving={saving} fiche={d} validated={validated}
                  onModify={() => setDraft(clone(d!.extraction!))}
                  onCancel={() => setDraft(null)}
                  onSave={() => save(false)}
                  onValidate={() => save(true)}
                  onValidateDirect={validateDirectly}
                  onDeleteClick={() => setConfirmDelete(true)}
                />
              </div>
            </>
          ) : <div className="card p-8 text-center text-slate-400">Aucune donnée d'extraction.</div>}
        </div>
      </div>

      {bulk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="card w-full max-w-md p-5">
            <h3 className="text-base font-bold text-slate-800">
              Corriger aussi «{bulk.oldValue}» → «{bulk.newValue}» ailleurs ?
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              {bulk.fieldLabel} — {bulk.matches.length} autre{bulk.matches.length > 1 ? "s" : ""} ligne{bulk.matches.length > 1 ? "s" : ""} de cette fiche a{bulk.matches.length > 1 ? "ent" : ""} encore «{bulk.oldValue}». Décochez celles à ne pas changer.
            </p>
            <div className="mt-3 max-h-48 space-y-1 overflow-y-auto rounded-lg border border-slate-100 p-2">
              {bulk.matches.map((m, i) => (
                <label key={i} className="flex items-center justify-between gap-2 rounded px-1.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50">
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={bulkChecked.has(i)}
                      onChange={(e) => setBulkChecked((s) => {
                        const n = new Set(s);
                        e.target.checked ? n.add(i) : n.delete(i);
                        return n;
                      })}
                    />
                    {m.label}
                  </span>
                  <span className="shrink-0 font-mono text-[11px] text-slate-400">
                    {bulk.oldValue} → <span className="font-semibold text-agilink-700">{bulk.newValue}</span>
                  </span>
                </label>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between gap-2">
              <button onClick={() => setBulk(null)} className="text-xs font-medium text-slate-500 hover:text-slate-700">
                Non, juste cette cellule
              </button>
              <button onClick={applyBulk} disabled={bulkChecked.size === 0} className="inline-flex items-center gap-1.5 rounded-lg bg-agilink-600 px-4 py-2 text-xs font-semibold text-white shadow-soft hover:bg-agilink-700 disabled:opacity-50">
                Oui, corriger {bulkChecked.size === bulk.matches.length ? "les " + bulkChecked.size : bulkChecked.size}
              </button>
            </div>
          </div>
        </div>
      )}

      {blocker.state === "blocked" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="card w-full max-w-sm p-5">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <AlertTriangle size={16} className="text-amber-500" /> Modifications non enregistrées
            </h3>
            <p className="mt-1.5 text-xs text-slate-500">
              Cette fiche est en cours de modification. Enregistrer vos corrections avant de quitter, ou les abandonner ?
            </p>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button onClick={() => blocker.reset?.()} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50">
                Rester sur la page
              </button>
              <button onClick={discardAndLeave} className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100">
                Quitter sans enregistrer
              </button>
              <button onClick={saveAndLeave} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-soft hover:bg-emerald-700 disabled:opacity-50">
                {saving ? <Loader2 size={14} className="animate-spin" /> : null} Enregistrer et quitter
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="card w-full max-w-sm p-5">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <Trash2 size={16} className="text-rose-600" /> Supprimer définitivement cette fiche ?
            </h3>
            <p className="mt-1.5 text-xs text-slate-500">
              Cette action est irréversible : la fiche, ses opérations, contrôles et numéros de série seront supprimés. Le document scanné original n'est pas affecté.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setConfirmDelete(false)} disabled={deleting} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50">
                Annuler
              </button>
              <button onClick={confirmedDelete} disabled={deleting} className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white shadow-soft hover:bg-rose-700 disabled:opacity-50">
                {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />} Supprimer définitivement
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ActionButtons({ editing, saving, fiche, validated, onModify, onCancel, onSave, onValidate, onValidateDirect, onDeleteClick }: {
  editing: boolean;
  saving: boolean;
  fiche: Detail;
  validated: boolean;
  onModify: () => void;
  onCancel: () => void;
  onSave: () => void;
  onValidate: () => void;
  onValidateDirect: () => void;
  onDeleteClick: () => void;
}) {
  if (editing) {
    return (
      <div className="flex items-center gap-2">
        <button onClick={onCancel} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50"><X size={14} /> Annuler</button>
        <button onClick={onSave} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">Enregistrer</button>
        <button onClick={onValidate} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-soft hover:bg-emerald-700">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />} Valider
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button onClick={onModify} className="inline-flex items-center gap-1.5 rounded-lg border border-agilink-200 bg-agilink-50 px-3 py-1.5 text-xs font-semibold text-agilink-700 hover:bg-agilink-100">
        <Pencil size={14} /> Modifier
      </button>
      {!validated && (
        <button onClick={onValidateDirect} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-soft hover:bg-emerald-700 disabled:opacity-50">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />} Valider
        </button>
      )}
      <a href={api.exportUrl(fiche.fiche_id, "xlsx")} className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-100"><FileSpreadsheet size={14} /> Excel</a>
      <a href={api.exportUrl(fiche.fiche_id, "pdf")} className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100"><FileText size={14} /> PDF</a>
      <a href={api.exportUrl(fiche.fiche_id, "csv")} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100"><FileDown size={14} /> CSV</a>
      <button onClick={onDeleteClick} className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50">
        <Trash2 size={14} /> Supprimer
      </button>
    </div>
  );
}

function applSel(v: boolean | null) {
  return v === true ? "Oui" : v === false ? "Non" : "—";
}

type RowProps = {
  editing: boolean;
  onFieldBlur: (scope: "operation" | "control", idx: number, field: string, valueOnFocus: string | null, finalValue: unknown) => void;
  active: Target | null;
  registerRow: (loc: string, el: HTMLTableRowElement | null) => void;
  enterEditAt: (scope: string, loc: string | null, field: string) => void;
};

// While viewing (not yet editing), a cell looks like plain read data and
// double-clicking it jumps straight into full edit mode (see enterEditAt).
// Once editing, every cell is a live input at once — no per-cell gating.
function EditCell({ editing, onEnterEdit, highlightCls, display, input }: {
  editing: boolean;
  onEnterEdit: () => void;
  highlightCls: string;
  display: ReactNode;
  input: ReactNode;
}) {
  if (editing) return <td className="px-2 py-1">{input}</td>;
  return (
    <td className={`px-2 py-1.5 cursor-text ${highlightCls}`} onDoubleClick={onEnterEdit} title="Double-cliquer pour modifier">
      {display}
    </td>
  );
}

// Enter commits (same as clicking away).
function commitOnEnter(e: KeyboardEvent<HTMLInputElement>) {
  if (e.key === "Enter") e.currentTarget.blur();
}

function OpRow({ o, idx, editing, setOp, onFieldBlur, active, registerRow, enterEditAt }: { o: OperationRow; idx: number; setOp: (i: number, f: string, p: object) => void } & RowProps) {
  const loc = rowLoc(o.partie, o.nom_operation);
  const isRow = !!active && active.loc === loc;
  const hit = (field: string) => (isRow && active!.field === field ? cellHighlightCls : "");
  const hitInput = (field: string) => (isRow && active!.field === field ? inputHighlightCls : "");
  // Tracks each field's value as of the last focus, so the bulk-correction
  // check (on blur) compares "before I started typing" → "final", not every
  // intermediate keystroke.
  const focusVal = useRef<Record<string, string | null>>({});
  const i = (field: string) => `${inputCls} ${hitInput(field)}`;
  const enter = (field: string) => () => enterEditAt("operation", loc, field);
  const blank = o.applicable.value === null && !o.matricule_operateur.value && !o.date_op.raw_text;

  return (
    <tr ref={(el) => registerRow(loc, el)} className={isRow ? "bg-amber-50/70" : !editing && blank ? "text-slate-300" : "hover:bg-slate-50"}>
      <td className="px-2 py-1.5 tabular-nums text-slate-400">{o.ordre}</td>
      <td className="px-2 py-1.5 text-slate-600">{o.nom_operation}</td>
      <EditCell
        editing={editing} onEnterEdit={enter("applicable")} highlightCls={hit("applicable")}
        display={<FieldCell value={o.applicable.value} confidence={o.applicable.confidence} />}
        input={
          <select className={i("applicable")} value={applSel(o.applicable.value)}
            onChange={(e) => setOp(idx, "applicable", { value: e.target.value === "Oui" ? true : e.target.value === "Non" ? false : null })}>
            <option>—</option><option>Oui</option><option>Non</option>
          </select>
        }
      />
      <EditCell
        editing={editing} onEnterEdit={enter("date_op")} highlightCls={hit("date_op")}
        display={<FieldCell value={o.date_op.value} confidence={o.date_op.confidence} raw={o.date_op.raw_text} />}
        input={
          <input className={i("date_op")} value={o.date_op.raw_text ?? (o.date_op.value as any) ?? ""}
            onChange={(e) => setOp(idx, "date_op", { value: null, raw_text: e.target.value })} onKeyDown={commitOnEnter}
          />
        }
      />
      <EditCell
        editing={editing} onEnterEdit={enter("qte_realisee")} highlightCls={`tabular-nums ${hit("qte_realisee")}`}
        display={<FieldCell value={o.qte_realisee.value} confidence={o.qte_realisee.confidence} />}
        input={
          <input className={i("qte_realisee")} value={(o.qte_realisee.value as any) ?? ""}
            onFocus={(e) => { focusVal.current.qte_realisee = e.target.value || null; }}
            onChange={(e) => {
              // Never write NaN to state: with a controlled input, value={NaN
              // ?? ""} still renders the literal text "NaN" (?? only catches
              // null/undefined) — so one stray keystroke would permanently
              // stick the cell on "NaN" with no way to type past it.
              // Silently reject anything that isn't empty or a number; the
              // input then just snaps back to its last valid value.
              const v = e.target.value;
              const n = v === "" ? null : Number(v);
              if (n === null || !Number.isNaN(n)) setOp(idx, "qte_realisee", { value: n });
            }}
            onBlur={(e) => onFieldBlur("operation", idx, "qte_realisee", focusVal.current.qte_realisee, e.target.value === "" ? null : Number(e.target.value))}
            onKeyDown={commitOnEnter}
          />
        }
      />
      <EditCell
        editing={editing} onEnterEdit={enter("heure_debut")} highlightCls={`tabular-nums ${hit("heure_debut")}`}
        display={<FieldCell value={o.heure_debut.value} confidence={o.heure_debut.confidence} />}
        input={
          <input className={i("heure_debut")} value={(o.heure_debut.value as any) ?? ""}
            onChange={(e) => setOp(idx, "heure_debut", { value: e.target.value || null })} onKeyDown={commitOnEnter}
          />
        }
      />
      <EditCell
        editing={editing} onEnterEdit={enter("heure_fin")} highlightCls={`tabular-nums ${hit("heure_fin")}`}
        display={<FieldCell value={o.heure_fin.value} confidence={o.heure_fin.confidence} />}
        input={
          <input className={i("heure_fin")} value={(o.heure_fin.value as any) ?? ""}
            onChange={(e) => setOp(idx, "heure_fin", { value: e.target.value || null })} onKeyDown={commitOnEnter}
          />
        }
      />
      <EditCell
        editing={editing} onEnterEdit={enter("outillage")} highlightCls={hit("outillage")}
        display={<FieldCell value={o.outillage.value} confidence={o.outillage.confidence} />}
        input={
          <input className={i("outillage")} value={(o.outillage.value as any) ?? ""}
            onChange={(e) => setOp(idx, "outillage", { value: e.target.value || null })} onKeyDown={commitOnEnter}
          />
        }
      />
      <EditCell
        editing={editing} onEnterEdit={enter("matricule_operateur")} highlightCls={`font-medium ${hit("matricule_operateur")}`}
        display={<FieldCell value={o.matricule_operateur.value} confidence={o.matricule_operateur.confidence} />}
        input={
          <input className={i("matricule_operateur")} value={(o.matricule_operateur.value as any) ?? ""}
            onFocus={(e) => { focusVal.current.matricule_operateur = e.target.value || null; }}
            onChange={(e) => setOp(idx, "matricule_operateur", { value: e.target.value || null })}
            onBlur={(e) => onFieldBlur("operation", idx, "matricule_operateur", focusVal.current.matricule_operateur, e.target.value || null)}
            onKeyDown={commitOnEnter}
          />
        }
      />
    </tr>
  );
}

function CtrlRow({ c, idx, editing, setCtrl, onFieldBlur, active, registerRow, enterEditAt }: { c: ControlRow; idx: number; setCtrl: (i: number, f: string, p: object) => void } & RowProps) {
  const resTxt = c.resultat.value === true ? "Conforme" : c.resultat.value === false ? "Non conforme" : "—";
  const loc = rowLoc(c.partie, c.nom_operation);
  const isRow = !!active && active.loc === loc;
  const hit = (field: string) => (isRow && active!.field === field ? cellHighlightCls : "");
  const hitInput = (field: string) => (isRow && active!.field === field ? inputHighlightCls : "");
  const focusVal = useRef<string | null>(null);
  const enter = (field: string) => () => enterEditAt("control", loc, field);

  return (
    <tr ref={(el) => registerRow(loc, el)} className={isRow ? "bg-amber-50/70" : "hover:bg-slate-50"}>
      <td className="px-2 py-1.5 text-slate-600">{c.nom_operation}</td>
      <EditCell
        editing={editing} onEnterEdit={enter("resultat")} highlightCls={hit("resultat")}
        display={c.resultat.value === null ? <span className="text-slate-300">—</span> : <span className={`rounded px-1.5 py-0.5 font-medium ${c.resultat.value ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>{resTxt}</span>}
        input={
          <select className={`${inputCls} ${hitInput("resultat")}`} value={resTxt}
            onChange={(e) => setCtrl(idx, "resultat", { value: e.target.value === "Conforme" ? true : e.target.value === "Non conforme" ? false : null })}>
            <option>—</option><option>Conforme</option><option>Non conforme</option>
          </select>
        }
      />
      <EditCell
        editing={editing} onEnterEdit={enter("matricule_operateur")} highlightCls={`font-medium ${hit("matricule_operateur")}`}
        display={<FieldCell value={c.matricule_operateur.value} confidence={c.matricule_operateur.confidence} />}
        input={
          <input className={`${inputCls} ${hitInput("matricule_operateur")}`} value={(c.matricule_operateur.value as any) ?? ""}
            onFocus={(e) => { focusVal.current = e.target.value || null; }}
            onChange={(e) => setCtrl(idx, "matricule_operateur", { value: e.target.value || null })}
            onBlur={(e) => onFieldBlur("control", idx, "matricule_operateur", focusVal.current, e.target.value || null)}
            onKeyDown={commitOnEnter}
          />
        }
      />
    </tr>
  );
}
