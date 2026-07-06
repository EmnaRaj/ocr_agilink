import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, CheckCircle2, AlertCircle, Square, Trash2, RotateCcw, Eye, UploadCloud, FolderInput, Cloud, ListChecks } from "lucide-react";
import { api, type ScanRow } from "../api";

const SOURCE_META: Record<string, { label: string; icon: typeof UploadCloud }> = {
  manual: { label: "Import manuel", icon: UploadCloud },
  local: { label: "Dossier local", icon: FolderInput },
  sharepoint: { label: "SharePoint", icon: Cloud },
};

const STATUS_META: Record<string, { label: string; cls: string }> = {
  processing: { label: "En cours", cls: "bg-brand/10 text-brand" },
  done: { label: "Terminé", cls: "bg-emerald-50 text-emerald-700" },
  stopped: { label: "Arrêté", cls: "bg-amber-50 text-amber-700" },
  error: { label: "Échec", cls: "bg-rose-50 text-rose-700" },
};

export default function Scans() {
  const nav = useNavigate();
  const [scans, setScans] = useState<ScanRow[]>([]);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function load() {
    try {
      const rows = await api.listScans();
      setScans(rows);
    } catch { /* keep last */ }
    setLoading(false);
  }

  useEffect(() => {
    load();
    // Live refresh while anything is processing (fast), else a slow heartbeat.
    const tick = () => {
      const active = scans.some((s) => s.status === "processing");
      timer.current = setTimeout(async () => { await load(); tick(); }, active ? 1500 : 6000);
    };
    tick();
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [scans.length, scans.map((s) => s.status).join(",")]); // eslint-disable-line

  async function act(fn: () => Promise<unknown>) {
    try { await fn(); await load(); } catch (e) { alert(String(e instanceof Error ? e.message : e)); }
  }

  const activeCount = scans.filter((s) => s.status === "processing").length;

  return (
    <div className="animate-fade-in mx-auto max-w-5xl space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand text-white shadow-glow">
            <ListChecks size={22} />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-800">Suivi des traitements</h2>
            <p className="text-sm text-slate-500">Chaque fichier scanné, son origine et son statut — en temps réel.</p>
          </div>
        </div>
        <button onClick={() => nav("/scanner")} className="btn-primary"><UploadCloud size={16} /> Numériser</button>
      </div>

      {activeCount > 0 && (
        <div className="flex items-center gap-2 rounded-xl bg-brand/5 px-4 py-2.5 text-sm font-medium text-brand ring-1 ring-brand/10">
          <Loader2 size={16} className="animate-spin" /> {activeCount} traitement(s) en cours…
        </div>
      )}

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
              <th className="px-4 py-3">Fichier</th>
              <th className="px-4 py-3">Origine</th>
              <th className="px-4 py-3">Progression</th>
              <th className="px-4 py-3">Statut</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400"><Loader2 size={20} className="mx-auto animate-spin" /></td></tr>
            )}
            {!loading && scans.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">Aucun scan pour le moment.</td></tr>
            )}
            {scans.map((s) => {
              const src = SOURCE_META[s.source] ?? { label: s.source, icon: UploadCloud };
              const st = STATUS_META[s.status] ?? { label: s.status, cls: "bg-slate-100 text-slate-600" };
              const pct = Math.round((100 * s.n_done) / (s.n_pages || 1));
              const SrcIcon = src.icon;
              return (
                <tr key={s.scan_id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/50">
                  <td className="px-4 py-3">
                    <p className="max-w-[240px] truncate font-medium text-slate-700">{s.original_name}</p>
                    <p className="text-xs text-slate-400">#{s.scan_id} · {new Date(s.uploaded_at).toLocaleString("fr-FR")}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500"><SrcIcon size={14} /> {src.label}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                        <div className={`h-full rounded-full ${s.status === "error" ? "bg-rose-400" : s.status === "stopped" ? "bg-amber-400" : s.done ? "bg-emerald-500" : "bg-brand"}`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs text-slate-400">{s.n_done}/{s.n_pages}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${st.cls}`}>
                      {s.status === "processing" && <Loader2 size={11} className="animate-spin" />}
                      {s.status === "done" && <CheckCircle2 size={11} />}
                      {s.status === "error" && <AlertCircle size={11} />}
                      {st.label}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      {s.status === "processing" ? (
                        <>
                          <button onClick={() => act(() => api.scanStop(s.scan_id))} title="Arrêter (garder les pages faites)" className="btn-icon text-amber-600"><Square size={15} /></button>
                          <button onClick={() => { if (confirm("Annuler et supprimer ce scan ?")) act(() => api.scanCancel(s.scan_id)); }} title="Annuler et supprimer" className="btn-icon text-rose-600"><Trash2 size={15} /></button>
                        </>
                      ) : (s.status === "error" || s.status === "stopped") ? (
                        <button onClick={() => act(() => api.scanRetry(s.scan_id))} title="Relancer" className="btn-icon text-brand"><RotateCcw size={15} /></button>
                      ) : null}
                      {s.n_done > 0 && (
                        <button onClick={() => nav("/historique")} title="Voir les fiches" className="btn-icon text-slate-500"><Eye size={15} /></button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
