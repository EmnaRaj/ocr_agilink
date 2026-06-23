import { useState, useRef, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { UploadCloud, FileCheck2, Loader2, AlertCircle, ScanLine, ShieldCheck, Sparkles, Files, CheckCircle2, ArrowRight } from "lucide-react";
import { api } from "../api";

interface Batch { scanId: number; nPages: number; nDone: number; done: boolean }

const STEPS = [
  { icon: UploadCloud, title: "1 · Importer", text: "Déposez la fiche suiveuse scannée (PDF ou photo)." },
  { icon: Sparkles, title: "2 · Extraction IA", text: "Le modèle lit le tableau et structure chaque champ." },
  { icon: ShieldCheck, title: "3 · Valider", text: "Vérifiez, corrigez si besoin, puis validez la fiche." },
];

export default function Scan() {
  const nav = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);

  function pick(f: File | null) {
    setErr(null);
    if (!f) return;
    if (!/\.(pdf|jpe?g|png)$/i.test(f.name)) return setErr("Format non supporté. Utilisez un PDF ou une image (JPG/PNG).");
    setFile(f);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files?.[0] ?? null);
  }

  function pollStatus(scanId: number) {
    const tick = async () => {
      try {
        const s = await api.scanStatus(scanId);
        setBatch({ scanId, nPages: s.n_pages, nDone: s.n_done, done: s.done });
        if (!s.done) setTimeout(tick, 1500);
      } catch {
        setTimeout(tick, 2500);
      }
    };
    tick();
  }

  async function submit() {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await api.scan(file);
      if (res.mode === "single") {
        nav(`/fiches/${res.fiche_id}`);
        return;
      }
      // Multi-page file → one fiche per page, extracted in the background.
      setBatch({ scanId: res.scan_id, nPages: res.n_pages, nDone: 0, done: false });
      pollStatus(res.scan_id);
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
      setBusy(false);
    }
  }

  return (
    <div className="animate-fade-in mx-auto max-w-3xl space-y-5">
      <div className="text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-white shadow-glow">
          <ScanLine size={26} />
        </div>
        <h2 className="mt-4 text-2xl font-bold tracking-tight text-slate-800">Numériser une fiche suiveuse</h2>
        <p className="mt-1 text-sm text-slate-500">Extraction automatique des opérations, contrôles et matricules.</p>
      </div>

      {batch ? (
        <div className="card animate-scale-in p-7 text-center">
          <div className={`mx-auto flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-soft ${batch.done ? "bg-emerald-500" : "bg-brand"}`}>
            {batch.done ? <CheckCircle2 size={28} /> : <Files size={26} />}
          </div>
          <h3 className="mt-4 text-lg font-bold text-slate-800">
            {batch.done ? `${batch.nDone} fiches extraites` : "Extraction des pages en cours…"}
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Document de <b>{batch.nPages} pages</b> — chaque page devient une fiche.
          </p>

          <div className="mx-auto mt-5 max-w-md">
            <div className="mb-1.5 flex justify-between text-xs font-medium text-slate-500">
              <span>{batch.nDone} / {batch.nPages} pages</span>
              <span>{Math.round((100 * batch.nDone) / batch.nPages)}%</span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-brand transition-all duration-500" style={{ width: `${(100 * batch.nDone) / batch.nPages}%` }} />
            </div>
          </div>

          <div className="mt-6 flex items-center justify-center gap-2">
            {!batch.done && <Loader2 size={16} className="animate-spin text-agilink-500" />}
            <button onClick={() => nav("/historique")} className="btn-primary">
              Voir les fiches <ArrowRight size={16} />
            </button>
            {batch.done && (
              <button onClick={() => { setBatch(null); setFile(null); setBusy(false); }} className="btn-ghost">
                Scanner un autre fichier
              </button>
            )}
          </div>
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
            <input ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            {file ? (
              <div className="flex flex-col items-center gap-2 text-agilink-700">
                <FileCheck2 size={44} />
                <p className="font-semibold">{file.name}</p>
                <p className="text-sm text-slate-400">{(file.size / 1024).toFixed(0)} Ko · cliquez pour changer</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-agilink-50 text-agilink-500">
                  <UploadCloud size={30} />
                </div>
                <p className="mt-2 font-semibold text-slate-700">Glissez-déposez une fiche ou un lot de fiches</p>
                <p className="text-sm text-slate-400">ou cliquez pour parcourir · PDF multi-pages, JPG, PNG</p>
              </div>
            )}
          </div>

          {err && (
            <div className="flex items-center gap-2 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-100">
              <AlertCircle size={18} /> {err}
            </div>
          )}

          <button onClick={submit} disabled={!file || busy} className="btn-primary w-full py-3.5 text-base">
            {busy ? <><Loader2 size={20} className="animate-spin" /> Analyse du document…</> : <>Lancer l'extraction</>}
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
