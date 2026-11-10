import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ReactFlowProvider } from "@xyflow/react";
import clsx from "clsx";
import { AlertCircle, Bell, Braces, Check, ChevronRight, CloudOff, Download, History, Info, Loader2, MoreHorizontal, Play, Rocket, Settings2, Sparkles, Trash2, Undo2, Workflow } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useShell } from "../components/AppShell";
import { Button, Dialog, EmptyState, Spinner, Toggle, toast } from "../components/ui";
import { AgentPanel, sendAgentMessage } from "../editor/AgentPanel";
import { Canvas } from "../editor/Canvas";
import { DryRunDrawer } from "../editor/DryRunDrawer";
import { Palette } from "../editor/Palette";
import { SettingsPanel } from "../editor/SettingsPanel";
import { VariablesPanel } from "../editor/VariablesPanel";
import { api, ApiError } from "../lib/api";
import { flowsEqual } from "../lib/flow";
import { timeAgo } from "../lib/format";
import { useEditor, type RightPanel } from "../store/editor";
import { AlertsTab } from "../tabs/AlertsTab";
import { RunsTab } from "../tabs/RunsTab";
import { StatusPill } from "./FlowsPage";
import { NextRun } from "../components/NextRun";
import { VERDICT_STYLE } from "../components/ui";

type Tab = "editor" | "runs" | "alerts";

/** Debounced autosave of the draft (PUT /api/flows/{id}). */
function useAutosave() {
  const rev = useEditor((s) => s.rev);
  const saving = useRef(false);
  const qc = useQueryClient();
  const save = useCallback(async () => {
    const s = useEditor.getState();
    if (!s.flowId || saving.current || !["dirty", "error"].includes(s.saveState)) return;
    saving.current = true;
    const sentRev = s.rev;
    s.setSaveState("saving");
    try {
      const res = await api.saveFlow(s.flowId, { name: s.name, draft: s.draft });
      useEditor.getState().applyServer(res, sentRev);
      qc.setQueryData(["flows"], (old: any) => old?.map((f: any) => (f.id === res.id ? { ...f, name: res.name, updated_at: new Date().toISOString() } : f)));
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 409) useEditor.getState().setSaveState("conflict");
      else if (err.status === 422) {
        useEditor.getState().setIssues(err.issues);
        useEditor.getState().setSaveState("invalid");
      } else {
        useEditor.getState().setSaveState("error");
        toast.error("Couldn't save your changes", err.message);
      }
    } finally {
      saving.current = false;
      // Edits that arrived during the save get their own save.
      if (useEditor.getState().saveState === "dirty") setTimeout(save, 300);
    }
  }, [qc]);
  useEffect(() => {
    if (!rev) return;
    const t = setTimeout(save, 800);
    return () => clearTimeout(t);
  }, [rev, save]);
  return save;
}

function SaveIndicator() {
  const s = useEditor((x) => x.saveState);
  const issues = useEditor((x) => x.issues.length);
  const map = {
    saved: { icon: <Check className="size-3.5" />, text: "Saved", cls: "text-muted" },
    dirty: { icon: <span className="size-1.5 rounded-full bg-zinc-400" />, text: "Unsaved", cls: "text-muted" },
    saving: { icon: <Loader2 className="size-3.5 animate-spin" />, text: "Saving…", cls: "text-muted" },
    invalid: { icon: <AlertCircle className="size-3.5" />, text: `Not saved · ${issues} to fix`, cls: "text-red-600" },
    conflict: { icon: <AlertCircle className="size-3.5" />, text: "Changed elsewhere", cls: "text-amber-700" },
    error: { icon: <CloudOff className="size-3.5" />, text: "Offline · retrying", cls: "text-amber-700" },
  }[s];
  return <span className={clsx("flex items-center gap-1 text-[12.5px]", map.cls)}>{map.icon}{map.text}</span>;
}

function NameEditor() {
  const name = useEditor((s) => s.name);
  const setName = useEditor((s) => s.setName);
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState(name);
  useEffect(() => setV(name), [name]);
  if (editing)
    return (
      <input
        autoFocus
        value={v}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => {
          setEditing(false);
          if (v.trim() && v !== name) setName(v.trim());
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setV(name);
            setEditing(false);
          }
        }}
        aria-label="Flow name"
        className="h-8 w-64 rounded-md border border-brand-300 px-2 text-[14px] font-semibold focus:outline-none focus:ring-3 focus:ring-brand-100"
      />
    );
  return (
    <button onClick={() => setEditing(true)} title="Rename" className="max-w-[280px] truncate rounded-md px-1.5 py-1 text-[14px] font-semibold hover:bg-zinc-100">
      {name}
    </button>
  );
}

export function FlowPage() {
  const { id = "", tab: tabParam } = useParams();
  const tab = (["runs", "alerts"].includes(tabParam ?? "") ? tabParam : "editor") as Tab;
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const flowQ = useQuery({ queryKey: ["flow", id], queryFn: () => api.getFlow(id), staleTime: Infinity });
  const alertsQ = useQuery({ queryKey: ["alerts", id], queryFn: () => api.listAlerts(id), refetchInterval: 10_000 });
  const st = useEditor();
  const save = useAutosave();
  const [confirm, setConfirm] = useState<null | "discard" | "unpublish" | "delete">(null);
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState<null | "publish" | "run" | "toggle">(null);

  // Collapse the app sidebar while editing; restore on leave.
  useEffect(() => {
    const prev = useShell.getState().collapsed;
    useShell.getState().set(true);
    return () => useShell.getState().set(prev);
  }, []);

  const storeFlowId = useEditor((s) => s.flowId);
  useEffect(() => {
    if (flowQ.data && storeFlowId !== flowQ.data.id) useEditor.getState().load(flowQ.data);
  }, [flowQ.data, storeFlowId]);

  // ?ask=… from the flow list: send it to the assistant once the flow is loaded.
  useEffect(() => {
    const ask = params.get("ask");
    if (ask && st.flowId === id) {
      setParams({}, { replace: true });
      void sendAgentMessage(ask);
    }
  }, [params, st.flowId, id, setParams]);

  const testNode = useCallback((nid: string) => void testFlowRef.current(nid), []);
  const testAll = useCallback(() => void testFlowRef.current(), []);

  const unread = (alertsQ.data ?? []).filter((a) => !a.read).length;
  const loaded = st.flowId === id;
  const differs = loaded && !!st.published && !flowsEqual(st.draft, st.published);
  const neverPublished = loaded && !st.published;

  const flush = async () => {
    if (useEditor.getState().saveState !== "saved") await save();
    let tries = 0;
    while (useEditor.getState().saveState === "saving" && tries++ < 40) await new Promise((r) => setTimeout(r, 100));
    return useEditor.getState().saveState;
  };

  const testFlowRef = useRef<(untilNode?: string) => Promise<void>>(async () => undefined);
  const testFlow = useCallback(async (untilNode?: string) => {
    const s = useEditor.getState();
    if (!s.flowId) return;
    s.setDryRun({ open: true, loading: true, report: null, error: null, untilNode });
    try {
      const report = await api.dryRun(s.flowId, s.draft, untilNode);
      useEditor.getState().setDryRun({ loading: false, report });
    } catch (e) {
      const err = e as ApiError;
      if (err.issues.length) useEditor.getState().setIssues(err.issues);
      useEditor.getState().setDryRun({ loading: false, error: err.issues.length ? `Fix the highlighted steps first: ${err.issues[0].message}` : err.message });
    }
  }, []);

  testFlowRef.current = testFlow;

  const publish = async () => {
    setBusy("publish");
    try {
      const state = await flush();
      if (state === "invalid" || state === "conflict") return toast.error("Fix the highlighted steps before publishing");
      const res = await api.publish(id);
      useEditor.getState().applyServer(res);
      useEditor.getState().setIssues([]);
      qc.invalidateQueries({ queryKey: ["flows"] });
      qc.invalidateQueries({ queryKey: ["next-run", id] });
      const trig = res.published?.nodes.find((n) => n.type === "trigger")?.config;
      toast.success("Published", trig?.mode === "interval" ? `It runs every ${trig.every_minutes} min. Runs never call AI.` : trig?.mode === "daily" ? `It runs daily at ${trig.at_time}.` : "Use Run now to run it.");
    } catch (e) {
      const err = e as ApiError;
      if (err.issues.length) {
        useEditor.getState().setIssues(err.issues);
        const first = err.issues.find((i) => i.node_id);
        if (first?.node_id) useEditor.getState().select(first.node_id);
        if (tab !== "editor") nav(`/flows/${id}`);
      }
      toast.error(err.issues.length ? `${err.issues.length} step${err.issues.length > 1 ? "s" : ""} to fix before publishing` : "Couldn't publish", err.issues[0]?.message ?? err.message);
    } finally {
      setBusy(null);
    }
  };

  const runNow = async () => {
    setBusy("run");
    try {
      const { run_id } = await api.runNow(id);
      useEditor.getState().setRun({ runId: run_id, nodes: {} });
      if (tab !== "editor" && tab !== "runs") nav(`/flows/${id}`);
      const ctrl = new AbortController();
      await api.streamRun(run_id, (e) => {
        const s = useEditor.getState();
        if (e.event === "node_started") s.patchRunNode(e.data.node_id, { state: "running" });
        if (e.event === "node_finished") s.patchRunNode(e.data.node_id, { state: "done", items_in: e.data.items_in, items_out: e.data.items_out });
        if (e.event === "finished") {
          const v = VERDICT_STYLE[e.data.verdict];
          (["OK", "CHANGED"].includes(e.data.verdict) ? toast.success : toast.error)(`Run finished: ${v.label}`, `${e.data.reason} · AI calls: 0`);
        }
      }, ctrl.signal);
      qc.invalidateQueries({ queryKey: ["runs", id] });
      qc.invalidateQueries({ queryKey: ["alerts", id] });
      qc.invalidateQueries({ queryKey: ["datasets", id] });
      qc.invalidateQueries({ queryKey: ["flows"] });
      qc.invalidateQueries({ queryKey: ["next-run", id] });
      setTimeout(() => useEditor.getState().setRun(null), 5000);
    } catch (e) {
      const err = e as ApiError;
      toast.error(err.code === "already_running" ? "Already running" : "Couldn't start the run", err.message);
    } finally {
      setBusy(null);
    }
  };

  const toggleLive = async (on: boolean) => {
    setBusy("toggle");
    try {
      const res = on ? await api.publish(id) : await api.pause(id);
      useEditor.getState().applyServer(res);
      qc.invalidateQueries({ queryKey: ["flows"] });
      qc.invalidateQueries({ queryKey: ["next-run", id] });
      toast.success(on ? "Schedule resumed" : "Paused", on ? undefined : "Nothing runs until you turn it back on. Run now still works after resuming.");
    } catch (e) {
      toast.error("Couldn't change the schedule", (e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  /** Download the flow on the canvas (saved or not) as a JSON file. Proposals not yet accepted are left out. */
  const exportFlow = () => {
    const s = useEditor.getState();
    const file = {
      format: "scrapeonce.flow",
      version: 1,
      name: s.name,
      exported_at: new Date().toISOString(),
      flow: { variables: s.draft.variables, nodes: s.draft.nodes, edges: s.draft.edges },
    };
    const slug = s.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "flow";
    const url = URL.createObjectURL(new Blob([JSON.stringify(file, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}.scrapeonce.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success("Workflow exported", `${slug}.scrapeonce.json`);
  };

  const doConfirm = async () => {
    const c = confirm;
    setConfirm(null);
    if (c === "discard") {
      useEditor.getState().discardToPublished();
      toast.info("Draft reset to the published version");
    } else if (c === "unpublish") {
      const res = await api.unpublish(id);
      useEditor.getState().applyServer(res);
      qc.invalidateQueries({ queryKey: ["flows"] });
      qc.invalidateQueries({ queryKey: ["next-run", id] });
      toast.success("Unpublished", "The schedule is off. Your draft is kept.");
    } else if (c === "delete") {
      await api.deleteFlow(id);
      qc.invalidateQueries({ queryKey: ["flows"] });
      qc.invalidateQueries({ queryKey: ["next-run", id] });
      nav("/");
      toast.success("Flow deleted");
    }
  };

  // Keyboard: Ctrl+D test flow, Ctrl+S save now, Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y undo and redo.
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      const typing = e.target instanceof HTMLElement && (e.target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName));
      if (tab === "editor" && !typing && (key === "z" || key === "y")) {
        e.preventDefault(); // in a text box the browser's own undo handles the typing
        if (key === "z" && !e.shiftKey) useEditor.getState().undo();
        else useEditor.getState().redo();
        return;
      }
      if (e.key.toLowerCase() === "d" && tab === "editor") {
        e.preventDefault();
        void testFlow();
      }
      if (e.key.toLowerCase() === "s") {
        e.preventDefault();
        void save();
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [tab, testFlow, save]);

  if (flowQ.isError)
    return <EmptyState icon={<Workflow className="size-5" />} title="Couldn't open this flow" body={(flowQ.error as Error).message} action={<Link to="/"><Button>Back to flows</Button></Link>} />;
  if (!loaded) return <div className="flex h-full items-center justify-center"><Spinner className="size-6" /></div>;

  const tabs: { id: Tab; label: string; icon: React.ReactNode; badge?: number }[] = [
    { id: "editor", label: "Editor", icon: <Workflow className="size-3.5" /> },
    { id: "runs", label: "Runs", icon: <History className="size-3.5" /> },
    { id: "alerts", label: "Alerts", icon: <Bell className="size-3.5" />, badge: unread },
  ];

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-4">
        <nav className="flex min-w-0 items-center gap-1 text-[14px]">
          <Link to="/" className="rounded-md px-1.5 py-1 text-muted hover:bg-zinc-100 hover:text-ink">Flows</Link>
          <ChevronRight className="size-3.5 text-zinc-300" />
          <NameEditor />
          <StatusPill status={st.status} />
        </nav>
        <SaveIndicator />
        <div className="flex flex-1 justify-center">
          <div className="flex rounded-lg bg-zinc-100 p-0.5">
            {tabs.map((t) => (
              <Link key={t.id} to={t.id === "editor" ? `/flows/${id}` : `/flows/${id}/${t.id}`} className={clsx("flex h-7 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium transition-colors", tab === t.id ? "bg-white text-ink shadow-sm" : "text-zinc-500 hover:text-ink")}>
                {t.icon}
                {t.label}
                {!!t.badge && <span className="rounded-full bg-orange-500 px-1.5 text-[10.5px] font-bold leading-4 text-white">{t.badge}</span>}
              </Link>
            ))}
          </div>
        </div>
        {st.status === "published" && <NextRun flowId={id} />}
        <Button size="md" icon={<Play className="size-3.5" />} disabled={!st.published || st.status !== "published"} loading={busy === "run"} onClick={runNow} title={!st.published ? "Publish first" : st.status === "paused" ? "Resume the schedule first" : "Run the published flow now"}>
          Run now
        </Button>
        <label className="flex items-center gap-2 text-[13px] font-medium text-zinc-600" title={st.published ? "Turn the schedule on or off" : "Publish to turn on the schedule"}>
          <Toggle label="Schedule on" checked={st.status === "published"} disabled={!st.published || busy === "toggle"} onChange={toggleLive} />
          {st.status === "published" ? "On" : "Off"}
        </label>
        <div className="relative">
          <button aria-label="More actions" onClick={() => setMenu((m) => !m)} className="flex size-8 items-center justify-center rounded-lg text-zinc-500 hover:bg-zinc-100 hover:text-ink">
            <MoreHorizontal className="size-4" />
          </button>
          {menu && (
            <div className="absolute right-0 top-9 z-30 w-52 rounded-lg border border-line bg-white p-1 shadow-pop" onMouseLeave={() => setMenu(false)}>
              <button onClick={() => { setMenu(false); exportFlow(); }} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] hover:bg-zinc-100">
                <Download className="size-3.5" /> Export workflow (.json)
              </button>
              <div className="my-1 h-px bg-line" />
              <button disabled={!st.published} onClick={() => { setMenu(false); setConfirm("unpublish"); }} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] hover:bg-zinc-100 disabled:opacity-40">
                <Undo2 className="size-3.5" /> Unpublish
              </button>
              <button onClick={() => { setMenu(false); setConfirm("delete"); }} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] text-red-600 hover:bg-red-50">
                <Trash2 className="size-3.5" /> Delete flow
              </button>
            </div>
          )}
        </div>
      </header>

      {tab === "editor" ? (
        <ReactFlowProvider>
          <div className="flex min-h-0 flex-1">
            <Palette />
            <div className="relative flex min-w-0 flex-1 flex-col">
              {(differs || neverPublished) && (
                <div className="flex shrink-0 items-center gap-3 border-b border-line bg-white px-4 py-2">
                  <Info className="size-4 text-zinc-500" />
                  <p className="flex-1 text-[13.5px]">
                    {neverPublished ? (
                      <>This flow is a draft. <span className="text-muted">Publish runs a test first, then starts the schedule.</span></>
                    ) : (
                      <>You have unpublished changes. <span className="text-muted">The live version, published {timeAgo(st.publishedAt)}, keeps running until you publish.</span></>
                    )}
                  </p>
                  {differs && <Button variant="ghost" onClick={() => setConfirm("discard")}>Discard changes</Button>}
                  <Button variant="primary" icon={<Rocket className="size-3.5" />} loading={busy === "publish"} disabled={!!st.pending.length} title={st.pending.length ? "Accept or reject the assistant's proposal first" : undefined} onClick={publish}>
                    Publish
                  </Button>
                </div>
              )}
              <div className="relative min-h-0 flex-1">
                <Canvas onTestNode={testNode} onTestFlow={testAll} testing={st.dryRun.loading} />
                <DryRunDrawer />
              </div>
            </div>
            <RightPanelHost onTestNode={testNode} onPublish={publish} />
          </div>
        </ReactFlowProvider>
      ) : (
        <div className="min-h-0 flex-1 overflow-hidden bg-zinc-50/40">
          {tab === "runs" && <RunsTab flowId={id} flow={st.published ?? st.draft} />}
          {tab === "alerts" && <AlertsTab flowId={id} />}
        </div>
      )}

      <Dialog
        open={st.saveState === "conflict"}
        onClose={() => undefined}
        title="This flow changed somewhere else"
        footer={<Button variant="primary" onClick={async () => { qc.removeQueries({ queryKey: ["flow", id] }); useEditor.setState({ flowId: null }); await flowQ.refetch(); }}>Reload the latest version</Button>}
      >
        Someone (or another tab) saved a newer version. Reload to continue from it. Your unsaved edits here will be lost.
      </Dialog>
      <Dialog
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title={confirm === "discard" ? "Discard your changes?" : confirm === "unpublish" ? "Unpublish this flow?" : "Delete this flow?"}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button variant={confirm === "discard" ? "primary" : "danger"} onClick={doConfirm}>
              {confirm === "discard" ? "Discard changes" : confirm === "unpublish" ? "Unpublish" : "Delete flow"}
            </Button>
          </>
        }
      >
        {confirm === "discard" && "Your draft goes back to the published version. Edits since then are lost."}
        {confirm === "unpublish" && "The schedule stops and Run now is disabled. Your draft, runs and saved data are kept."}
        {confirm === "delete" && "The flow, its runs, alerts and saved records are deleted. This can't be undone."}
      </Dialog>
    </div>
  );
}

function RightPanelHost({ onTestNode, onPublish }: { onTestNode: (id: string) => void; onPublish: () => void }) {
  const panel = useEditor((s) => s.panel);
  const selectedId = useEditor((s) => s.selectedId);
  const setPanel = useEditor((s) => s.setPanel);
  const vars = useEditor((s) => s.draft.variables.length);
  const pending = useEditor((s) => s.pending.length);
  const items: { id: RightPanel; label: string; icon: React.ReactNode; disabled?: boolean; dot?: boolean }[] = [
    { id: "agent", label: "Assistant", icon: <Sparkles className="size-3.5" />, dot: pending > 0 },
    { id: "settings", label: "Settings", icon: <Settings2 className="size-3.5" />, disabled: !selectedId },
    { id: "variables", label: `Variables${vars ? ` (${vars})` : ""}`, icon: <Braces className="size-3.5" /> },
  ];
  return (
    <aside className="flex w-[384px] shrink-0 flex-col border-l border-line bg-white">
      <div className="flex gap-1 border-b border-line px-2 pt-2">
        {items.map((i) => (
          <button
            key={i.id}
            disabled={i.disabled}
            onClick={() => setPanel(i.id)}
            title={i.disabled ? "Select a step on the canvas" : undefined}
            className={clsx(
              "relative flex h-9 items-center gap-1.5 rounded-t-lg px-3 text-[13px] font-medium transition-colors disabled:opacity-40",
              panel === i.id ? "text-ink after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-brand-600" : "text-zinc-500 hover:text-ink",
            )}
          >
            {i.icon}
            {i.label}
            {i.dot && <span className="size-1.5 rounded-full bg-emerald-500" />}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        {panel === "agent" && <AgentPanel onPublish={onPublish} />}
        {panel === "settings" && selectedId && <SettingsPanel onTestNode={onTestNode} />}
        {panel === "variables" && <VariablesPanel />}
      </div>
    </aside>
  );
}
