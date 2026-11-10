import clsx from "clsx";
import { AlertCircle, Braces, ChevronLeft, ChevronRight, FlaskConical, Info, Lock, Plus, Trash2, X } from "lucide-react";
import type { ReactNode } from "react";
import { Button, Field, IconButton, Input, Segmented, Select, Toggle } from "../components/ui";
import { isVarRef, knownFields, stepNumbers } from "../lib/flow";
import { NODE_META, TONE } from "../lib/nodeMeta";
import { useEditor, useIssues } from "../store/editor";
import type { Flow, FlowNode, Issue, VariableType } from "../types/contracts";
import { DataPanel } from "./DataPanel";
import { sampleText, useStepData } from "./useStepData";

type StepData = ReturnType<typeof useStepData>;

const FIELD_TYPES = ["text", "price", "int", "url", "date", "stock"] as const;

const OP_LABEL: Record<string, string> = {
  lt: "is less than", lte: "is at most", gt: "is more than", gte: "is at least", eq: "equals", neq: "doesn't equal",
  contains: "contains", not_contains: "doesn't contain", is_empty: "is empty", not_empty: "is not empty",
  in_stock: "is in stock", out_of_stock: "is out of stock", back_in_stock: "is back in stock",
  is_new: "is new", is_removed: "was removed", changed: "changed", increased: "went up", decreased: "went down",
  drop_pct_gt: "dropped by more than (%)", rise_pct_gt: "rose by more than (%)",
};
const NEEDS_VALUE = new Set(["lt", "lte", "gt", "gte", "eq", "neq", "contains", "not_contains", "drop_pct_gt", "rise_pct_gt"]);

function opsFor(fieldType: string, tracked: boolean) {
  if (fieldType === "change") return ["is_new", "is_removed"];
  const base =
    fieldType === "price" || fieldType === "int"
      ? ["lt", "lte", "gt", "gte", "eq", "neq"]
      : fieldType === "stock"
        ? ["in_stock", "out_of_stock", "back_in_stock"]
        : ["eq", "neq", "contains", "not_contains"];
  const change = tracked ? (fieldType === "price" || fieldType === "int" ? ["changed", "increased", "decreased", "drop_pct_gt", "rise_pct_gt"] : ["changed"]) : [];
  return [...change, ...base, "is_empty", "not_empty"];
}

function errFor(issues: Issue[], path: string) {
  return issues.find((i) => i.path === path || i.path.startsWith(path + "["))?.message;
}

/** Text/number input that can be switched to a {var} reference (only allowed spots, per design.md). */
function ValueOrVar({ value, onChange, flow, types, placeholder, mono, inputType = "text", invalid }: { value: any; onChange: (v: any) => void; flow: Flow; types: VariableType[]; placeholder?: string; mono?: boolean; inputType?: string; invalid?: boolean }) {
  const vars = flow.variables.filter((v) => types.includes(v.type));
  if (isVarRef(value))
    return (
      <div className="flex gap-1.5">
        <Select value={value.var} onChange={(e) => onChange({ var: e.target.value })} className="flex-1 font-mono text-[12.5px]" aria-label="Variable">
          {!vars.some((v) => v.name === value.var) && <option value={value.var}>{value.var} (missing)</option>}
          {vars.map((v) => (
            <option key={v.name} value={v.name}>{`{${v.name}}`} · {v.type}</option>
          ))}
        </Select>
        <IconButton label="Type a value instead" onClick={() => onChange("")}><X className="size-4" /></IconButton>
      </div>
    );
  return (
    <div className="flex gap-1.5">
      <Input value={value ?? ""} type={inputType} onChange={(e) => onChange(inputType === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)} placeholder={placeholder} mono={mono} invalid={invalid} className="flex-1" />
      <IconButton label={vars.length ? "Use a variable" : `No ${types.join(" / ")} variables yet`} disabled={!vars.length} onClick={() => onChange({ var: vars[0].name })} className="border border-line">
        <Braces className="size-3.5" />
      </IconButton>
    </div>
  );
}

function FieldsEditor({ node, set, issues, withAttr = true }: { node: FlowNode; set: (patch: Record<string, any>) => void; issues: Issue[]; withAttr?: boolean }) {
  const fields: any[] = node.config.fields ?? [];
  const update = (i: number, patch: Record<string, any>) => set({ fields: fields.map((f, j) => (j === i ? { ...f, ...patch } : f)) });
  return (
    <div className="space-y-2">
      {fields.map((f, i) => {
        const selErr = errFor(issues, `config.fields[${i}].selector`);
        const nameErr = errFor(issues, `config.fields[${i}].name`);
        return (
          <div key={i} className={clsx("rounded-lg border bg-zinc-50/60 p-2.5", selErr || nameErr ? "border-red-300" : "border-line")}>
            <div className="flex gap-1.5">
              <Input value={f.name} onChange={(e) => update(i, { name: e.target.value.replace(/\s+/g, "_").toLowerCase() })} placeholder="field_name" aria-label="Field name" className="h-8 flex-1" invalid={!!nameErr} />
              <Select value={f.type} onChange={(e) => update(i, { type: e.target.value })} className="h-8 w-[92px]" aria-label="Field type">
                {FIELD_TYPES.map((t) => <option key={t}>{t}</option>)}
              </Select>
              <IconButton label="Remove field" onClick={() => set({ fields: fields.filter((_, j) => j !== i) })} className="size-8 hover:text-red-600"><Trash2 className="size-3.5" /></IconButton>
            </div>
            <div className="mt-1.5 flex gap-1.5">
              <Input value={f.selector} onChange={(e) => update(i, { selector: e.target.value })} placeholder="CSS selector, e.g. .price" aria-label="Selector" mono className="h-8 flex-1" invalid={!!selErr} />
              {withAttr && <Input value={f.attr ?? ""} onChange={(e) => update(i, { attr: e.target.value || undefined })} placeholder="attr" aria-label="Attribute (optional)" mono className="h-8 w-[72px]" />}
            </div>
            <label className="mt-1.5 flex items-center gap-1.5 text-[12px] text-muted">
              <input type="checkbox" checked={!!f.required} onChange={(e) => update(i, { required: e.target.checked })} className="accent-brand-600" />
              Required: a missing value marks the run as broken
            </label>
            {(selErr || nameErr) && <p className="mt-1 text-[12px] text-red-600">{selErr || nameErr}</p>}
          </div>
        );
      })}
      <Button size="sm" variant="soft" icon={<Plus className="size-3.5" />} onClick={() => set({ fields: [...fields, { name: "", selector: "", type: "text", required: false }] })}>
        Add field
      </Button>
    </div>
  );
}

function ConditionEditor({ node, set, flow, issues, upstream }: { node: FlowNode; set: (p: Record<string, any>) => void; flow: Flow; issues: Issue[]; upstream?: StepData }) {
  const rules: any[] = node.config.rules ?? [];
  // Only fields from EARLIER steps (data selector); the whole-flow list is a fallback while it loads.
  const fields: { name: string; type: string; sample?: unknown; ops?: string[] }[] = upstream?.data ? upstream.fields : knownFields(flow);
  const tracked = new Set<string>(flow.nodes.filter((n) => n.type === "save_records").flatMap((n) => n.config.track_fields ?? []));
  const hasSave = upstream?.data ? upstream.hasChange : flow.nodes.some((n) => n.type === "save_records");
  const typeOf = (f: string) => (f === "change" ? "change" : fields.find((x) => x.name === f)?.type ?? "text");
  const opsOf = (f: string) => {
    const fromServer = fields.find((x) => x.name === f)?.ops;
    return f !== "change" && fromServer?.length ? fromServer : opsFor(typeOf(f), tracked.has(f));
  };
  const update = (i: number, patch: Record<string, any>) => set({ rules: rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  return (
    <div className="space-y-3">
      <Field label="Pass items when">
        <Segmented value={node.config.match ?? "all"} onChange={(v) => set({ match: v })} options={[{ value: "all", label: "All rules match" }, { value: "any", label: "Any rule matches" }]} />
      </Field>
      <div className="space-y-2">
        {rules.map((r, i) => {
          const ft = typeOf(r.field);
          const ops = opsOf(r.field);
          return (
            <div key={i} className="space-y-1.5 rounded-lg border border-line bg-zinc-50/60 p-2.5">
              <div className="flex gap-1.5">
                <Select value={r.field} onChange={(e) => update(i, { field: e.target.value, op: opsOf(e.target.value)[0], value: undefined })} className="h-8 flex-1" aria-label="Field">
                  {hasSave && <option value="change">change (new / removed)</option>}
                  {fields.map((f) => <option key={f.name} value={f.name}>{f.name} · {f.type}{sampleText(f.sample) ? ` · e.g. ${sampleText(f.sample)}` : ""}</option>)}
                  {!fields.some((f) => f.name === r.field) && r.field !== "change" && <option value={r.field}>{r.field || "pick a field"}</option>}
                </Select>
                <IconButton label="Remove rule" onClick={() => set({ rules: rules.filter((_, j) => j !== i) })} className="size-8 hover:text-red-600"><Trash2 className="size-3.5" /></IconButton>
              </div>
              <Select value={r.op} onChange={(e) => update(i, { op: e.target.value, value: NEEDS_VALUE.has(e.target.value) ? r.value : undefined })} className="h-8" aria-label="Operator">
                {ops.map((o) => <option key={o} value={o}>{OP_LABEL[o] ?? o}</option>)}
              </Select>
              {NEEDS_VALUE.has(r.op) && (
                <ValueOrVar value={r.value} onChange={(v) => update(i, { value: v })} flow={flow} types={ft === "price" || ft === "int" || r.op.endsWith("pct_gt") ? ["number", "price"] : ["text"]} inputType={ft === "price" || ft === "int" || r.op.endsWith("pct_gt") ? "number" : "text"} placeholder="value" />
              )}
              {r.field !== "change" && !tracked.has(r.field) && ["changed", "increased", "decreased", "drop_pct_gt", "rise_pct_gt"].includes(r.op) && (
                <p className="text-[12px] text-amber-700">Add “{r.field}” to the tracked fields in Save records.</p>
              )}
            </div>
          );
        })}
        {errFor(issues, "config.rules") && <p className="text-[12px] text-red-600">{errFor(issues, "config.rules")}</p>}
        <Button size="sm" variant="soft" icon={<Plus className="size-3.5" />} onClick={() => set({ rules: [...rules, { field: hasSave ? "change" : fields[0]?.name ?? "", op: hasSave ? "is_new" : "not_empty" }] })}>
          Add rule
        </Button>
      </div>
      <p className="rounded-lg bg-zinc-50 p-2.5 text-[12px] leading-snug text-muted">Items that match go out the <strong className="text-emerald-700">true</strong> handle, the rest out <strong>false</strong>. An output with no link drops those items.</p>
    </div>
  );
}

function Form({ node, flow, issues, upstream }: { node: FlowNode; flow: Flow; issues: Issue[]; upstream?: StepData }) {
  const updateConfig = useEditor((s) => s.updateConfig);
  const c = node.config;
  const set = (patch: Record<string, any>) => updateConfig(node.id, { ...c, ...patch });
  const e = (k: string) => errFor(issues, `config.${k}`);
  const fields: { name: string; type: string }[] = upstream?.data ? upstream.fields : knownFields(flow);

  switch (node.type) {
    case "trigger":
      return (
        <div className="space-y-4">
          <Field label="Run this flow">
            <Segmented value={c.mode ?? "interval"} onChange={(v) => set({ mode: v })} options={[{ value: "manual", label: "Manually" }, { value: "interval", label: "Every…" }, { value: "daily", label: "Daily" }]} />
          </Field>
          {c.mode === "interval" && (
            <Field label="Every (minutes)" required hint="At least 1 minute. 60 is a good default for price tracking." error={e("every_minutes")}>
              <Input type="number" min={1} value={c.every_minutes ?? 60} onChange={(ev) => set({ every_minutes: Math.max(1, Number(ev.target.value)) })} />
            </Field>
          )}
          {c.mode === "daily" && (
            <>
              <Field label="At" required error={e("at_time")}>
                <Input type="time" value={c.at_time ?? "09:00"} onChange={(ev) => set({ at_time: ev.target.value })} />
              </Field>
              <Field label="Time zone">
                <Select value={c.timezone ?? "Asia/Karachi"} onChange={(ev) => set({ timezone: ev.target.value })}>
                  {["Asia/Karachi", "UTC", "Asia/Dubai", "Europe/London", "America/New_York"].map((t) => <option key={t}>{t}</option>)}
                </Select>
              </Field>
            </>
          )}
          <Note>Changes take effect when you publish. “Run now” works in every mode.</Note>
        </div>
      );
    case "fetch_page":
      return (
        <div className="space-y-4">
          <Field label="Page URL" required error={e("url")} hint="http or https only. Private and internal addresses are always refused.">
            <ValueOrVar value={c.url} onChange={(v) => set({ url: v })} flow={flow} types={["url"]} placeholder="https://example.com/products" mono invalid={!!e("url")} />
          </Field>
          <Note>We fetch plain HTML and don't run JavaScript. Pages that build themselves in the browser show as “Unsupported”.</Note>
        </div>
      );
    case "paginate":
      return (
        <div className="space-y-4">
          <Field label="Next-page link selector" required error={e("next_selector")}>
            <Input mono value={c.next_selector ?? ""} onChange={(ev) => set({ next_selector: ev.target.value })} placeholder="a.next" />
          </Field>
          <Field label="Max pages" hint="1 to 5" error={e("max_pages")}>
            <Input type="number" min={1} max={5} value={c.max_pages ?? 3} onChange={(ev) => set({ max_pages: Math.min(5, Math.max(1, Number(ev.target.value))) })} />
          </Field>
        </div>
      );
    case "extract_list":
      return (
        <div className="space-y-4">
          <Field label="Item selector" required error={e("base_selector")} hint="The box around one product or article. Fields are read inside it.">
            <Input mono value={c.base_selector ?? ""} onChange={(ev) => set({ base_selector: ev.target.value })} placeholder="div.product" invalid={!!e("base_selector")} />
          </Field>
          <Field label="Fields" required error={e("fields") && !(c.fields ?? []).length ? e("fields") : undefined}>
            <FieldsEditor node={node} set={set} issues={issues} />
          </Field>
          <Field label="Identity field" required error={e("identity_key")} hint="Tells items apart between runs. A URL or SKU works best.">
            <Select value={c.identity_key ?? ""} onChange={(ev) => set({ identity_key: ev.target.value })}>
              <option value="">Pick a field</option>
              {(c.fields ?? []).filter((f: any) => f.name).map((f: any) => <option key={f.name}>{f.name}</option>)}
            </Select>
          </Field>
          <details className="group rounded-lg border border-line">
            <summary className="cursor-pointer select-none px-3 py-2 text-[13px] font-medium">Breakage checks <span className="font-normal text-muted">(set at publish)</span></summary>
            <div className="space-y-3 border-t border-line p-3">
              <Field label="Page anchor" hint="An element that should always be there. If it disappears, the run is marked broken.">
                <Input mono value={c.page_anchor ?? ""} onChange={(ev) => set({ page_anchor: ev.target.value || undefined })} placeholder="#product-grid" />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Expect at least">
                  <Input type="number" value={c.expected_count?.min ?? ""} onChange={(ev) => set({ expected_count: { ...c.expected_count, min: Number(ev.target.value) } })} />
                </Field>
                <Field label="At most">
                  <Input type="number" value={c.expected_count?.max ?? ""} onChange={(ev) => set({ expected_count: { ...c.expected_count, max: Number(ev.target.value) } })} />
                </Field>
              </div>
            </div>
          </details>
        </div>
      );
    case "extract_fields":
      return (
        <div className="space-y-4">
          <Field label="Fields" required error={!(c.fields ?? []).length ? e("fields") : undefined} hint="Selectors apply to the whole item page, so one page gives one item.">
            <FieldsEditor node={node} set={set} issues={issues} />
          </Field>
        </div>
      );
    case "fetch_item_page":
      return (
        <Field label="Link field" required hint="The item's URL field to open. Every link goes through the same safety checks." error={e("url_field")}>
          <Select value={c.url_field ?? "url"} onChange={(ev) => set({ url_field: ev.target.value })}>
            {[...new Set(["url", ...fields.filter((f) => f.type === "url").map((f) => f.name)])].map((f) => <option key={f}>{f}</option>)}
          </Select>
        </Field>
      );
    case "for_each": {
      const listVars = flow.variables.filter((v) => v.type === "url_list" || v.type === "text_list");
      return (
        <div className="space-y-4">
          <Field label="Loop over">
            <Select value={isVarRef(c.source) ? c.source.var : "items"} onChange={(ev) => set({ source: ev.target.value === "items" ? "items" : { var: ev.target.value } })}>
              <option value="items">Items from the previous step</option>
              {listVars.map((v) => <option key={v.name} value={v.name}>{`{${v.name}}`} · {Array.isArray(v.value) ? v.value.length : 0} links</option>)}
            </Select>
          </Field>
          <Field label="Max items" hint="1 to 25. Extra items pass through untouched and the run report says so.">
            <Input type="number" min={1} max={25} value={c.max_items ?? 25} onChange={(ev) => set({ max_items: Math.min(25, Math.max(1, Number(ev.target.value))) })} />
          </Field>
          <Field label="If one item fails">
            <Segmented value={c.on_error ?? "skip"} onChange={(v) => set({ on_error: v })} options={[{ value: "skip", label: "Skip it" }, { value: "stop", label: "Stop the run" }]} />
          </Field>
          <Note>Items run one at a time, in page order. If half or more fail, the run is broken and nothing is saved.</Note>
        </div>
      );
    }
    case "check_page":
      return (
        <div className="space-y-3">
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-[13px] leading-snug text-amber-900">
            <Lock className="mt-0.5 size-4 shrink-0" />
            <p>This step is required and can't be removed. It judges every page fetched in a run.</p>
          </div>
          <ul className="space-y-1.5 text-[13px] text-zinc-700">
            {[
              ["Blocked", "captcha, 403/429, timeouts"],
              ["Unsupported", "the page needs JavaScript"],
              ["Broken", "required fields missing, anchor gone, item count off"],
            ].map(([k, v]) => (
              <li key={k} className="flex gap-2"><span className="w-24 shrink-0 font-medium">{k}</span><span className="text-muted">{v}</span></li>
            ))}
          </ul>
          <Note>If any of these happen, nothing after this step runs, your saved data is kept, and you get a system alert.</Note>
        </div>
      );
    case "save_records":
      return (
        <div className="space-y-4">
          <Field label="Dataset name" required error={e("dataset")} hint="Unique in this flow. Shown in the Data tab and on the Data page.">
            <Input mono value={c.dataset ?? ""} onChange={(ev) => set({ dataset: ev.target.value.replace(/\s+/g, "_").toLowerCase() })} placeholder="shop_prices" invalid={!!e("dataset")} />
          </Field>
          <Field label="Identity field" hint="Defaults to the list's identity field. Use url after a loop over links.">
            <Select value={c.identity_key ?? ""} onChange={(ev) => set({ identity_key: ev.target.value || undefined })}>
              <option value="">Same as the list</option>
              {fields.map((f) => <option key={f.name}>{f.name}</option>)}
            </Select>
          </Field>
          <Field label="Track changes in" hint="Only these fields create “changed” labels and history.">
            <div className="flex flex-wrap gap-1.5">
              {fields.map((f) => {
                const on = (c.track_fields ?? []).includes(f.name);
                return (
                  <button key={f.name} onClick={() => set({ track_fields: on ? c.track_fields.filter((x: string) => x !== f.name) : [...(c.track_fields ?? []), f.name] })} className={clsx("rounded-full border px-2.5 py-0.5 text-[12.5px] font-medium", on ? "border-brand-300 bg-brand-50 text-brand-700" : "border-line text-zinc-600 hover:bg-zinc-50")}>
                    {f.name}
                  </button>
                );
              })}
              {!fields.length && <span className="text-[12.5px] text-muted">Add fields to an extract step first.</span>}
            </div>
          </Field>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[13px] font-semibold">Alert on the first run</p>
              <p className="text-[12px] leading-snug text-muted">Off: the first run only saves a baseline, so you don't get an alert for every item.</p>
            </div>
            <Toggle label="Alert on the first run" checked={!!c.alert_on_first_run} onChange={(v) => set({ alert_on_first_run: v })} />
          </div>
          <Note>Prices that move more than 50% in one run are held as “suspect” until you confirm.</Note>
        </div>
      );
    case "condition":
      return <ConditionEditor node={node} set={set} flow={flow} issues={issues} upstream={upstream} />;
    case "wait":
      return (
        <Field label="Seconds" hint="1 to 10. Requests to one site are already spaced at least 2 s apart.">
          <ValueOrVar value={c.seconds} onChange={(v) => set({ seconds: typeof v === "number" ? Math.min(10, Math.max(1, v)) : v })} flow={flow} types={["number"]} inputType="number" />
        </Field>
      );
    case "alert":
      return (
        <div className="space-y-4">
          <Field label="Title" required error={e("title")}>
            <Input value={c.title ?? ""} onChange={(ev) => set({ title: ev.target.value })} placeholder="Price dropped" invalid={!!e("title")} />
          </Field>
          <Field label="Level">
            <Segmented value={c.level ?? "info"} onChange={(v) => set({ level: v })} options={[{ value: "info", label: "Info" }, { value: "warning", label: "Warning" }]} />
          </Field>
          <Note>The message is written from the changes, for example “Blue Kettle: Rs 1,250 → Rs 1,099 (−12%)”.</Note>
        </div>
      );
    case "results":
      return (
        <Field label="Table name" required error={e("name")}>
          <Input mono value={c.name ?? ""} onChange={(ev) => set({ name: ev.target.value })} />
        </Field>
      );
    default:
      return <Note>This step needs a real browser. It's shown so you can plan ahead, but flows with it can't be published yet.</Note>;
  }
}

const Note = ({ children }: { children: ReactNode }) => (
  <div className="flex gap-2 rounded-lg border border-line bg-zinc-50/60 p-3 text-[12.5px] leading-snug text-zinc-600">
    <Info className="mt-px size-3.5 shrink-0 text-zinc-400" />
    <div>{children}</div>
  </div>
);

export function SettingsPanel({ onTestNode }: { onTestNode: (id: string) => void }) {
  const draft = useEditor((s) => s.draft);
  const selectedId = useEditor((s) => s.selectedId);
  const allIssues = useIssues();
  const select = useEditor((s) => s.select);
  const removeNode = useEditor((s) => s.removeNode);
  const stepData = useStepData(selectedId);
  const node = draft.nodes.find((n) => n.id === selectedId);
  if (!node) return null;
  const meta = NODE_META[node.type];
  const steps = stepNumbers(draft);
  const order = [...draft.nodes].sort((a, b) => steps[a.id] - steps[b.id]);
  const idx = order.findIndex((n) => n.id === node.id);
  const issues = allIssues.filter((i) => i.node_id === node.id);
  const unplaced = issues.filter((i) => !/^config\./.test(i.path) || i.path === "config.fields" || i.path === "config.rules");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
        <div className={clsx("flex size-9 shrink-0 items-center justify-center rounded-lg", TONE[meta.tone].tile)}>
          <meta.icon className="size-[18px]" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14.5px] font-semibold">{steps[node.id]}. {meta.label}</p>
          <p className="truncate font-mono text-[11px] text-zinc-400">{node.id}</p>
        </div>
        <IconButton label="Previous step" disabled={idx <= 0} onClick={() => select(order[idx - 1].id)}><ChevronLeft className="size-4" /></IconButton>
        <IconButton label="Next step" disabled={idx >= order.length - 1} onClick={() => select(order[idx + 1].id)}><ChevronRight className="size-4" /></IconButton>
        <IconButton label="Close settings" onClick={() => select(null)}><X className="size-4" /></IconButton>
      </div>
      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto p-4">
        {unplaced.length > 0 && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3">
            {unplaced.map((i, k) => (
              <p key={k} className="flex items-start gap-1.5 text-[12.5px] text-red-700"><AlertCircle className="mt-0.5 size-3.5 shrink-0" />{i.message}</p>
            ))}
          </div>
        )}
        <p className="text-[13px] text-muted">{meta.blurb}.</p>
        {!["trigger", "fetch_page", "extract_list"].includes(node.type) && <DataPanel data={stepData} />}
        <Form node={node} flow={draft} issues={issues} upstream={stepData} />
      </div>
      <div className="flex gap-2 border-t border-line p-3">
        {node.type !== "trigger" && !meta.disabled && (
          <button onClick={() => onTestNode(node.id)} className="flex h-10 flex-1 items-center justify-center gap-2 rounded-lg border border-brand-200 bg-brand-50 text-[13.5px] font-medium text-brand-700 hover:bg-brand-100">
            <FlaskConical className="size-4" /> Test up to this step
          </button>
        )}
        {node.type !== "trigger" && node.type !== "check_page" && (
          <button onClick={() => removeNode(node.id)} title="Delete this step" className="flex h-10 items-center justify-center gap-2 rounded-lg border border-red-200 bg-white px-4 text-[13.5px] font-medium text-red-600 hover:bg-red-50">
            <Trash2 className="size-4" /> Delete
          </button>
        )}
      </div>
    </div>
  );
}
