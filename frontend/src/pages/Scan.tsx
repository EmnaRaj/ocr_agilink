import { useState, useRef, useEffect, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { UploadCloud, FileCheck2, Loader2, AlertCircle, ScanLine, ShieldCheck, Sparkles, CheckCircle2, ArrowRight, Square, Trash2, X, FileText } from "lucide-react";
import { api } from "../api";

interface Batch {
  scanId: number;
  name: string;
  nPages: number;
  nDone: number;
  done: boolean;
  status: "processing" | "done" | "error" | "stopped";
  ficheId?: number;
  error?: string;
}

// Batches keep extracting server-side (Celery) regardless of this page's
// lifecycle, so we persist the active scan ids and resume tracking on mount.
const ACTIVE_SCANS_KEY = "agilink.activeScanIds";

const STEPS = [
  { icon: UploadCloud, title: "1 · Importer", text: "Déposez une ou plusieurs fiches suiveuses (PDF ou photo)." },
  { icon: Sparkles, title: "2 · Extraction IA", text: "Le modèle lit le tableau et structure chaque champ." },
  { icon: ShieldCheck, title: "3 · Valider", text: "Vérifiez, corrigez si besoin, puis validez la fiche." },
];

export default function Scan() {
  const nav = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);

  // Ref mirror so the poll loop always sees the latest batches without
  // re-subscribing on every tick.
  const batchesRef = useRef<Batch[]>([]);
  batchesRef.current = batches;
  const pollingRef = useRef(false);

  function persistActive(list: Batch[]) {
    const ids = list.filter((b) => !b.done).map((b) => b.scanId);
    if (ids.length) localStorage.setItem(ACTIVE_SCANS_KEY, JSON.stringify(ids));
    else localStorage.removeItem(ACTIVE_SCANS_KEY);
  }

  function startPolling() {
    if (pollingRef.current) return;
    pollingRef.current = true;
    const tick = async () => {
      const cur = batchesRef.current;
      if (!cur.some((b) => !b.done)) { pollingRef.current = false; return; }
      const updated = await Promise.all(
        cur.map(async (b) => {
          if (b.done) return b;
          try {
            const s = await api.scanStatus(b.scanId);
            return { ...b, nDone: s.n_done, nPages: s.n_pages, done: s.done, status: s.status };
          } catch {
            return b;
          }
        }),
      );
      setBatches(updated);
      persistActive(updated);
      if (updated.some((b) => !b.done)) setTimeout(tick, 1500);
      else pollingRef.current = false;
    };
    setTimeout(tick, 1200);
  }

  // Resume tracking any batches that were in flight when the page was left.
  useEffect(() => {
    let ids: number[] = [];
    const saved = localStorage.getItem(ACTIVE_SCANS_KEY);
    if (saved) { try { ids = JSON.parse(saved); } catch { /* ignore */ } }
    // Migrate the previous single-scan key so a batch started before this
    // update still shows up (with its new stop/cancel controls).
    const legacy = localStorage.getItem("agilink.activeScanId");
    if (legacy && Number.isFinite(Number(legacy))) { ids = [...new Set([...ids, Number(legacy)])]; localStorage.removeItem("agilink.activeScanId"); }
    if (!Array.isArray(ids) || !ids.length) return;
    (async () => {
      const resumed: Batch[] = [];
      for (const scanId of ids) {
        try {
          const s = await api.scanStatus(scanId);
          resumed.push({ scanId, name: `Scan #${scanId}`, nPages: s.n_pages, nDone: s.n_done, done: s.done, status: s.status });
        } catch { /* scan gone (canceled) — drop it */ }
      }
      if (resumed.length) { setBatches(resumed); startPolling(); }
      else localStorage.removeItem(ACTIVE_SCANS_KEY);
    })();
  }, []); // eslint-disable-line

  function addFiles(list: FileList | null) {
    setErr(null);
    if (!list) return;
    const picked = Array.from(list).filter((f) => {
      if (!/\.(pdf|jpe?g|png)$/i.test(f.name)) { setErr("Certains fichiers ont un format non supporté (PDF ou image uniquement)."); return false; }
      return true;
    });
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => f.name + f.size));
      return [...prev, ...picked.filter((f) => !seen.has(f.name + f.size))];
    });
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  async function submit() {
    if (!files.length) return;
    setBusy(true);
    setErr(null);
    const results: Batch[] = [];
    for (const f of files) {
      try {
        const res = await api.scan(f);
        if (res.mode === "single") {
          results.push({ scanId: res.scan_id, name: f.name, nPages: 1, nDone: 1, done: true, status: "done", ficheId: res.fiche_id });
        } else {
          results.push({ scanId: res.scan_id, name: f.name, nPages: res.n_pages, nDone: 0, done: false, status: "processing" });
        }
      } catch (e) {
        results.push({ scanId: -1, name: f.name, nPages: 0, nDone: 0, done: true, status: "error", error: String(e instanceof Error ? e.message : e) });
      }
    }
    setBatches(results);
    setFiles([]);
    setBusy(false);
    persistActive(results);
    startPolling();
  }

  async function stopOne(scanId: number) {
    try {
      await api.scanStop(scanId);
      setBatches((bs) => { const n = bs.map((b) => (b.scanId === scanId ? { ...b, done: true, status: "stopped" as const } : b)); persistActive(n); return n; });
    } catch (e) { setErr(String(e instanceof Error ? e.message : e)); }
  }

  async function cancelOne(scanId: number) {
    if (!confirm("Annuler ce scan et supprimer les fiches déjà extraites de ce lot ?")) return;
    try { await api.scanCancel(scanId); } catch (e) { setErr(String(e instanceof Error ? e.message : e)); }
    setBatches((bs) => { const n = bs.filter((b) => b.scanId !== scanId); persistActive(n); return n; });
  }

  const anyRunning = batches.some((b) => !b.done);

  return (
    <div className="animate-fade-in mx-auto max-w-3xl space-y-5">
      <div className="text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-white shadow-glow">
          <ScanLine size={26} />
        </div>
        <h2 className="mt-4 text-2xl font-bold tracking-tight text-slate-800">Numériser des fiches suiveuses</h2>
        <p className="mt-1 text-sm text-slate-500">Extraction automatique des opérations, contrôles et matricules.</p>
      </div>

      {batches.length > 0 ? (
        <div className="card animate-scale-in p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-bold text-slate-800">
              {anyRunning ? "Extraction en cours…" : "Extraction terminée"}
            </h3>
            <div className="flex items-center gap-2">
              {anyRunning && <Loader2 size={16} className="animate-spin text-agilink-500" />}
              <button onClick={() => nav("/historique")} className="btn-primary">
                Voir les fiches <ArrowRight size={16} />
              </button>
            </div>
          </div>

          <div className="space-y-3">
            {batches.map((b) => (
              <div key={`${b.scanId}-${b.name}`} className="rounded-xl border border-slate-100 bg-slate-50/60 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white ${b.status === "error" ? "bg-rose-500" : b.status === "stopped" ? "bg-amber-500" : b.done ? "bg-emerald-500" : "bg-brand"}`}>
                      {b.status === "error" ? <AlertCircle size={16} /> : b.status === "stopped" ? <Square size={14} /> : b.done ? <CheckCircle2 size={16} /> : <FileText size={16} />}
                    </div>
                    <p className="truncate text-sm font-semibold text-slate-700">{b.name}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {!b.done ? (
                      <>
                        <button onClick={() => stopOne(b.scanId)} title="Arrêter (garder les fiches déjà extraites)" className="btn-ghost px-2.5 py-1.5 text-xs text-amber-700 ring-1 ring-amber-200">
                          <Square size={13} /> Arrêter
                        </button>
                        <button onClick={() => cancelOne(b.scanId)} title="Annuler et supprimer ce scan" className="btn-ghost px-2.5 py-1.5 text-xs text-rose-700 ring-1 ring-rose-200">
                          <Trash2 size={13} /> Annuler
                        </button>
                      </>
                    ) : b.status === "error" ? (
                      <span className="text-xs font-medium text-rose-600">Échec</span>
                    ) : b.status === "stopped" ? (
                      <span className="text-xs font-medium text-amber-600">Arrêté</span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs font-medium text-emerald-600"><CheckCircle2 size={13} /> Terminé</span>
                    )}
                  </div>
                </div>
                {b.status !== "error" && (
                  <div className="mt-2.5">
                    <div className="mb-1 flex justify-between text-xs font-medium text-slate-400">
                      <span>{b.nDone} / {b.nPages || 1} pages</span>
                      <span>{Math.round((100 * b.nDone) / (b.nPages || 1))}%</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                      <div className={`h-full rounded-full transition-all duration-500 ${b.status === "stopped" ? "bg-amber-400" : b.done ? "bg-emerald-500" : "bg-brand"}`} style={{ width: `${(100 * b.nDone) / (b.nPages || 1)}%` }} />
                    </div>
                  </div>
                )}
                {b.error && <p className="mt-2 text-xs text-rose-600">{b.error}</p>}
              </div>
            ))}
          </div>

          {!anyRunning && (
            <div className="mt-4 text-center">
              <button onClick={() => { setBatches([]); setFiles([]); localStorage.removeItem(ACTIVE_SCANS_KEY); }} className="btn-ghost">
                Scanner d'autres fichiers
              </button>
            </div>
          )}
        </div>
      ) : (
        <>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`card cursor-pointer p-12 text-center transition-all ${
              dragging ? "border-agilink-500 ring-2 ring-agilink-500/20" : "border-dashed hover:border-agilink-400"
            } border-2`}
          >
            <input ref={inputRef} type="file" multiple accept=".pdf,.jpg,.jpeg,.png" className="hidden" onChange={(e) => addFiles(e.target.files)} />
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-agilink-50 text-agilink-500">
                <UploadCloud size={30} />
              </div>
              <p className="mt-2 font-semibold text-slate-700">Glissez-déposez une ou plusieurs fiches</p>
              <p className="text-sm text-slate-400">ou cliquez pour parcourir · PDF multi-pages, JPG, PNG</p>
            </div>
          </div>

          {files.length > 0 && (
            <div className="card p-3">
              <div className="mb-2 flex items-center justify-between px-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{files.length} fichier(s) sélectionné(s)</p>
                <button onClick={() => setFiles([])} className="text-xs text-slate-400 hover:text-rose-600">Tout retirer</button>
              </div>
              <div className="space-y-1.5">
                {files.map((f, i) => (
                  <div key={f.name + f.size} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                    <div className="flex min-w-0 items-center gap-2 text-agilink-700">
                      <FileCheck2 size={16} className="shrink-0" />
                      <span className="truncate text-sm font-medium">{f.name}</span>
                      <span className="shrink-0 text-xs text-slate-400">{(f.size / 1024).toFixed(0)} Ko</span>
                    </div>
                    <button onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))} className="text-slate-300 hover:text-rose-500"><X size={16} /></button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {err && (
            <div className="flex items-center gap-2 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-100">
              <AlertCircle size={18} /> {err}
            </div>
          )}

          <button onClick={submit} disabled={!files.length || busy} className="btn-primary w-full py-3.5 text-base">
            {busy ? <><Loader2 size={20} className="animate-spin" /> Envoi en cours…</> : <>Lancer l'extraction{files.length > 1 ? ` (${files.length} fichiers)` : ""}</>}
          </button>
        </>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {STEPS.map(({ icon: Icon, title, text }) => (
          <div key={title} className="card p-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-agilink-50 text-agilink-600">
              <Icon size={18} />
            </div>
            <p className="mt-2.5 text-sm font-semibold text-slate-700">{title}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
