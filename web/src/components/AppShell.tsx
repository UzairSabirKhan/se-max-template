import clsx from "clsx";
import { BookOpen, PanelLeft, ShieldCheck, Store, Workflow } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { create } from "zustand";
import { api } from "../lib/api";
import { IconButton } from "./ui";

export const useShell = create<{ collapsed: boolean; toggle: () => void; set: (v: boolean) => void }>((set) => ({
  collapsed: false,
  toggle: () => set((s) => ({ collapsed: !s.collapsed })),
  set: (collapsed) => set({ collapsed }),
}));

export function Logo({ small }: { small?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" className={small ? "size-6" : "size-7"} aria-hidden>
        <rect width="32" height="32" rx="8" fill="#5b3df5" />
        <path d="M9 11h8a3 3 0 0 1 0 6h-2a3 3 0 0 0 0 6h8" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
        <circle cx="9" cy="11" r="2.2" fill="#fff" />
        <circle cx="23" cy="23" r="2.2" fill="#fff" />
      </svg>
      {!small && <span className="text-[15px] font-semibold tracking-tight">ScrapeOnce</span>}
    </div>
  );
}

function NavItem({ to, icon, label, external, collapsed }: { to: string; icon: ReactNode; label: string; external?: boolean; collapsed: boolean }) {
  const cls = (active: boolean) =>
    clsx(
      "flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] font-medium transition-colors",
      active ? "bg-white text-ink shadow-card" : "text-zinc-600 hover:bg-zinc-200/60 hover:text-ink",
      collapsed && "justify-center px-0",
    );
  if (external)
    return (
      <a href={to} target="_blank" rel="noreferrer" className={cls(false)} title={label}>
        {icon}
        {!collapsed && label}
      </a>
    );
  return (
    <NavLink to={to} end={to === "/"} className={({ isActive }) => cls(isActive)} title={label}>
      {icon}
      {!collapsed && label}
    </NavLink>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { collapsed, toggle } = useShell();
  return (
    <div className="flex h-screen overflow-hidden bg-zinc-50">
      <aside className={clsx("flex shrink-0 flex-col border-r border-line bg-zinc-50 transition-[width] duration-200", collapsed ? "w-[60px]" : "w-[236px]")}>
        <div className={clsx("flex h-14 items-center", collapsed ? "justify-center" : "justify-between px-4")}>
          {!collapsed && <Logo />}
          <IconButton label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={toggle}>
            <PanelLeft className="size-4" />
          </IconButton>
        </div>
        <nav className={clsx("flex flex-col gap-0.5", collapsed ? "px-2" : "px-3")}>
          <NavItem to="/" icon={<Workflow className="size-4" />} label="Flows" collapsed={collapsed} />
          <NavItem to="/shop" external icon={<Store className="size-4" />} label="Mock shop" collapsed={collapsed} />
          <NavItem to="https://github.com/muhammadusamahoyrr/ScrapeOne#readme" external icon={<BookOpen className="size-4" />} label="Docs" collapsed={collapsed} />
        </nav>
        <div className="flex-1" />
        {!collapsed ? (
          <div className="m-3 rounded-xl border border-line bg-white p-3">
            <div className="flex items-center gap-2 text-[12.5px] font-semibold">
              <ShieldCheck className="size-4 text-emerald-600" />
              Runs never call AI
            </div>
            <p className="mt-1 text-[12px] leading-snug text-muted">The assistant only helps you build. Published flows run on plain rules.</p>
            {api.mode === "mock" && (
              <p className="mt-2 inline-flex rounded-md bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700">Demo data · no backend</p>
            )}
          </div>
        ) : (
          <div className="mb-4 flex justify-center" title="Runs never call AI">
            <ShieldCheck className="size-4 text-emerald-600" />
          </div>
        )}
      </aside>
      <main className="min-w-0 flex-1 overflow-hidden py-2 pr-2">
        <div className="h-full overflow-hidden rounded-xl border border-line bg-white">{children}</div>
      </main>
    </div>
  );
}
