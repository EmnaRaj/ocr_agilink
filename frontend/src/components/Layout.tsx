import { NavLink, useLocation, Link } from "react-router-dom";
import { LayoutDashboard, ScanLine, History, BotMessageSquare } from "lucide-react";
import type { ReactNode } from "react";
import FloatingChat from "./FloatingChat";

const NAV = [
  { to: "/", label: "Tableau de bord", icon: LayoutDashboard, end: true },
  { to: "/scanner", label: "Scanner une fiche", icon: ScanLine, end: false },
  { to: "/historique", label: "Historique", icon: History, end: false },
  { to: "/assistant", label: "Assistant IA", icon: BotMessageSquare, end: false },
];

const META: Record<string, { title: string; sub: string }> = {
  "/": { title: "Tableau de bord", sub: "Pilotage de la traçabilité interne" },
  "/scanner": { title: "Scanner une fiche", sub: "Importer et extraire une fiche suiveuse" },
  "/historique": { title: "Historique des fiches", sub: "Rechercher et consulter les fiches" },
  "/assistant": { title: "Assistant IA", sub: "Interrogez vos données en langage naturel" },
};

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const meta =
    META[pathname] ??
    (pathname.startsWith("/fiches/")
      ? { title: "Détail de la fiche", sub: "Données extraites & validation" }
      : { title: "Agilink", sub: "" });

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="relative flex w-[262px] flex-col bg-sidebar text-white shadow-glow">
        <div className="pointer-events-none absolute inset-0 bg-mesh opacity-60" />
        <div className="relative flex items-center justify-center px-6 pt-9 pb-6">
          <img
            src="/logo.png"
            alt="Agilink Group"
            className="h-16 w-auto drop-shadow-sm"
            style={{ filter: "brightness(0) invert(1)" }}
          />
        </div>
        <div className="relative mx-6 mb-3 border-b border-white/10 pb-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-agilink-200/70">
            Traçabilité Interne
          </p>
        </div>

        <nav className="relative flex-1 space-y-1 px-3.5 py-4">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `group relative flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-all ${
                  isActive
                    ? "bg-white/12 text-white shadow-innerlg"
                    : "text-agilink-100/70 hover:bg-white/[0.07] hover:text-white"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-white" />
                  )}
                  <Icon size={18} className={isActive ? "text-white" : "text-agilink-200/70 group-hover:text-white"} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="relative m-3.5 rounded-xl bg-white/[0.06] p-3.5 ring-1 ring-white/10">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-white/90">
            Your smart connection
          </p>
          <p className="mt-1 text-[11px] text-agilink-200/60">Fiches Suiveuses · v1.0</p>
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-[68px] shrink-0 items-center justify-between border-b border-slate-200/70 bg-white/75 px-8 backdrop-blur-xl">
          <div>
            <h1 className="text-[17px] font-semibold leading-tight tracking-tight text-slate-800">{meta.title}</h1>
            {meta.sub && <p className="text-xs text-slate-400">{meta.sub}</p>}
          </div>
          <div className="flex items-center gap-3">
            {pathname !== "/scanner" && (
              <Link to="/scanner" className="btn-primary hidden sm:inline-flex">
                <ScanLine size={16} /> Nouvelle fiche
              </Link>
            )}
            <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200/60">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              Système opérationnel
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-8">{children}</main>
      </div>

      <FloatingChat />
    </div>
  );
}
