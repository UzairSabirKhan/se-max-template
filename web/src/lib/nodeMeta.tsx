import {
  Bell,
  Database,
  FileSearch,
  GitBranch,
  Globe,
  Hourglass,
  Keyboard,
  Link2,
  ListChecks,
  MousePointerClick,
  Repeat,
  Rows3,
  ScrollText,
  ShieldCheck,
  Table2,
  TextCursorInput,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { FlowNode, NodeType } from "../types/contracts";

export type Tone = "violet" | "blue" | "cyan" | "emerald" | "amber" | "indigo" | "pink" | "orange" | "slate";

export type NodeMeta = {
  type: NodeType;
  label: string;
  group: "Trigger" | "Source" | "Navigate" | "Extract" | "Check" | "Store" | "Control" | "Loop body" | "Output" | "Browser";
  icon: LucideIcon;
  tone: Tone;
  blurb: string;
  disabled?: boolean;
  /** Only allowed inside a for_each body. */
  bodyOnly?: boolean;
  defaultConfig: () => Record<string, any>;
};

export const NODE_META: Record<NodeType, NodeMeta> = {
  trigger: {
    type: "trigger", label: "Schedule", group: "Trigger", icon: Zap, tone: "violet",
    blurb: "When the flow runs",
    defaultConfig: () => ({ mode: "interval", every_minutes: 60, timezone: "Asia/Karachi" }),
  },
  fetch_page: {
    type: "fetch_page", label: "Fetch page", group: "Source", icon: Globe, tone: "blue",
    blurb: "Download one web page",
    defaultConfig: () => ({ url: "" }),
  },
  paginate: {
    type: "paginate", label: "Paginate", group: "Navigate", icon: ScrollText, tone: "cyan",
    blurb: "Follow the next-page link",
    defaultConfig: () => ({ next_selector: "a.next", max_pages: 3 }),
  },
  extract_list: {
    type: "extract_list", label: "Extract list", group: "Extract", icon: Rows3, tone: "emerald",
    blurb: "Read repeated items from a page",
    defaultConfig: () => ({ base_selector: "", identity_key: "", fields: [] }),
  },
  check_page: {
    type: "check_page", label: "Check page", group: "Check", icon: ShieldCheck, tone: "amber",
    blurb: "Stops the run if the site broke",
    defaultConfig: () => ({}),
  },
  save_records: {
    type: "save_records", label: "Save records", group: "Store", icon: Database, tone: "indigo",
    blurb: "Remember items and label changes",
    defaultConfig: () => ({ dataset: "", track_fields: [], alert_on_first_run: false }),
  },
  condition: {
    type: "condition", label: "Condition", group: "Control", icon: GitBranch, tone: "pink",
    blurb: "Split items into true / false",
    defaultConfig: () => ({ match: "all", rules: [] }),
  },
  for_each: {
    type: "for_each", label: "Loop", group: "Control", icon: Repeat, tone: "pink",
    blurb: "Run steps once per item",
    defaultConfig: () => ({ source: "items", max_items: 25, on_error: "skip" }),
  },
  wait: {
    type: "wait", label: "Wait", group: "Control", icon: Hourglass, tone: "pink",
    blurb: "Pause 1–10 seconds",
    defaultConfig: () => ({ seconds: 2 }),
  },
  fetch_item_page: {
    type: "fetch_item_page", label: "Open item page", group: "Loop body", icon: Link2, tone: "blue",
    blurb: "Fetch the page an item links to", bodyOnly: true,
    defaultConfig: () => ({ url_field: "url" }),
  },
  extract_fields: {
    type: "extract_fields", label: "Extract fields", group: "Loop body", icon: FileSearch, tone: "emerald",
    blurb: "Read fields from one page", bodyOnly: true,
    defaultConfig: () => ({ fields: [] }),
  },
  alert: {
    type: "alert", label: "Alert", group: "Output", icon: Bell, tone: "orange",
    blurb: "Notify me in the Alerts tab",
    defaultConfig: () => ({ title: "", level: "info" }),
  },
  results: {
    type: "results", label: "Results table", group: "Output", icon: Table2, tone: "orange",
    blurb: "Keep a named table of items",
    defaultConfig: () => ({ name: "results" }),
  },
  click: {
    type: "click", label: "Click", group: "Browser", icon: MousePointerClick, tone: "slate",
    blurb: "Needs a browser", disabled: true, defaultConfig: () => ({}),
  },
  scroll: {
    type: "scroll", label: "Scroll", group: "Browser", icon: ListChecks, tone: "slate",
    blurb: "Needs a browser", disabled: true, defaultConfig: () => ({}),
  },
  type: {
    type: "type", label: "Type text", group: "Browser", icon: Keyboard, tone: "slate",
    blurb: "Needs a browser", disabled: true, defaultConfig: () => ({}),
  },
  wait_for_element: {
    type: "wait_for_element", label: "Wait for element", group: "Browser", icon: TextCursorInput, tone: "slate",
    blurb: "Needs a browser", disabled: true, defaultConfig: () => ({}),
  },
};

export const PALETTE_GROUPS: { group: NodeMeta["group"]; types: NodeType[] }[] = [
  { group: "Trigger", types: ["trigger"] },
  { group: "Source", types: ["fetch_page", "paginate", "extract_list"] },
  { group: "Check", types: ["check_page"] },
  { group: "Store", types: ["save_records"] },
  { group: "Control", types: ["condition", "for_each", "wait"] },
  { group: "Loop body", types: ["fetch_item_page", "extract_fields"] },
  { group: "Output", types: ["alert", "results"] },
  { group: "Browser", types: ["click", "scroll", "type", "wait_for_element"] },
];

export const TONE: Record<Tone, { tile: string; text: string; ring: string }> = {
  violet: { tile: "bg-violet-50 text-violet-600", text: "text-violet-700", ring: "ring-violet-200" },
  blue: { tile: "bg-sky-50 text-sky-600", text: "text-sky-700", ring: "ring-sky-200" },
  cyan: { tile: "bg-cyan-50 text-cyan-600", text: "text-cyan-700", ring: "ring-cyan-200" },
  emerald: { tile: "bg-emerald-50 text-emerald-600", text: "text-emerald-700", ring: "ring-emerald-200" },
  amber: { tile: "bg-amber-50 text-amber-600", text: "text-amber-700", ring: "ring-amber-200" },
  indigo: { tile: "bg-indigo-50 text-indigo-600", text: "text-indigo-700", ring: "ring-indigo-200" },
  pink: { tile: "bg-fuchsia-50 text-fuchsia-600", text: "text-fuchsia-700", ring: "ring-fuchsia-200" },
  orange: { tile: "bg-orange-50 text-orange-600", text: "text-orange-700", ring: "ring-orange-200" },
  slate: { tile: "bg-zinc-100 text-zinc-400", text: "text-zinc-500", ring: "ring-zinc-200" },
};

const refName = (v: unknown) => (v && typeof v === "object" && "var" in (v as any) ? `{${(v as any).var}}` : null);

function shortUrl(u: string) {
  try {
    const url = new URL(u);
    return url.host + (url.pathname === "/" ? "" : url.pathname);
  } catch {
    return u;
  }
}

/** One-line human summary shown under the node title. */
export function summarize(node: FlowNode): string {
  const c = node.config ?? {};
  switch (node.type) {
    case "trigger":
      if (c.mode === "manual") return "Only when I press Run now";
      if (c.mode === "daily") return `Every day at ${c.at_time ?? "09:00"}`;
      return `Every ${c.every_minutes ?? 60} min`;
    case "fetch_page":
      return refName(c.url) ?? (c.url ? shortUrl(String(c.url)) : "No URL yet");
    case "paginate":
      return `Up to ${c.max_pages ?? 3} pages · ${c.next_selector || "no selector"}`;
    case "extract_list":
    case "extract_fields": {
      const n = (c.fields ?? []).length;
      const base = node.type === "extract_list" && c.base_selector ? ` from ${c.base_selector}` : "";
      return n ? `${n} field${n > 1 ? "s" : ""}${base}` : "No fields yet";
    }
    case "check_page":
      return "Blocks bad runs · required";
    case "save_records":
      return c.dataset ? `Dataset “${c.dataset}”` : "No dataset yet";
    case "condition": {
      const n = (c.rules ?? []).length;
      if (!n) return "No rules yet";
      const r = c.rules[0];
      const first = `${r.field} ${String(r.op).replaceAll("_", " ")}${r.value !== undefined ? " " + (refName(r.value) ?? r.value) : ""}`;
      return n > 1 ? `${first} +${n - 1} (${c.match})` : first;
    }
    case "for_each":
      return `${refName(c.source) ?? "Each item"} · max ${c.max_items ?? 25}`;
    case "wait":
      return `${refName(c.seconds) ?? c.seconds ?? 2} s`;
    case "fetch_item_page":
      return `Open item.${c.url_field ?? "url"}`;
    case "alert":
      return c.title ? `“${c.title}” · ${c.level}` : "No title yet";
    case "results":
      return `Table “${c.name ?? "results"}”`;
    default:
      return "Coming soon";
  }
}
