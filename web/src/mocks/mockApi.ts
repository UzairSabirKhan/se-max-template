// In-browser fake of the C3 REST API and C5 agent stream.
// Used while Workstream A's backend is still stubs (opt in with VITE_API_MODE=mock; the default is live).
import type { Api, AgentRequest } from "../lib/api";
import { ApiError } from "../lib/errors";
import { applyOps, clone, isVarRef, knownFields, newId, stepNumbers, validateFlow } from "../lib/flow";
import type { AgentEvent, Flow, FlowDetail, FlowNode, FlowOp, Item, RunReport, Verdict } from "../types/contracts";
import { NODE_META } from "../lib/nodeMeta";
import { PRODUCTS, SHOP, seedDb, starterFlow, type MockDb } from "./fixtures";

const KEY = "scrapeonce.mockdb.v1";
const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((res, rej) => {
    const t = setTimeout(res, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      rej(new DOMException("aborted", "AbortError"));
    });
  });

function load(): MockDb {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* private mode etc. */
  }
  return seedDb();
}

export function createMockApi(): Api {
  let db = load();
  const save = () => {
    try {
      localStorage.setItem(KEY, JSON.stringify(db));
    } catch {
      /* ignore */
    }
  };
  const latency = () => sleep(120 + Math.random() * 180);
  const flowOr404 = (id: string) => {
    const f = db.flows.find((x) => x.id === id);
    if (!f) throw new ApiError(404, { error: "not_found", message: "This flow doesn't exist any more." });
    return f;
  };
  const detail = (f: MockDb["flows"][number]): FlowDetail => clone({ id: f.id, name: f.name, status: f.status, draft: f.draft, published: f.published, published_at: f.published_at });
  const agentCalls: number[] = [];

  function dryRunReport(flowId: string | null, flow: Flow, trigger: RunReport["trigger"]): RunReport {
    const sourceIssues = validateFlow(flow, "publish").filter((i) => {
      const n = flow.nodes.find((x) => x.id === i.node_id);
      return !i.node_id || (n && ["fetch_page", "extract_list", "extract_fields", "for_each", "fetch_item_page"].includes(n.type));
    });
    if (sourceIssues.length) throw new ApiError(422, { error: "invalid_flow", issues: sourceIssues });

    const fetchNode = flow.nodes.find((n) => n.type === "fetch_page");
    const listNode = flow.nodes.find((n) => n.type === "extract_list");
    const loop = flow.nodes.find((n) => n.type === "for_each");
    const paged = flow.nodes.some((n) => n.type === "paginate");
    const url = fetchNode ? (isVarRef(fetchNode.config.url) ? String(flow.variables.find((v) => v.name === fetchNode.config.url.var)?.value ?? "") : String(fetchNode.config.url)) : "";

    let verdict: Verdict = "OK";
    let reason = "";
    const evidence: string[] = [];
    let raw: { slug: string; title: string; price: string; stock: string }[] = [];
    const http: RunReport["http"] = [];
    let fields: { name: string; type: string; selector: string }[] = [];

    if (loop) {
      const v = isVarRef(loop.config.source) ? flow.variables.find((x) => x.name === loop.config.source.var) : null;
      const urls = (Array.isArray(v?.value) ? (v!.value as string[]) : []).slice(0, loop.config.max_items ?? 25);
      fields = flow.nodes.find((n) => n.type === "extract_fields" && n.parentId === loop.id)?.config.fields ?? [];
      for (const u of urls) {
        const slug = u.split("/").pop() ?? "";
        const p = PRODUCTS.find((x) => x.slug === slug);
        http.push({ url: u, status: p ? 200 : 404, body_size: p ? 18_400 : 0, error: p ? undefined : "Not found" });
        if (p) raw.push(p);
      }
      evidence.push(`${raw.length} of ${urls.length} links opened`);
    } else if (listNode) {
      fields = listNode.config.fields ?? [];
      if (url.includes("mode=blocked")) {
        verdict = "BLOCKED"; reason = "The site showed a captcha page"; evidence.push("Page asks to verify you are human");
      } else if (url.includes("mode=js")) {
        verdict = "UNSUPPORTED"; reason = "The page builds its content with JavaScript"; evidence.push("0 product boxes in the HTML; page is an app shell");
      } else {
        raw = paged ? PRODUCTS : PRODUCTS.slice(0, 6);
        http.push({ url, status: 200, body_size: 48_211 });
        if (paged) http.push({ url: `${url}?page=2`, status: 200, body_size: 31_877 });
      }
    }

    const v2 = url.includes("layout=v2");
    const value = (p: (typeof PRODUCTS)[number], f: { name: string; type: string; selector: string }) => {
      if (v2 && f.type === "price") return null;
      const n = f.name.toLowerCase();
      if (n.includes("price") || f.type === "price") return p.price;
      if (n.includes("title") || n === "name") return p.title;
      if (n.includes("url") || n.includes("link") || f.type === "url") return `${SHOP}/p/${p.slug}`;
      if (n.includes("stock") || f.type === "stock") return p.stock;
      return null;
    };

    const prev = flowId ? db.records.filter((r) => db.datasets.find((d) => d.id === r.dataset_id && d.flow_id === flowId)) : [];
    const items: Item[] = raw.map((p) => {
      const data: Item["data"] = {};
      for (const f of fields) data[f.name] = value(p, f);
      if (loop) data.url = data.url ?? `${SHOP}/p/${p.slug}`;
      const key = String(data.url ?? p.slug);
      const old = prev.find((r) => r.key === key);
      if (!old) return { key, data, change: "new" };
      const priceField = fields.find((f) => f.type === "price")?.name;
      if (priceField && old.data[priceField] !== data[priceField]) {
        const o = Number(old.data[priceField]);
        const n = Number(data[priceField]);
        return { key, data, change: "changed", previous: { [priceField]: old.data[priceField] }, pct_change: { [priceField]: Math.round(((n - o) / o) * 1000) / 10 } };
      }
      return { key, data, change: "same" };
    });

    const coverage: Record<string, number> = {};
    for (const f of fields) coverage[f.name] = items.length ? items.filter((i) => i.data[f.name] != null).length / items.length : 0;
    const required = fields.filter((f: any) => f.required);
    const missing = required.filter((f) => coverage[f.name] < 1);
    if (verdict === "OK" && !items.length) {
      verdict = "BROKEN";
      reason = listNode || loop ? "No items found: the item selector matched nothing" : "No items found: add Fetch page → Extract list (or a Loop over links) before Check page";
      evidence.push(listNode || loop ? "The item selector matched nothing" : "The flow has no source step");
    } else if (verdict === "OK" && missing.length) {
      verdict = "BROKEN";
      reason = `Site layout changed: ${missing[0].name} missing on ${items.filter((i) => i.data[missing[0].name] == null).length} of ${items.length} items`;
      for (const m of missing) evidence.push(`${m.name} missing on ${items.filter((i) => i.data[m.name] == null).length} of ${items.length} items`);
    }
    const changes = { new: items.filter((i) => i.change === "new").length, changed: items.filter((i) => i.change === "changed").length, removed: 0 };
    if (verdict === "OK") {
      evidence.unshift(`${items.length} of ${items.length} items have every required field`);
      if (changes.new || changes.changed) {
        verdict = "CHANGED";
        reason = changes.new === items.length ? `First run: ${items.length} items would be the baseline` : `${changes.changed} changed, ${changes.new} new`;
      } else reason = `${items.length} items, nothing changed`;
    }

    const order = stepNumbers(flow);
    let stopped = false;
    const node_trace = [...flow.nodes]
      .sort((a, b) => order[a.id] - order[b.id])
      .map((n) => {
        if (stopped) return { node_id: n.id, items_in: 0, items_out: 0, status: "skipped" as const };
        if (n.type === "check_page" && !["OK", "CHANGED"].includes(verdict)) {
          stopped = true;
          return { node_id: n.id, items_in: items.length, items_out: 0, status: "error" as const, note: `${verdict}: stopped here` };
        }
        const isOutput = n.type === "alert" || n.type === "results";
        return { node_id: n.id, items_in: n.type === "trigger" ? 0 : items.length, items_out: isOutput ? 0 : items.length, status: "ok" as const };
      });

    return {
      id: newId("run_"), flow_id: flowId ?? "", trigger, verdict, reason,
      started_at: new Date().toISOString(), duration_ms: 900 + raw.length * 210,
      items_found: items.length, items_valid: items.length - items.filter((i) => required.some((f) => i.data[f.name] == null)).length,
      changes, ai_calls: 0, evidence, http, coverage, node_trace,
      iterations: loop ? items.map((i, index) => ({ node_id: loop.id, index, key: i.key, status: "ok" as const })) : undefined,
      items,
    };
  }

  // ---------- scripted agent ----------
  function agentScript(body: AgentRequest): { text1: string; tools: [string, Record<string, unknown>, string][]; ops: FlowOp[]; text2: string } | { reply: string; ops?: FlowOp[] } {
    const msg = body.message.toLowerCase();
    const draft = body.draft;
    const urls = body.message.match(/https?:\/\/[^\s,]+/g) ?? [];
    const trig = draft.nodes.find((n) => n.type === "trigger");
    const check = draft.nodes.find((n) => n.type === "check_page");
    const builtAlready = draft.nodes.some((n) => ["extract_list", "for_each", "extract_fields"].includes(n.type));
    const every = msg.match(/every\s+(\d+)\s*(min|minute|minutes|h|hour|hours)/);

    const triggerOp: FlowOp[] =
      every && trig
        ? [{ op: "update_node", id: trig.id, config: { ...trig.config, mode: "interval", every_minutes: Number(every[1]) * (every[2].startsWith("h") ? 60 : 1) } }]
        : [];

    if (!builtAlready && trig && check) {
      const startEdge = draft.edges.find((e) => e.source === trig.id && e.target === check.id);
      const node = (type: FlowNode["type"], config: Record<string, any>, parentId?: string): FlowNode => ({ id: newId(), type, config, position: { x: 0, y: 0 }, ...(parentId ? { parentId } : {}) });
      const edge = (source: string, target: string, extra: Partial<FlowOp & { sourceHandle: any; targetHandle: any }> = {}): FlowOp => ({ op: "add_edge", edge: { id: newId("e_"), source, target, ...(extra as any) } });

      if (urls.length > 1 || /these (links|products|pages)/.test(msg)) {
        const list = urls.length > 1 ? urls : [`${SHOP}/p/blue-kettle`, `${SHOP}/p/steel-flask`, `${SHOP}/p/tea-set`];
        const L = node("for_each", { source: { var: "watch_urls" }, max_items: 25, on_error: "skip" });
        const B1 = node("fetch_item_page", { url_field: "url" }, L.id);
        const B2 = node("extract_fields", { fields: [
          { name: "title", selector: "h1.product-title", type: "text", required: true },
          { name: "price", selector: ".price", type: "price", required: true },
        ] }, L.id);
        const S = node("save_records", { dataset: "watched_prices", identity_key: "url", track_fields: ["price"], alert_on_first_run: false });
        const C = node("condition", { match: "all", rules: [{ field: "price", op: "drop_pct_gt", value: { var: "min_drop_pct" } }] });
        const A = node("alert", { title: "Price dropped", level: "warning" });
        return {
          text1: `I'll watch those ${list.length} product pages and alert you when a price drops. First I'll check that each page has the same layout.`,
          tools: [
            ["fetch_page", { url: list[0] }, "18 KB · one product page"],
            ["test_selector_on_many", { urls: list, selector: "h1.product-title" }, `${list.length} of ${list.length} pages match`],
            ["test_selector_on_many", { urls: list, selector: ".price" }, `${list.length} of ${list.length} · Rs 1,250, Rs 2,199, Rs 3,450`],
            ["set_variable", { name: "watch_urls", type: "url_list" }, `${list.length} links`],
            ["dry_run", {}, "OK · 3 items"],
          ],
          ops: [
            { op: "set_variable", variable: { name: "watch_urls", type: "url_list", value: list } },
            { op: "set_variable", variable: { name: "min_drop_pct", type: "number", value: 1 } },
            ...triggerOp,
            ...(startEdge ? [{ op: "remove_edge", id: startEdge.id } as FlowOp] : []),
            { op: "add_node", node: L }, { op: "add_node", node: B1 }, { op: "add_node", node: B2 },
            { op: "add_node", node: S }, { op: "add_node", node: C }, { op: "add_node", node: A },
            edge(trig.id, L.id),
            edge(L.id, B1.id, { sourceHandle: "item" }), edge(B1.id, B2.id), edge(B2.id, L.id, { targetHandle: "next" }),
            edge(L.id, check.id, { sourceHandle: "done" }), edge(check.id, S.id), edge(S.id, C.id),
            edge(C.id, A.id, { sourceHandle: "true" }),
          ],
          text2: "Done. The links live in a **watch_urls** variable, so you can edit them in the Variables panel. Each link is saved as its own record, and you get an alert when any price drops by more than 1%. Review the highlighted steps, then Accept.",
        };
      }

      const target = urls[0] ?? SHOP;
      const F = node("fetch_page", { url: target });
      const P = node("paginate", { next_selector: "a.next", max_pages: 3 });
      const E = node("extract_list", {
        base_selector: "div.product", identity_key: "url", page_anchor: "#product-grid", expected_count: { min: 10, max: 40 },
        fields: [
          { name: "title", selector: "h2", type: "text", required: true },
          { name: "price", selector: ".price", type: "price", required: true },
          { name: "url", selector: "a", attr: "href", type: "url", required: true },
        ],
      });
      const S = node("save_records", { dataset: "shop_prices", identity_key: "url", track_fields: ["price"], alert_on_first_run: false });
      const C1 = node("condition", { match: "any", rules: [{ field: "change", op: "is_new" }] });
      const C2 = node("condition", { match: "any", rules: [{ field: "price", op: "changed" }] });
      const A1 = node("alert", { title: "New product", level: "info" });
      const A2 = node("alert", { title: "Price changed", level: "warning" });
      return {
        text1: "I'll look at the page first, find the repeating product boxes, and test each selector before adding anything.",
        tools: [
          ["fetch_page", { url: target }, "48 KB · 6 product boxes, a next-page link"],
          ["test_selector", { url: target, selector: "div.product" }, "6 matches"],
          ["test_selector", { url: target, selector: ".price" }, "6 matches · Rs 1,250, Rs 2,199, Rs 3,450"],
          ["test_selector", { url: target, selector: "a", attr: "href" }, "6 matches · /shop/p/blue-kettle…"],
          ["test_selector", { url: target, selector: "a.next" }, "1 match · page 2"],
          ["dry_run", {}, "OK · 12 items over 2 pages"],
        ],
        ops: [
          ...triggerOp,
          ...(startEdge ? [{ op: "remove_edge", id: startEdge.id } as FlowOp] : []),
          { op: "add_node", node: F }, { op: "add_node", node: P }, { op: "add_node", node: E },
          { op: "add_node", node: S }, { op: "add_node", node: C1 }, { op: "add_node", node: C2 },
          { op: "add_node", node: A1 }, { op: "add_node", node: A2 },
          edge(trig.id, F.id), edge(F.id, P.id), edge(P.id, E.id), edge(E.id, check.id),
          edge(check.id, S.id), edge(S.id, C1.id), edge(S.id, C2.id),
          edge(C1.id, A1.id, { sourceHandle: "true" }), edge(C2.id, A2.id, { sourceHandle: "true" }),
        ],
        text2: "Here's the flow: fetch the shop, follow up to 3 pages, read **title, price and url** from each product, then save them. You'll get an alert for new products and for price changes. The first run only saves a baseline, so you won't get 12 alerts on day one. Review the highlighted steps, then Accept.",
      };
    }

    if (triggerOp.length) return { reply: `Done: the flow will run every ${(triggerOp[0] as any).config.every_minutes} minutes once you publish.`, ops: triggerOp };
    if (body.selected_node_ids.length) {
      const n = draft.nodes.find((x) => x.id === body.selected_node_ids[0]);
      return { reply: `You've selected **${n ? NODE_META[n.type].label : "a step"}**. Tell me what to change, for example “also read the stock field” or “only alert when the price drops more than 10%”.` };
    }
    return { reply: "I can build a flow from one sentence. Try “track prices on <a shop URL> and alert me on changes” or “alert me when any of these prices drops: <links>”." };
  }

  const api: Api = {
    mode: "mock",
    async nodeTypes() {
      return Object.values(NODE_META).map((m) => ({ type: m.type, group: m.group, label: m.label, disabled: !!m.disabled, config_schema: {} }));
    },
    async listFlows() {
      await latency();
      return db.flows
        .map((f) => ({
          id: f.id, name: f.name, status: f.status, updated_at: f.updated_at, published_at: f.published_at,
          unread_alerts: db.alerts.filter((a) => a.flow_id === f.id && !a.read).length,
        }))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    },
    async createFlow(name) {
      await latency();
      const f = { id: newId("fl_"), name: name || "Untitled flow", status: "draft" as const, draft: starterFlow(), published: null, published_at: null, updated_at: new Date().toISOString() };
      db.flows.push(f);
      save();
      return detail(f);
    },
    async getFlow(id) {
      await latency();
      return detail(flowOr404(id));
    },
    async saveFlow(id, body) {
      await latency();
      const f = flowOr404(id);
      if (body.draft.version !== f.draft.version) throw new ApiError(409, { error: "version_conflict" });
      const issues = validateFlow(body.draft, "save");
      if (issues.length) throw new ApiError(422, { error: "invalid_flow", issues });
      f.draft = { ...clone(body.draft), version: f.draft.version + 1 };
      if (body.name) f.name = body.name;
      f.updated_at = new Date().toISOString();
      save();
      return detail(f);
    },
    async deleteFlow(id) {
      await latency();
      db.flows = db.flows.filter((f) => f.id !== id);
      save();
    },
    async dataSelector(_id, draft, nodeId) {
      // Mock only: every extracted field, no upstream ordering (the real API lists only earlier steps).
      await latency();
      const fields = knownFields(draft).map((f) => ({ name: f.name, type: f.type as any, ops: [], sample: null, source_node_id: null }));
      const hasSave = draft.nodes.some((n) => n.type === "save_records");
      return {
        node_id: nodeId,
        groups: [
          ...(fields.length ? [{ source_node_id: "", source_type: "extract_list", label: "Extracted fields", fields }] : []),
          ...(hasSave ? [{ source_node_id: "", source_type: "save_records", label: "Save records (changes since the last run)",
                           fields: [{ name: "change", type: "change" as const, ops: ["is_new", "is_removed"], sample: null, source_node_id: null }] }] : []),
        ],
        variables: draft.variables.map((v) => ({ name: v.name, type: v.type, sample: v.value })),
      };
    },
    async dryRun(id, draft) {
      await sleep(900);
      return dryRunReport(id, draft, "dry_run");
    },
    async publish(id) {
      await sleep(700);
      const f = flowOr404(id);
      const issues = validateFlow(f.draft, "publish");
      if (issues.length) throw new ApiError(422, { error: "invalid_flow", message: "Fix these steps before publishing.", issues });
      const rep = dryRunReport(id, f.draft, "dry_run");
      if (!["OK", "CHANGED"].includes(rep.verdict))
        throw new ApiError(422, { error: "invalid_flow", message: `The test run failed: ${rep.reason}`, issues: [{ node_id: f.draft.nodes.find((n) => n.type === "check_page")?.id ?? null, path: "", message: rep.reason }] });
      f.published = clone(f.draft);
      f.status = "published";
      f.published_at = new Date().toISOString();
      f.updated_at = f.published_at;
      save();
      return detail(f);
    },
    async pause(id) {
      await latency();
      const f = flowOr404(id);
      f.status = "paused";
      save();
      return detail(f);
    },
    async unpublish(id) {
      await latency();
      const f = flowOr404(id);
      f.status = "draft";
      f.published = null;
      f.published_at = null;
      save();
      return detail(f);
    },
    async runNow(id) {
      await latency();
      const f = flowOr404(id);
      if (!f.published) throw new ApiError(400, { error: "not_published", message: "Publish the flow before running it." });
      const rep = { ...dryRunReport(id, f.published, "manual") };
      // Records were already saved by earlier runs, so labels are mostly "same".
      db.runs.unshift(rep);
      if (rep.verdict === "CHANGED" && rep.changes.new && !db.datasets.some((d) => d.flow_id === id)) {
        const save = f.published.nodes.find((n) => n.type === "save_records");
        const ds = { id: newId("ds_"), flow_id: id, name: save?.config.dataset ?? "data", identity_key: save?.config.identity_key ?? "url", fields: Object.keys(rep.items[0]?.data ?? {}) };
        db.datasets.push(ds);
        rep.items.forEach((i, idx) => db.records.push({ id: `${ds.id}_${idx}`, dataset_id: ds.id, key: i.key, data: i.data, first_seen: rep.started_at, last_changed: null, removed_at: null }));
        db.alerts.unshift({ id: newId("al_"), flow_id: id, run_id: rep.id, node_id: null, kind: "condition", level: "info", title: "Baseline saved", message: `First run saved ${rep.items.length} items. Alerts start from the next run.`, items: [], created_at: rep.started_at, read: false });
      }
      if (!["OK", "CHANGED"].includes(rep.verdict))
        db.alerts.unshift({ id: newId("al_"), flow_id: id, run_id: rep.id, node_id: null, kind: rep.verdict === "BLOCKED" ? "blocked" : rep.verdict === "UNSUPPORTED" ? "unsupported" : "site_changed", level: "error", title: rep.verdict === "BROKEN" ? "Site changed" : `Run ${rep.verdict.toLowerCase()}`, message: rep.reason, items: [], created_at: rep.started_at, read: false });
      save();
      return { run_id: rep.id };
    },
    async nextRun(flowId) {
      const f = flowOr404(flowId);
      const trig = f.published?.nodes.find((n) => n.type === "trigger")?.config;
      if (f.status !== "published" || trig?.mode !== "interval") return { next_run_at: null };
      const last = db.runs.find((r) => r.flow_id === flowId && r.trigger !== "dry_run")?.started_at ?? f.published_at;
      const due = new Date(new Date(last ?? Date.now()).getTime() + (trig.every_minutes ?? 60) * 60_000);
      return { next_run_at: (due.getTime() > Date.now() ? due : new Date(Date.now() + 10_000)).toISOString() };
    },
    async listRuns(flowId, limit = 20) {
      await latency();
      return db.runs.filter((r) => r.flow_id === flowId).slice(0, limit).map(({ evidence, http, coverage, node_trace, iterations, items, ...s }) => s);
    },
    async getRun(runId) {
      await latency();
      const r = db.runs.find((x) => x.id === runId);
      if (!r) throw new ApiError(404, { error: "not_found" });
      return clone(r);
    },
    async streamRun(runId, onEvent, signal) {
      const r = db.runs.find((x) => x.id === runId);
      if (!r) return;
      try {
        for (const t of r.node_trace) {
          if (t.status === "skipped") continue;
          onEvent({ event: "node_started", data: { node_id: t.node_id } });
          await sleep(380, signal);
          onEvent({ event: "node_finished", data: { node_id: t.node_id, items_in: t.items_in, items_out: t.items_out } });
        }
        const { evidence, http, coverage, node_trace, iterations, items, ...summary } = r;
        onEvent({ event: "finished", data: summary });
      } catch {
        /* aborted */
      }
    },
    async listAlerts(flowId) {
      await latency();
      return clone(db.alerts.filter((a) => a.flow_id === flowId));
    },
    async markAlertRead(id) {
      const a = db.alerts.find((x) => x.id === id);
      if (a) a.read = true;
      save();
    },
    async listDatasets(flowId) {
      await latency();
      return db.datasets.filter((d) => d.flow_id === flowId).map((d) => ({ ...d, record_count: db.records.filter((r) => r.dataset_id === d.id).length }));
    },
    async listRecords(datasetId, q) {
      await latency();
      let rows = db.records.filter((r) => r.dataset_id === datasetId);
      if (q.sort) {
        const desc = q.sort.startsWith("-");
        const k = q.sort.replace(/^-/, "");
        rows = [...rows].sort((a, b) => {
          const av = (a.data as any)[k] ?? (a as any)[k];
          const bv = (b.data as any)[k] ?? (b as any)[k];
          const cmp = !isNaN(Number(av)) && !isNaN(Number(bv)) ? Number(av) - Number(bv) : String(av ?? "").localeCompare(String(bv ?? ""));
          return desc ? -cmp : cmp;
        });
      }
      const off = q.offset ?? 0;
      return { total: rows.length, records: clone(rows.slice(off, off + (q.limit ?? 25))) };
    },
    async recordHistory(id) {
      await latency();
      const r = db.records.find((x) => x.id === id);
      return clone(db.history[id] ?? (r ? [{ run_id: "", at: r.first_seen, change: "new" as const, field: null, old_value: null, new_value: null, pct_change: null }] : []));
    },
    async resetDataset(id) {
      await latency();
      db.records = db.records.filter((r) => r.dataset_id !== id);
      save();
    },
    exportCsvUrl(id) {
      const ds = db.datasets.find((d) => d.id === id);
      const rows = db.records.filter((r) => r.dataset_id === id);
      const cols = ds?.fields ?? [];
      const esc = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
      const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc((r.data as any)[c])).join(","))].join("\n");
      return URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    },
    async agent(flowId, body, onEvent, signal) {
      const emit = (e: AgentEvent): void => {
        if (!signal.aborted) onEvent(e);
      };
      const now = Date.now();
      while (agentCalls.length && now - agentCalls[0] > 60_000) agentCalls.shift();
      if (agentCalls.length >= 10) return emit({ event: "error", data: { code: "rate_limited", message: "You've sent 10 messages this minute. Wait a moment." } });
      agentCalls.push(now);
      const typeOut = async (text: string) => {
        for (const chunk of text.match(/.{1,6}/gs) ?? []) {
          emit({ event: "text", data: { delta: chunk } });
          await sleep(14, signal);
        }
      };
      try {
        await sleep(450, signal);
        if (/offline|no ai/.test(body.message.toLowerCase()))
          return emit({ event: "error", data: { code: "ai_unavailable", message: "The AI service isn't answering right now. Your published flows keep running; you can still edit by hand." } });
        const s = agentScript(body);
        if ("reply" in s) {
          await typeOut(s.reply);
          if (s.ops?.length) emit({ event: "flow_ops", data: { ops: s.ops } });
          return emit({ event: "done", data: { tool_calls: 0 } });
        }
        await typeOut(s.text1);
        emit({ event: "text", data: { delta: "\n\n" } });
        let calls = 0;
        for (const [name, args, summary] of s.tools.slice(0, -1)) {
          await sleep(520, signal);
          emit({ event: "tool_call", data: { name, args, ok: true, summary } });
          calls++;
        }
        await sleep(300, signal);
        emit({ event: "flow_ops", data: { ops: s.ops } });
        await sleep(650, signal);
        const merged = applyOps(body.draft, s.ops);
        const [lname, largs] = s.tools[s.tools.length - 1];
        const report = dryRunReport(flowId, merged, "dry_run");
        emit({ event: "tool_call", data: { name: lname, args: largs, ok: true, summary: `${report.verdict} · ${report.items_found} items` } });
        calls++;
        emit({ event: "dry_run_result", data: report });
        await typeOut(s.text2);
        emit({ event: "done", data: { tool_calls: calls } });
      } catch {
        /* aborted by the user */
      }
    },
  };
  // Keep the dev console handy: window.__resetMock() restores the seed data.
  (window as any).__resetMock = () => {
    db = seedDb();
    save();
    location.reload();
  };
  return api;
}
