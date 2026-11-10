import clsx from "clsx";
import { AlertTriangle, ArrowUp, Check, CheckCircle2, ChevronDown, Eraser, Rocket, Sparkles, Square, Wrench, X, XCircle } from "lucide-react";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { create } from "zustand";
import { Button, IconButton, VerdictBadge } from "../components/ui";
import { api } from "../lib/api";
import { applyOps, stepNumbers, summarizeOps } from "../lib/flow";
import { NODE_META } from "../lib/nodeMeta";
import { useEditor } from "../store/editor";
import type { AgentErrorCode, ChatTurn, RunReport } from "../types/contracts";

type Tool = { name: string; summary: string; ok: boolean; args: Record<string, unknown> };
type Msg = {
  id: number;
  role: "user" | "assistant";
  text: string;
  tools: Tool[];
  opsCount?: number;
  proposal?: "pending" | "accepted" | "rejected";
  dryRun?: RunReport;
  error?: { code: AgentErrorCode; message: string };
  streaming?: boolean;
};

type ChatState = { byFlow: Record<string, Msg[]>; busy: boolean; abort: AbortController | null };
const useChat = create<ChatState>(() => ({ byFlow: {}, busy: false, abort: null }));
const NO_MSGS: Msg[] = [];

const patchLast = (flowId: string, fn: (m: Msg) => Msg) =>
  useChat.setState((s) => {
    const list = [...(s.byFlow[flowId] ?? [])];
    list[list.length - 1] = fn(list[list.length - 1]);
    return { byFlow: { ...s.byFlow, [flowId]: list } };
  });

/** Send one message to the agent for the open flow. Also used by ?ask= on first open. */
export async function sendAgentMessage(text: string) {
  const ed = useEditor.getState();
  const flowId = ed.flowId;
  if (!flowId || !text.trim() || useChat.getState().busy) return;
  const prev = useChat.getState().byFlow[flowId] ?? [];
  const history: ChatTurn[] = prev.filter((m) => m.text).map((m) => ({ role: m.role, content: m.text }));
  const abort = new AbortController();
  useChat.setState((s) => ({
    busy: true,
    abort,
    byFlow: { ...s.byFlow, [flowId]: [...prev, { id: Date.now(), role: "user", text: text.trim(), tools: [] }, { id: Date.now() + 1, role: "assistant", text: "", tools: [], streaming: true }] },
  }));
  // The agent works on what the user sees: the draft plus any proposal not yet accepted.
  const draft = ed.pending.length ? applyOps(ed.draft, ed.pending) : ed.draft;
  try {
    await api.agent(flowId, { message: text.trim(), draft, selected_node_ids: ed.selectedIds.length ? ed.selectedIds : ed.selectedId ? [ed.selectedId] : [], history }, (e) => {
      if (e.event === "text") patchLast(flowId, (m) => ({ ...m, text: m.text + e.data.delta }));
      else if (e.event === "tool_call") patchLast(flowId, (m) => ({ ...m, tools: [...m.tools, e.data] }));
      else if (e.event === "flow_ops") {
        useEditor.getState().propose(e.data.ops);
        patchLast(flowId, (m) => ({ ...m, opsCount: (m.opsCount ?? 0) + e.data.ops.length, proposal: "pending" }));
      } else if (e.event === "dry_run_result") patchLast(flowId, (m) => ({ ...m, dryRun: e.data }));
      else if (e.event === "error") patchLast(flowId, (m) => ({ ...m, error: e.data, streaming: false }));
      else if (e.event === "done") patchLast(flowId, (m) => ({ ...m, streaming: false }));
    }, abort.signal);
  } finally {
    patchLast(flowId, (m) => ({ ...m, streaming: false }));
    useChat.setState({ busy: false, abort: null });
  }
}

/** Tiny, safe formatter: **bold** and line breaks. Never injects HTML. */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => (part.startsWith("**") && part.endsWith("**") ? <strong key={j} className="font-semibold text-ink">{part.slice(2, -2)}</strong> : <Fragment key={j}>{part}</Fragment>))}
        </Fragment>
      ))}
    </>
  );
}

const ERROR_COPY: Record<AgentErrorCode, { title: string; body: string }> = {
  ai_unavailable: { title: "The assistant is offline", body: "You can keep editing by hand. Published flows keep running; they never use AI." },
  invalid_ai_reply: { title: "The assistant gave an answer we couldn't use", body: "Nothing was changed. Try rephrasing, or be more specific about the page." },
  rate_limited: { title: "Slow down a little", body: "You can send 10 messages a minute. Try again shortly." },
  tool_failed: { title: "A check failed", body: "The assistant couldn't test the page. Check the URL and try again." },
};

function ToolList({ tools, streaming }: { tools: Tool[]; streaming?: boolean }) {
  const [open, setOpen] = useState(true);
  if (!tools.length) return null;
  return (
    <div className="mt-2 rounded-lg border border-line bg-zinc-50/70">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-[12px] font-medium text-zinc-600">
        <Wrench className="size-3" /> {tools.length} check{tools.length > 1 ? "s" : ""} on the live page
        <ChevronDown className={clsx("ml-auto size-3.5 transition-transform", !open && "-rotate-90")} />
      </button>
      {open && (
        <ul className="space-y-1 border-t border-line px-2.5 py-2">
          {tools.map((t, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[12px]">
              {t.ok ? <CheckCircle2 className="mt-0.5 size-3 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 size-3 shrink-0 text-red-500" />}
              <span className="min-w-0">
                <span className="font-mono text-[11.5px] text-zinc-700">{t.name}</span>
                {"selector" in t.args && <span className="font-mono text-[11.5px] text-brand-700"> {String(t.args.selector)}</span>}
                <span className="text-muted"> · {t.summary}</span>
              </span>
            </li>
          ))}
          {streaming && <li className="text-[12px] text-muted">…</li>}
        </ul>
      )}
    </div>
  );
}

function ProposalCard({ msg, onPublish }: { msg: Msg; onPublish: () => void }) {
  const pending = useEditor((s) => s.pending);
  const { acceptPending, rejectPending, setDryRun } = useEditor.getState();
  const isLive = msg.proposal === "pending" && pending.length > 0;
  const c = summarizeOps(pending);
  const healthy = msg.dryRun && ["OK", "CHANGED"].includes(msg.dryRun.verdict);
  return (
    <div className="mt-2.5 space-y-2">
      {msg.dryRun && (
        <button onClick={() => setDryRun({ open: true, report: msg.dryRun!, loading: false, error: null })} className="flex w-full items-center gap-2 rounded-lg border border-line bg-white px-2.5 py-2 text-left hover:border-zinc-300">
          <VerdictBadge verdict={msg.dryRun.verdict} size="sm" />
          <span className="min-w-0 flex-1 truncate text-[12.5px]">Test run: {msg.dryRun.items_found} items · {msg.dryRun.reason}</span>
          <span className="text-[12px] font-medium text-brand-700">View</span>
        </button>
      )}
      {msg.opsCount ? (
        isLive ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-2.5">
            <p className="text-[12.5px] font-medium text-emerald-900">
              Proposed on the canvas: {[c.added && `${c.added} new steps`, c.changed && `${c.changed} changed`, c.removed && `${c.removed} removed`, c.variables && `${c.variables} variables`].filter(Boolean).join(", ") || `${c.links} links`}
            </p>
            <p className="mt-0.5 text-[12px] text-emerald-800/80">Nothing is saved until you accept.</p>
            <div className="mt-2 flex gap-1.5">
              <Button size="sm" variant="primary" icon={<Check className="size-3.5" />} onClick={acceptPending}>Accept</Button>
              <Button size="sm" variant="ghost" icon={<X className="size-3.5" />} onClick={rejectPending}>Reject</Button>
            </div>
          </div>
        ) : msg.proposal === "accepted" ? (
          <div className="flex items-center justify-between gap-2 rounded-lg border border-line bg-white p-2.5">
            <span className="flex items-center gap-1.5 text-[12.5px] text-emerald-700"><CheckCircle2 className="size-3.5" /> Added to your draft</span>
            {healthy && <Button size="sm" variant="primary" icon={<Rocket className="size-3.5" />} onClick={onPublish}>Ready to publish</Button>}
          </div>
        ) : (
          <p className="text-[12px] text-muted">{msg.proposal === "rejected" ? "Proposal rejected. Your draft is unchanged." : "Proposal replaced."}</p>
        )
      ) : null}
    </div>
  );
}

function suggestions(starter: boolean, selectedLabel: string | null) {
  if (selectedLabel) return [`Explain what ${selectedLabel} does`, "Also read the stock field", "Only alert when the price drops more than 10%"];
  if (starter) return ["Track prices on the mock shop and alert me when one changes", "Alert me when any of these prices drops: blue kettle, steel flask, tea set", "Watch for new products every 30 minutes"];
  return ["Run every 30 minutes", "Also alert me when a product goes out of stock", "Why would this run be marked broken?"];
}

export function AgentPanel({ onPublish }: { onPublish: () => void }) {
  const flowId = useEditor((s) => s.flowId)!;
  const draft = useEditor((s) => s.draft);
  const selectedIds = useEditor((s) => s.selectedIds);
  const selectedId = useEditor((s) => s.selectedId);
  const msgs = useChat((s) => s.byFlow[flowId] ?? NO_MSGS);
  const busy = useChat((s) => s.busy);
  const [input, setInput] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  // Reflect accept / reject (from the chat or the canvas bar) on open proposals.
  const decision = useEditor((s) => s.decision);
  useEffect(() => {
    if (!decision) return;
    useChat.setState((s) => ({ byFlow: { ...s.byFlow, [flowId]: (s.byFlow[flowId] ?? []).map((m) => (m.proposal === "pending" ? { ...m, proposal: decision.kind } : m)) } }));
  }, [decision, flowId]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  const sel = selectedIds.length ? selectedIds : selectedId ? [selectedId] : [];
  const steps = stepNumbers(draft);
  const selNodes = sel.map((id) => draft.nodes.find((n) => n.id === id)).filter(Boolean);
  const starter = !draft.nodes.some((n) => ["fetch_page", "for_each", "extract_list"].includes(n.type));

  const send = (t: string) => {
    if (!t.trim()) return;
    setInput("");
    void sendAgentMessage(t);
  };

  const chip = (t: string, children?: ReactNode) => (
    <button key={t} onClick={() => send(t)} className="w-full rounded-lg border border-line bg-white px-3 py-2 text-left text-[13px] text-zinc-700 transition-colors hover:border-brand-300 hover:bg-brand-50/40">
      {children ?? t}
    </button>
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
        <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-fuchsia-500 text-white">
          <Sparkles className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[14.5px] font-semibold leading-tight">Assistant</p>
          <p className="text-[12px] text-muted">Edits your draft. Only you can publish.</p>
        </div>
        {msgs.length > 0 && (
          <IconButton label="Clear chat" disabled={busy} onClick={() => useChat.setState((s) => ({ byFlow: { ...s.byFlow, [flowId]: [] } }))}>
            <Eraser className="size-4" />
          </IconButton>
        )}
      </div>

      <div ref={scroller} className="scroll-thin flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {msgs.length === 0 && (
          <div className="space-y-3 pt-2">
            <p className="text-[13.5px] leading-relaxed text-zinc-700">
              Tell me what to watch and when to alert you. I'll open the page, test every selector, and propose steps on the canvas for you to review.
            </p>
            <p className="text-[11.5px] font-semibold uppercase tracking-wide text-zinc-400">Try</p>
            <div className="space-y-1.5">{suggestions(starter, selNodes[0] ? NODE_META[selNodes[0]!.type].label : null).map((s) => chip(s))}</div>
          </div>
        )}
        {msgs.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[88%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand-600 px-3.5 py-2 text-[13.5px] leading-relaxed text-white">{m.text}</div>
            </div>
          ) : (
            <div key={m.id} className="flex gap-2.5">
              <div className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600">
                <Sparkles className="size-3.5" />
              </div>
              <div className="min-w-0 flex-1 text-[13.5px] leading-relaxed text-zinc-700">
                {m.text ? <Rich text={m.text} /> : m.streaming && !m.error ? <span className="inline-flex gap-1 py-2"><Dot /><Dot d={150} /><Dot d={300} /></span> : null}
                <ToolList tools={m.tools} streaming={m.streaming} />
                <ProposalCard msg={m} onPublish={onPublish} />
                {m.error && (
                  <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-3">
                    <p className="flex items-center gap-1.5 text-[13px] font-semibold text-red-800"><AlertTriangle className="size-3.5" /> {ERROR_COPY[m.error.code]?.title ?? "Something went wrong"}</p>
                    <p className="mt-0.5 text-[12.5px] text-red-700">{m.error.message || ERROR_COPY[m.error.code]?.body}</p>
                  </div>
                )}
              </div>
            </div>
          ),
        )}
      </div>

      <div className="border-t border-line p-3">
        {selNodes.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {selNodes.slice(0, 3).map((n) => (
              <span key={n!.id} className="rounded-md bg-brand-50 px-1.5 py-0.5 text-[11.5px] font-medium text-brand-700">
                About: {steps[n!.id]}. {NODE_META[n!.type].label}
              </span>
            ))}
            {selNodes.length > 3 && <span className="text-[11.5px] text-muted">+{selNodes.length - 3}</span>}
          </div>
        )}
        <div className="flex items-end gap-2 rounded-xl border border-line bg-zinc-50 p-1.5 pl-3 focus-within:border-brand-300 focus-within:bg-white focus-within:ring-3 focus-within:ring-brand-50">
          <textarea
            ref={box}
            rows={1}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(140, e.target.scrollHeight) + "px";
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder={starter ? "Describe what to watch…" : "Ask for a change…"}
            aria-label="Message the assistant"
            className="max-h-36 min-h-[34px] flex-1 resize-none bg-transparent py-1.5 text-[13.5px] leading-relaxed placeholder:text-zinc-400 focus:outline-none"
          />
          {busy ? (
            <button aria-label="Stop" onClick={() => useChat.getState().abort?.abort()} className="flex size-8 items-center justify-center rounded-lg bg-zinc-800 text-white">
              <Square className="size-3 fill-current" />
            </button>
          ) : (
            <button aria-label="Send" disabled={!input.trim()} onClick={() => send(input)} className="flex size-8 items-center justify-center rounded-lg bg-brand-600 text-white disabled:bg-zinc-200 disabled:text-zinc-400">
              <ArrowUp className="size-4" />
            </button>
          )}
        </div>
        <p className="mt-1.5 px-1 text-[11px] text-zinc-400">Page content is treated as untrusted. The assistant can't publish, run or delete.</p>
      </div>
    </div>
  );
}

const Dot = ({ d = 0 }: { d?: number }) => <span className="size-1.5 animate-bounce rounded-full bg-zinc-400" style={{ animationDelay: `${d}ms` }} />;
