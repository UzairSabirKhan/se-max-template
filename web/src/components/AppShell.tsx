import clsx from "clsx";
import { BookOpen, ChevronsUpDown, LogOut, PanelLeft, Settings, Store, User, Workflow } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { create } from "zustand";
import { api } from "../lib/api";
import { IconButton, toast } from "./ui";

/** Placeholder profile: there are no accounts yet (see README, known limitations). */
const DEMO_USER = { name: "Demo User", email: "demo@scrapeonce.app", initials: "DU" };

function ProfileMenu({ collapsed }: { collapsed: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const notYet = (what: string) => {
    setOpen(false);
    toast.info(`${what} isn’t available in this demo`, "Accounts are not part of the hackathon build.");
  };
  const avatar = (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-sky-400 text-[12px] font-semibold text-white">
      {DEMO_USER.initials}
    </span>
  );
  return (
    <div ref={ref} className={clsx("relative", collapsed ? "mb-3 flex justify-center" : "m-3")}>
      {open && (
        <div role="menu" className={clsx("absolute bottom-full z-30 mb-2 w-56 rounded-xl border border-line bg-white p-1 shadow-pop", collapsed ? "left-0" : "left-0 right-0 w-auto")}>
          <div className="border-b border-line px-3 py-2">
            <p className="truncate text-[13px] font-semibold">{DEMO_USER.name}</p>
            <p className="truncate text-[12px] text-muted">{DEMO_USER.email}</p>
          </div>
          {[
            { label: "Profile", icon: <User className="size-3.5" /> },
            { label: "Settings", icon: <Settings className="size-3.5" /> },
          ].map((i) => (
            <button key={i.label} role="menuitem" onClick={() => notYet(i.label)} className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-[13px] hover:bg-zinc-100">
              {i.icon}
              {i.label}
            </button>
          ))}
          <div className="my-1 h-px bg-line" />
          <button role="menuitem" onClick={() => notYet("Signing out")} className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-[13px] text-red-600 hover:bg-red-50">
            <LogOut className="size-3.5" />
            Sign out
          </button>
        </div>
      )}
      <button
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        title={collapsed ? DEMO_USER.name : undefined}
        onClick={() => setOpen((o) => !o)}
        className={clsx("flex items-center gap-2.5 rounded-xl text-left transition-colors hover:bg-zinc-200/60", collapsed ? "p-1" : "w-full p-2")}
      >
        {avatar}
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold">{DEMO_USER.name}</span>
              <span className="block truncate text-[12px] text-muted">{DEMO_USER.email}</span>
            </span>
            <ChevronsUpDown className="size-4 shrink-0 text-zinc-400" />
          </>
        )}
      </button>
    </div>
  );
}

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
        {!collapsed && api.mode === "mock" && (
          <p className="mx-3 inline-flex self-start rounded-md bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700">Demo data · no backend</p>
        )}
        <ProfileMenu collapsed={collapsed} />
      </aside>
      <main className="min-w-0 flex-1 overflow-hidden py-2 pr-2">
        <div className="h-full overflow-hidden rounded-xl border border-line bg-white">{children}</div>
      </main>
    </div>
  );
}
