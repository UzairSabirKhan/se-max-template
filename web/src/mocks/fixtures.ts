import type { Alert, DataRecord, Flow, FlowDetail, RecordChange, RunReport } from "../types/contracts";

export const SHOP = `${typeof location !== "undefined" ? location.origin : "http://localhost:5173"}/shop`;

export const PRODUCTS = [
  { slug: "blue-kettle", title: "Blue Enamel Kettle", price: "1250.00", stock: "In stock" },
  { slug: "steel-flask", title: "Steel Travel Flask", price: "2199.00", stock: "In stock" },
  { slug: "tea-set", title: "Six-Cup Tea Set", price: "3450.00", stock: "Low stock" },
  { slug: "clay-pot", title: "Clay Cooking Pot", price: "1890.00", stock: "In stock" },
  { slug: "spice-rack", title: "Bamboo Spice Rack", price: "990.00", stock: "Out of stock" },
  { slug: "cast-pan", title: "Cast Iron Pan 26cm", price: "4200.00", stock: "In stock" },
  { slug: "rice-cooker", title: "Mini Rice Cooker", price: "5600.00", stock: "In stock" },
  { slug: "knife-block", title: "Five-Knife Block", price: "3999.00", stock: "In stock" },
  { slug: "glass-jars", title: "Glass Jar Set (4)", price: "1450.00", stock: "In stock" },
  { slug: "chai-mugs", title: "Chai Mugs, Pair", price: "799.00", stock: "In stock" },
  { slug: "wooden-board", title: "Walnut Cutting Board", price: "2650.00", stock: "Low stock" },
  { slug: "milk-pan", title: "Milk Pan with Spout", price: "1150.00", stock: "In stock" },
];

const iso = (minsAgo: number) => new Date(Date.now() - minsAgo * 60_000).toISOString();

export function starterFlow(): Flow {
  return {
    version: 1,
    variables: [],
    nodes: [
      { id: "n_trig01", type: "trigger", position: { x: 0, y: 0 }, config: { mode: "interval", every_minutes: 60, timezone: "Asia/Karachi" } },
      { id: "n_chk001", type: "check_page", position: { x: 0, y: 140 }, config: {} },
    ],
    edges: [{ id: "e_start", source: "n_trig01", target: "n_chk001" }],
  };
}

export function listTrackingFlow(): Flow {
  return {
    version: 4,
    variables: [],
    nodes: [
      { id: "n_t1aaaa", type: "trigger", position: { x: 0, y: 0 }, config: { mode: "interval", every_minutes: 60, timezone: "Asia/Karachi" } },
      { id: "n_f1aaaa", type: "fetch_page", position: { x: 0, y: 0 }, config: { url: SHOP } },
      { id: "n_p1aaaa", type: "paginate", position: { x: 0, y: 0 }, config: { next_selector: "a.next", max_pages: 3 } },
      {
        id: "n_e1aaaa", type: "extract_list", position: { x: 0, y: 0 },
        config: {
          base_selector: "div.product", identity_key: "url", page_anchor: "#product-grid",
          expected_count: { min: 10, max: 40 },
          fields: [
            { name: "title", selector: "h2", type: "text", required: true },
            { name: "price", selector: ".price", type: "price", required: true },
            { name: "url", selector: "a", attr: "href", type: "url", required: true },
            { name: "stock", selector: ".stock", type: "stock", required: false },
          ],
        },
      },
      { id: "n_k1aaaa", type: "check_page", position: { x: 0, y: 0 }, config: {} },
      { id: "n_s1aaaa", type: "save_records", position: { x: 0, y: 0 }, config: { dataset: "shop_prices", identity_key: "url", track_fields: ["price", "stock"], alert_on_first_run: false } },
      { id: "n_c1aaaa", type: "condition", position: { x: 0, y: 0 }, config: { match: "any", rules: [{ field: "change", op: "is_new" }] } },
      { id: "n_c2aaaa", type: "condition", position: { x: 0, y: 0 }, config: { match: "any", rules: [{ field: "price", op: "changed" }] } },
      { id: "n_a1aaaa", type: "alert", position: { x: 0, y: 0 }, config: { title: "New product", level: "info" } },
      { id: "n_a2aaaa", type: "alert", position: { x: 0, y: 0 }, config: { title: "Price changed", level: "warning" } },
    ],
    edges: [
      { id: "e1", source: "n_t1aaaa", target: "n_f1aaaa" },
      { id: "e2", source: "n_f1aaaa", target: "n_p1aaaa" },
      { id: "e3", source: "n_p1aaaa", target: "n_e1aaaa" },
      { id: "e4", source: "n_e1aaaa", target: "n_k1aaaa" },
      { id: "e5", source: "n_k1aaaa", target: "n_s1aaaa" },
      { id: "e6", source: "n_s1aaaa", target: "n_c1aaaa" },
      { id: "e7", source: "n_s1aaaa", target: "n_c2aaaa" },
      { id: "e8", source: "n_c1aaaa", sourceHandle: "true", target: "n_a1aaaa" },
      { id: "e9", source: "n_c2aaaa", sourceHandle: "true", target: "n_a2aaaa" },
    ],
  };
}

export function multiLinkFlow(): Flow {
  return {
    version: 7,
    variables: [
      { name: "watch_urls", type: "url_list", value: [`${SHOP}/p/blue-kettle`, `${SHOP}/p/steel-flask`, `${SHOP}/p/tea-set`] },
      { name: "min_drop_pct", type: "number", value: 1 },
    ],
    nodes: [
      { id: "n_t1bbbb", type: "trigger", position: { x: 0, y: 0 }, config: { mode: "interval", every_minutes: 60 } },
      { id: "n_l1bbbb", type: "for_each", position: { x: 0, y: 0 }, config: { source: { var: "watch_urls" }, max_items: 25, on_error: "skip" } },
      { id: "n_b1bbbb", type: "fetch_item_page", parentId: "n_l1bbbb", position: { x: 0, y: 0 }, config: { url_field: "url" } },
      {
        id: "n_b2bbbb", type: "extract_fields", parentId: "n_l1bbbb", position: { x: 0, y: 0 },
        config: {
          fields: [
            { name: "title", selector: "h1.product-title", type: "text", required: true },
            { name: "price", selector: ".price", type: "price", required: true },
          ],
        },
      },
      { id: "n_k1bbbb", type: "check_page", position: { x: 0, y: 0 }, config: {} },
      { id: "n_s1bbbb", type: "save_records", position: { x: 0, y: 0 }, config: { dataset: "watched_prices", identity_key: "url", track_fields: ["price"] } },
      { id: "n_c1bbbb", type: "condition", position: { x: 0, y: 0 }, config: { match: "all", rules: [{ field: "price", op: "drop_pct_gt", value: { var: "min_drop_pct" } }] } },
      { id: "n_a1bbbb", type: "alert", position: { x: 0, y: 0 }, config: { title: "Price dropped", level: "warning" } },
    ],
    edges: [
      { id: "f1", source: "n_t1bbbb", target: "n_l1bbbb" },
      { id: "f2", source: "n_l1bbbb", sourceHandle: "item", target: "n_b1bbbb" },
      { id: "f3", source: "n_b1bbbb", target: "n_b2bbbb" },
      { id: "f4", source: "n_b2bbbb", target: "n_l1bbbb", targetHandle: "next" },
      { id: "f5", source: "n_l1bbbb", sourceHandle: "done", target: "n_k1bbbb" },
      { id: "f6", source: "n_k1bbbb", target: "n_s1bbbb" },
      { id: "f7", source: "n_s1bbbb", target: "n_c1bbbb" },
      { id: "f8", source: "n_c1bbbb", sourceHandle: "true", target: "n_a1bbbb" },
    ],
  };
}

export type MockDb = {
  flows: (FlowDetail & { updated_at: string })[];
  runs: RunReport[];
  alerts: Alert[];
  datasets: { id: string; flow_id: string; name: string; identity_key: string; fields: string[] }[];
  records: (DataRecord & { dataset_id: string })[];
  history: Record<string, RecordChange[]>;
};

function productItems() {
  return PRODUCTS.map((p) => ({
    key: `${SHOP}/p/${p.slug}`,
    data: { title: p.title, price: p.price, url: `${SHOP}/p/${p.slug}`, stock: p.stock },
  }));
}

export function seedDb(): MockDb {
  const lt = listTrackingFlow();
  const ml = multiLinkFlow();
  const items = productItems();
  const kettle = items[0];

  const okRun = (id: string, minsAgo: number, extra: Partial<RunReport> = {}): RunReport => ({
    id, flow_id: "fl_prices", trigger: "schedule", verdict: "OK", reason: "12 items, nothing changed",
    started_at: iso(minsAgo), duration_ms: 3400 + (minsAgo % 7) * 110, items_found: 12, items_valid: 12,
    changes: { new: 0, changed: 0, removed: 0 }, ai_calls: 0,
    evidence: ["12 of 12 items have every required field", "Anchor #product-grid found on 2 of 2 pages"],
    http: [
      { url: SHOP, status: 200, body_size: 48211 },
      { url: `${SHOP}?page=2`, status: 200, body_size: 31877 },
    ],
    coverage: { title: 1, price: 1, url: 1, stock: 1 },
    node_trace: [
      { node_id: "n_t1aaaa", items_in: 0, items_out: 1, status: "ok" },
      { node_id: "n_f1aaaa", items_in: 1, items_out: 1, status: "ok" },
      { node_id: "n_p1aaaa", items_in: 1, items_out: 2, status: "ok", note: "2 pages" },
      { node_id: "n_e1aaaa", items_in: 2, items_out: 12, status: "ok" },
      { node_id: "n_k1aaaa", items_in: 12, items_out: 12, status: "ok" },
      { node_id: "n_s1aaaa", items_in: 12, items_out: 12, status: "ok" },
      { node_id: "n_c1aaaa", items_in: 12, items_out: 0, status: "ok" },
      { node_id: "n_c2aaaa", items_in: 12, items_out: 0, status: "ok" },
      { node_id: "n_a1aaaa", items_in: 0, items_out: 0, status: "skipped" },
      { node_id: "n_a2aaaa", items_in: 0, items_out: 0, status: "skipped" },
    ],
    items: items.map((i) => ({ ...i, change: "same" as const })),
    ...extra,
  });

  const changedRun = okRun("run_003", 62, {
    verdict: "CHANGED", reason: "1 price changed", changes: { new: 0, changed: 1, removed: 0 },
    items: items.map((i, idx) =>
      idx === 0
        ? { ...i, data: { ...i.data, price: "1099.00" }, change: "changed" as const, previous: { price: "1250.00" }, pct_change: { price: -12.1 } }
        : { ...i, change: "same" as const },
    ),
  });
  changedRun.node_trace = changedRun.node_trace.map((t) =>
    t.node_id === "n_c2aaaa" ? { ...t, items_out: 1 } : t.node_id === "n_a2aaaa" ? { ...t, items_in: 1, items_out: 1, status: "ok" } : t,
  );

  const brokenRun: RunReport = {
    ...okRun("run_004", 2),
    verdict: "BROKEN", reason: "Site layout changed: price missing on 12 of 12 items",
    items_valid: 0,
    evidence: ["price missing on 12 of 12 items", "Anchor #product-grid not found", "Last good run had 12 items"],
    coverage: { title: 1, price: 0, url: 1, stock: 0 },
    node_trace: [
      { node_id: "n_t1aaaa", items_in: 0, items_out: 1, status: "ok" },
      { node_id: "n_f1aaaa", items_in: 1, items_out: 1, status: "ok" },
      { node_id: "n_p1aaaa", items_in: 1, items_out: 2, status: "ok" },
      { node_id: "n_e1aaaa", items_in: 2, items_out: 12, status: "ok" },
      { node_id: "n_k1aaaa", items_in: 12, items_out: 0, status: "error", note: "BROKEN: stopped here" },
      { node_id: "n_s1aaaa", items_in: 0, items_out: 0, status: "skipped" },
      { node_id: "n_c1aaaa", items_in: 0, items_out: 0, status: "skipped" },
      { node_id: "n_c2aaaa", items_in: 0, items_out: 0, status: "skipped" },
      { node_id: "n_a1aaaa", items_in: 0, items_out: 0, status: "skipped" },
      { node_id: "n_a2aaaa", items_in: 0, items_out: 0, status: "skipped" },
    ],
    items: [],
  };

  const firstRun = okRun("run_001", 182, {
    trigger: "manual", verdict: "CHANGED", reason: "First run: 12 items saved as the baseline",
    changes: { new: 12, changed: 0, removed: 0 }, items: items.map((i) => ({ ...i, change: "new" as const })),
  });

  return {
    flows: [
      {
        id: "fl_prices", name: "Kitchen shop prices", status: "published",
        draft: lt, published: listTrackingFlow(), published_at: iso(190), updated_at: iso(190),
      },
      {
        id: "fl_watch", name: "Watch three product links", status: "draft",
        draft: ml, published: null, published_at: null, updated_at: iso(35),
      },
    ],
    runs: [brokenRun, changedRun, okRun("run_002", 122), firstRun],
    alerts: [
      {
        id: "al_3", flow_id: "fl_prices", run_id: "run_004", node_id: "n_k1aaaa", kind: "site_changed", level: "error",
        title: "Site changed", message: "Price is missing on 12 of 12 items. Your saved prices were kept. Check the selectors on Extract list.",
        items: [], created_at: iso(2), read: false,
      },
      {
        id: "al_2", flow_id: "fl_prices", run_id: "run_003", node_id: "n_a2aaaa", kind: "condition", level: "warning",
        title: "Price changed", message: "Blue Enamel Kettle: Rs 1,250 → Rs 1,099 (−12%)",
        items: [{ ...kettle, data: { ...kettle.data, price: "1099.00" }, change: "changed", previous: { price: "1250.00" }, pct_change: { price: -12.1 } }],
        created_at: iso(62), read: false,
      },
      {
        id: "al_1", flow_id: "fl_prices", run_id: "run_001", node_id: null, kind: "condition", level: "info",
        title: "Baseline saved", message: "First run saved 12 products. Alerts start from the next run.",
        items: [], created_at: iso(182), read: true,
      },
    ],
    datasets: [{ id: "ds_prices", flow_id: "fl_prices", name: "shop_prices", identity_key: "url", fields: ["title", "price", "url", "stock"] }],
    records: items.map((i, idx) => ({
      id: `rec_${idx}`, dataset_id: "ds_prices", key: i.key,
      data: idx === 0 ? { ...i.data, price: "1099.00" } : i.data,
      first_seen: iso(182), last_changed: idx === 0 ? iso(62) : null, removed_at: null,
    })),
    history: {
      rec_0: [
        { run_id: "run_003", at: iso(62), change: "changed", field: "price", old_value: "1250.00", new_value: "1099.00", pct_change: -12.1 },
        { run_id: "run_001", at: iso(182), change: "new", field: null, old_value: null, new_value: null, pct_change: null },
      ],
    },
  };
}
