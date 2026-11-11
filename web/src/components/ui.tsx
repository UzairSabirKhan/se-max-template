import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { AlertCircle, CheckCircle2, Info, Loader2, X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { create } from "zustand";
import type { Verdict } from "../types/contracts";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

// ---------- Button ----------
type Variant = "primary" | "secondary" | "ghost" | "danger" | "soft";
type Size = "sm" | "md";
export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium transition-colors disabled:opacity-50",
        size === "sm" ? "h-7 px-2.5 text-[12.5px]" : "h-9 px-3.5 text-[13.5px]",
        variant === "primary" && "bg-brand-600 text-white shadow-sm hover:bg-brand-700",
        variant === "secondary" && "border border-line bg-white text-ink shadow-[0_1px_1px_rgb(0_0_0/0.03)] hover:bg-zinc-50",
        variant === "ghost" && "text-zinc-700 hover:bg-zinc-100",
        variant === "soft" && "bg-brand-50 text-brand-700 hover:bg-brand-100",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
        className,
      )}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function IconButton({ label, className, children, active, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; active?: boolean }) {
  return (
    <button
      aria-label={label}
      title={label}
      {...rest}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-lg text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-ink disabled:opacity-40",
        active && "bg-brand-600 text-white hover:bg-brand-700 hover:text-white",
        className,
      )}
    >
      {children}
    </button>
  );
}

// ---------- Form controls ----------
const inputBase =
  "w-full rounded-lg border border-line bg-white px-3 text-[13.5px] text-ink placeholder:text-zinc-400 transition-shadow focus:border-brand-400 focus:outline-none focus:ring-3 focus:ring-brand-100 disabled:bg-zinc-50 disabled:text-zinc-500";

export function Input({ className, invalid, mono, ...rest }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean; mono?: boolean }) {
  return <input {...rest} className={cn(inputBase, "h-9", mono && "font-mono text-[12.5px]", invalid && "border-red-400 focus:border-red-400 focus:ring-red-100", className)} />;
}

export function Textarea({ className, invalid, mono, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean; mono?: boolean }) {
  return <textarea {...rest} className={cn(inputBase, "py-2 leading-relaxed", mono && "font-mono text-[12.5px]", invalid && "border-red-400", className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={cn(
        inputBase,
        "h-9 appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 fill=%22none%22 stroke=%22%2371717a%22 stroke-width=%222%22 viewBox=%220 0 24 24%22><path d=%22m7 15 5 5 5-5M7 9l5-5 5 5%22/></svg>')] bg-[length:12px] bg-[right_10px_center] bg-no-repeat pr-8",
        className,
      )}
    >
      {children}
    </select>
  );
}

export function Toggle({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-40",
        checked ? "bg-brand-600" : "bg-zinc-300",
      )}
    >
      <span className={clsx("inline-block size-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
    </button>
  );
}

export function Segmented<T extends string>({ value, options, onChange, size = "md" }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; size?: Size }) {
  return (
    <div className="inline-flex rounded-lg bg-zinc-100 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "rounded-md px-3 font-medium transition-colors",
            size === "sm" ? "h-6 text-[12px]" : "h-7 text-[13px]",
            value === o.value ? "bg-white text-ink shadow-sm" : "text-zinc-500 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, required, hint, error, children, action }: { label: string; required?: boolean; hint?: ReactNode; error?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label className="text-[13px] font-semibold text-ink">
          {label}
          {required && <span className="ml-0.5 text-red-500">*</span>}
        </label>
        {action}
      </div>
      {children}
      {error ? (
        <p className="flex items-start gap-1 text-[12px] text-red-600">
          <AlertCircle className="mt-0.5 size-3 shrink-0" />
          {error}
        </p>
      ) : hint ? (
        <p className="text-[12px] leading-snug text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

export const Kbd = ({ children }: { children: ReactNode }) => (
  <kbd className="rounded border border-current/20 px-1 font-sans text-[10.5px] font-medium opacity-70">{children}</kbd>
);

export const Spinner = ({ className }: { className?: string }) => <Loader2 className={clsx("size-4 animate-spin text-zinc-400", className)} />;

export function Pill({ tone = "zinc", children, className }: { tone?: "zinc" | "green" | "amber" | "red" | "brand" | "blue"; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium",
        tone === "zinc" && "bg-zinc-100 text-zinc-600",
        tone === "green" && "bg-emerald-50 text-emerald-700",
        tone === "amber" && "bg-amber-50 text-amber-700",
        tone === "red" && "bg-red-50 text-red-700",
        tone === "brand" && "bg-brand-50 text-brand-700",
        tone === "blue" && "bg-sky-50 text-sky-700",
        className,
      )}
    >
      {children}
    </span>
  );
}

// ---------- Verdicts ----------
export const VERDICT_STYLE: Record<Verdict, { tone: "green" | "amber" | "red" | "zinc" | "brand" | "blue"; label: string; help: string }> = {
  OK: { tone: "green", label: "OK", help: "Everything looked right; nothing changed." },
  CHANGED: { tone: "blue", label: "Changed", help: "The site looked right and some items changed." },
  SUSPECT: { tone: "amber", label: "Suspect", help: "A value moved more than 50%; held for you to confirm." },
  BROKEN: { tone: "red", label: "Broken", help: "The site's layout changed. Saved data was kept." },
  BLOCKED: { tone: "red", label: "Blocked", help: "The site refused us (captcha, 403, too slow)." },
  UNSUPPORTED: { tone: "amber", label: "Unsupported", help: "The page needs JavaScript, which we don't run." },
  UNKNOWN: { tone: "zinc", label: "Unknown", help: "Not enough history to judge yet." },
};

export function VerdictBadge({ verdict, size = "md" }: { verdict: Verdict; size?: "sm" | "md" }) {
  const v = VERDICT_STYLE[verdict];
  return (
    <span title={v.help}>
      <Pill tone={v.tone} className={size === "sm" ? "px-1.5 text-[11px]" : ""}>
        <span
          className={clsx(
            "size-1.5 rounded-full",
            v.tone === "green" && "bg-emerald-500",
            v.tone === "blue" && "bg-sky-500",
            v.tone === "amber" && "bg-amber-500",
            v.tone === "red" && "bg-red-500",
            v.tone === "zinc" && "bg-zinc-400",
          )}
        />
        {v.label}
      </Pill>
    </span>
  );
}

// ---------- Toasts ----------
type Toast = { id: number; kind: "success" | "error" | "info"; title: string; body?: string };
type ToastState = { toasts: Toast[]; push: (t: Omit<Toast, "id">) => void; dismiss: (id: number) => void };
export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = Date.now() + Math.random();
    set((s) => ({ toasts: [...s.toasts.slice(-3), { ...t, id }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })), t.kind === "error" ? 7000 : 3500);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));
export const toast = {
  success: (title: string, body?: string) => useToasts.getState().push({ kind: "success", title, body }),
  error: (title: string, body?: string) => useToasts.getState().push({ kind: "error", title, body }),
  info: (title: string, body?: string) => useToasts.getState().push({ kind: "info", title, body }),
};

export function Toaster() {
  const { toasts, dismiss } = useToasts();
  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-[100] flex w-[360px] flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto flex items-start gap-3 rounded-xl border border-line bg-white p-3.5 shadow-pop">
          {t.kind === "success" ? (
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
          ) : t.kind === "error" ? (
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-red-600" />
          ) : (
            <Info className="mt-0.5 size-4 shrink-0 text-brand-600" />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-[13.5px] font-semibold">{t.title}</p>
            {t.body && <p className="mt-0.5 text-[12.5px] text-muted">{t.body}</p>}
          </div>
          <button aria-label="Dismiss" onClick={() => dismiss(t.id)} className="text-zinc-400 hover:text-ink">
            <X className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

// ---------- Dialog ----------
export function Dialog({ open, onClose, title, children, footer, width = 440 }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; width?: number }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-zinc-900/30 p-4 backdrop-blur-[2px]" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className="w-full rounded-2xl border border-line bg-white shadow-pop" style={{ maxWidth: width }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          <IconButton label="Close" onClick={onClose}>
            <X className="size-4" />
          </IconButton>
        </div>
        <div className="px-5 py-4 text-[13.5px] leading-relaxed text-zinc-700">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function EmptyState({ icon, title, body, action }: { icon: ReactNode; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-3 flex size-11 items-center justify-center rounded-xl bg-zinc-100 text-zinc-500">{icon}</div>
      <p className="text-[14.5px] font-semibold">{title}</p>
      {body && <p className="mt-1 max-w-sm text-[13px] text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
