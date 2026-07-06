import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, Link } from "react-router-dom";
import { LayoutDashboard, ScanLine, History, Database, BotMessageSquare, ListChecks, Loader2, FolderInput, Cloud, X } from "lucide-react";
import FloatingChat from "./FloatingChat";
import { api } from "../api";

// Global, always-on awareness of auto-ingested scans (inbox / SharePoint):
// a live "processing" count for the nav badge + topbar pill, and a toast the
// moment a NEW auto-detected file appears — from any page.
function useScanActivity() {
  const [processing, setProcessing] = useState(0);
  const [toast, setToast] = useState<{ name: string; source: string } | null>(null);
  const lastMax = useRef(-1);
  const seeded = useRef(false);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const scans = await api.listScans();
        if (stop) return;
        setProcessing(scans.filter((s) => s.status === "processing").length);
        const maxId = scans.reduce((m, s) => Math.max(m, s.scan_id), -1);
        if (seeded.current && maxId > lastMax.current) {
          const fresh = scans.find((s) => s.scan_id > lastMax.current && (s.source === "local" || s.source === "sharepoint"));
          if (fresh) setToast({ name: fresh.original_name, source: fresh.source });
        }
        lastMax.current = Math.max(lastMax.current, maxId);
        seeded.current = true;
      } catch { /* keep last */ }
      if (!stop) setTimeout(tick, 4000);
    };
    tick();
    return () => { stop = true; };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 8000);
    return () => clearTimeout(t);
  }, [toast]);

  return { processing, toast, dismiss: () => setToast(null) };
}

const NAV_SECTIONS = [
  {
    label: "Pilotage",
    items: [
      { to: "/", label: "Tableau de bord", icon: LayoutDashboard, end: true },
      { to: "/scanner", label: "Scanner une fiche", icon: ScanLine, end: false },
      { to: "/suivi", label: "Suivi des scans", icon: ListChecks, end: false },
      { to: "/historique", label: "Historique", icon: History, end: false },
    ],
  },
  {
    label: "Exploration",
    items: [
      { to: "/operations", label: "Base de données", icon: Database, end: false },
      { to: "/assistant", label: "Assistant IA", icon: BotMessageSquare, end: false },
    ],
  },
];

const META: Record<string, { title: string; sub: string }> = {
  "/": { title: "Tableau de bord", sub: "Pilotage de la traçabilité interne" },
  "/scanner": { title: "Scanner une fiche", sub: "Importer et extraire une fiche suiveuse" },
  "/suivi": { title: "Suivi des scans", sub: "Statut et progression de chaque fichier" },
  "/historique": { title: "Historique des fiches", sub: "Rechercher et consulter les fiches" },
  "/operations": { title: "Base de données", sub: "Toutes les opérations des fiches validées" },
  "/assistant": { title: "Assistant IA", sub: "Interrogez vos données en langage naturel" },
};

export default function Layout() {
  const { pathname } = useLocation();
  const { processing, toast, dismiss } = useScanActivity();
  const meta =
    META[pathname] ??
    (pathname.startsWith("/fiches/")
      ? { title: "Détail de la fiche", sub: "Données extraites & validation" }
      : { title: "Agilink", sub: "" });

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="relative flex w-[264px] flex-col bg-sidebar text-white shadow-glow">
        <div className="pointer-events-none absolute inset-0 bg-mesh opacity-70" />
        <div className="pointer-events-none absolute inset-y-0 right-0 w-px bg-white/10" />

        <Link to="/" className="relative flex items-center justify-center px-6 pt-9 pb-5">
          <img
            src="/logo.png"
            alt="Agilink Group"
            className="h-14 w-auto drop-shadow-sm"
            style={{ filter: "brightness(0) invert(1)" }}
          />
        </Link>
        <div className="relative mx-6 mb-2 flex items-center gap-2 border-b border-white/10 pb-4">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-300 opacity-70" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </span>
          <p className="text-[10px] font-semibold uppercase tracking-[0.26em] text-agilink-100/70">
            Traçabilité Interne
          </p>
        </div>

        <nav className="relative flex-1 space-y-5 overflow-y-auto px-3.5 py-4">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="space-y-1">
              <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.18em] text-agilink-200/45">
                {section.label}
              </p>
              {section.items.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `group relative flex items-center gap-3 rounded-xl px-2.5 py-2 text-sm font-medium transition-all ${
                      isActive
                        ? "bg-white/[0.10] text-white ring-1 ring-inset ring-white/10"
                        : "text-agilink-100/70 hover:bg-white/[0.06] hover:text-white"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-white shadow-[0_0_12px_rgba(255,255,255,.5)]" />
                      )}
                      <span
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all ${
                          isActive ? "bg-white/15 text-white" : "text-agilink-200/70 group-hover:bg-white/10 group-hover:text-white"
                        }`}
                      >
                        <Icon size={17} />
                      </span>
                      {label}
                      {to === "/suivi" && processing > 0 && (
                        <span className="ml-auto flex items-center gap-1 rounded-full bg-emerald-400/20 px-2 py-0.5 text-[11px] font-bold text-emerald-200 ring-1 ring-inset ring-emerald-300/30">
                          <Loader2 size={10} className="animate-spin" /> {processing}
                        </span>
                      )}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="relative mx-3.5 mb-4 mt-1 space-y-3">
          <div className="rounded-xl bg-white/[0.06] p-3 ring-1 ring-inset ring-white/10">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-white/90">
              Your smart connection
            </p>
            <p className="mt-1 text-[11px] text-agilink-200/55">Fiches Suiveuses · v1.0</p>
          </div>
          <div className="flex items-center gap-2.5 border-t border-white/10 px-1 pt-3.5">
            <span className="text-[9px] font-semibold uppercase tracking-[0.22em] text-agilink-200/45">
              Propulsé par
            </span>
            <img
              src="/farness.png"
              alt="Farness"
              className="h-[15px] w-auto"
              style={{ filter: "brightness(0) invert(1)", opacity: 0.88 }}
            />
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-[68px] shrink-0 items-center justify-between border-b border-slate-200/60 bg-white/70 px-8 shadow-[0_1px_0_rgba(16,24,40,.02)] backdrop-blur-xl">
          <div>
            <h1 className="text-[17px] font-bold leading-tight tracking-tight text-slate-800">{meta.title}</h1>
            {meta.sub && <p className="text-xs text-slate-400">{meta.sub}</p>}
          </div>
          <div className="flex items-center gap-3">
            {/* Persistent Farness credit — on every page, every screen size. */}
            <div className="flex items-center gap-2" title="Plateforme conçue et développée par Farness">
              <span className="hidden text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400 sm:inline">Propulsé par</span>
              <img src="/farness.png" alt="Farness" className="h-4 w-auto opacity-75" />
              <span className="mx-1 hidden h-5 w-px bg-slate-200 sm:block" />
            </div>
            {processing > 0 && (
              <Link to="/suivi" className="inline-flex items-center gap-1.5 rounded-full bg-brand/10 px-3 py-1.5 text-xs font-semibold text-brand ring-1 ring-inset ring-brand/15 transition hover:bg-brand/15" title="Voir le suivi des traitements">
                <Loader2 size={13} className="animate-spin" /> {processing} en cours
              </Link>
            )}
            {pathname !== "/scanner" && (
              <Link to="/scanner" className="btn-primary hidden sm:inline-flex">
                <ScanLine size={16} /> Nouvelle fiche
              </Link>
            )}
            <div className="badge badge-emerald px-3 py-1.5">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              Système opérationnel
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-8"><Outlet /></main>
      </div>

      {/* New auto-ingested file detected (inbox / SharePoint) */}
      {toast && (
        <Link
          to="/suivi"
          onClick={dismiss}
          className="animate-scale-in fixed bottom-6 right-6 z-50 flex max-w-sm items-start gap-3 rounded-2xl border border-slate-100 bg-white p-4 shadow-lift ring-1 ring-black/5"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
            {toast.source === "sharepoint" ? <Cloud size={20} /> : <FolderInput size={20} />}
          </div>
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-800">
              <Loader2 size={13} className="animate-spin text-brand" /> Nouveau fichier détecté
            </p>
            <p className="truncate text-xs text-slate-500">{toast.name}</p>
            <p className="mt-0.5 text-[11px] text-slate-400">
              {toast.source === "sharepoint" ? "SharePoint" : "Dossier local"} · extraction en cours — voir le suivi
            </p>
          </div>
          <button onClick={(e) => { e.preventDefault(); dismiss(); }} className="shrink-0 rounded-md p-0.5 text-slate-300 hover:text-slate-500"><X size={16} /></button>
        </Link>
      )}

      <FloatingChat />
    </div>
  );
}
