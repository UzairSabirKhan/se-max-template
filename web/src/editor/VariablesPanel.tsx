import { AlertCircle, Braces, CheckCircle2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button, EmptyState, Field, IconButton, Input, Select, Textarea, Toggle } from "../components/ui";
import { useEditor } from "../store/editor";
import type { Flow, Variable, VariableType } from "../types/contracts";

const TYPES: { value: VariableType; label: string }[] = [
  { value: "url_list", label: "List of links" },
  { value: "url", label: "One link" },
  { value: "number", label: "Number" },
  { value: "price", label: "Price" },
  { value: "text", label: "Text" },
  { value: "text_list", label: "List of text" },
  { value: "boolean", label: "Yes / no" },
];

const defaultValue = (t: VariableType): unknown => (t === "url_list" || t === "text_list" ? [] : t === "boolean" ? false : t === "number" || t === "price" ? 0 : "");

function usages(flow: Flow, name: string) {
  return flow.nodes.filter((n) => JSON.stringify(n.config).includes(`{"var":"${name}"}`)).length;
}

function ListEditor({ v, onChange }: { v: Variable; onChange: (value: string[]) => void }) {
  const [text, setText] = useState(((v.value as string[]) ?? []).join("\n"));
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const isUrl = v.type === "url_list";
  const bad = isUrl ? lines.filter((l) => !/^https?:\/\/[^\s/]+\.?[^\s]*$/.test(l)) : lines.filter((l) => l.length > 200);
  const dupes = lines.length - new Set(lines).size;
  return (
    <div className="space-y-1.5">
      <Textarea
        mono
        rows={Math.min(8, Math.max(3, lines.length + 1))}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          const l = e.target.value.split("\n").map((x) => x.trim()).filter(Boolean);
          onChange([...new Set(l)].slice(0, 25));
        }}
        placeholder={isUrl ? "One link per line\nhttps://shop.example.com/p/kettle" : "One value per line"}
        invalid={bad.length > 0 || lines.length > 25}
      />
      <div className="space-y-0.5 text-[12px]">
        {bad.length === 0 && lines.length > 0 && lines.length <= 25 && (
          <p className="flex items-center gap-1 text-emerald-700"><CheckCircle2 className="size-3" /> {new Set(lines).size} {isUrl ? "links" : "values"} look fine{dupes ? ` · ${dupes} duplicate${dupes > 1 ? "s" : ""} removed` : ""}</p>
        )}
        {bad.map((b) => (
          <p key={b} className="flex items-start gap-1 break-all text-red-600"><AlertCircle className="mt-0.5 size-3 shrink-0" /> {isUrl ? `Not a web link: ${b}` : `Longer than 200 characters: ${b.slice(0, 40)}…`}</p>
        ))}
        {lines.length > 25 && <p className="text-red-600">At most 25. Only the first 25 are kept.</p>}
        {isUrl && <p className="text-muted">Every link is checked again before publishing; internal addresses are refused.</p>}
      </div>
    </div>
  );
}

function VariableCard({ v, flow }: { v: Variable; flow: Flow }) {
  const { setVariable, removeVariable } = useEditor.getState();
  const [name, setName] = useState(v.name);
  const used = usages(flow, v.name);
  const clash = name !== v.name && flow.variables.some((x) => x.name === name);
  return (
    <div className="space-y-3 rounded-xl border border-line bg-white p-3.5 shadow-card">
      <div className="flex items-center gap-2">
        <Braces className="size-4 text-brand-500" />
        <Input
          mono
          aria-label="Variable name"
          value={name}
          onChange={(e) => setName(e.target.value.replace(/[^a-z0-9_]/gi, "_").toLowerCase())}
          onBlur={() => {
            if (name && !clash && name !== v.name) setVariable({ ...v, name }, v.name);
            else setName(v.name);
          }}
          className="h-8 flex-1"
          invalid={clash}
        />
        <IconButton label="Delete variable" onClick={() => removeVariable(v.name)} className="hover:text-red-600"><Trash2 className="size-4" /></IconButton>
      </div>
      <div className="flex items-center gap-2">
        <Select aria-label="Variable type" value={v.type} onChange={(e) => setVariable({ ...v, type: e.target.value as VariableType, value: defaultValue(e.target.value as VariableType) })} className="h-8 flex-1">
          {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </Select>
        <span className={used ? "text-[12px] text-muted" : "text-[12px] text-amber-700"}>{used ? `Used in ${used} step${used > 1 ? "s" : ""}` : "Not used yet"}</span>
      </div>
      {v.type === "url_list" || v.type === "text_list" ? (
        <ListEditor v={v} onChange={(value) => setVariable({ ...v, value })} />
      ) : v.type === "boolean" ? (
        <Toggle label="Value" checked={!!v.value} onChange={(value) => setVariable({ ...v, value })} />
      ) : (
        <Input mono={v.type === "url"} type={v.type === "number" || v.type === "price" ? "number" : "text"} value={String(v.value ?? "")} onChange={(e) => setVariable({ ...v, value: v.type === "number" || v.type === "price" ? Number(e.target.value) : e.target.value })} aria-label="Value" />
      )}
    </div>
  );
}

export function VariablesPanel() {
  const draft = useEditor((s) => s.draft);
  const setVariable = useEditor((s) => s.setVariable);
  const add = () => {
    let i = 1;
    while (draft.variables.some((v) => v.name === `variable_${i}`)) i++;
    setVariable({ name: `variable_${i}`, type: "url_list", value: [] });
  };
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-4 py-3">
        <p className="text-[14.5px] font-semibold">Variables</p>
        <p className="text-[12.5px] text-muted">Your inputs: links to watch, a price limit, a percentage. Steps point to them with {"{name}"}.</p>
      </div>
      <div className="scroll-thin flex-1 space-y-3 overflow-y-auto bg-zinc-50/50 p-4">
        {draft.variables.length === 0 ? (
          <EmptyState icon={<Braces className="size-5" />} title="No variables yet" body="Ask the assistant “alert me when any of these prices drops: …” and it creates them, or add one here." />
        ) : (
          draft.variables.map((v) => <VariableCard key={v.name} v={v} flow={draft} />)
        )}
        <Field label="">
          <Button variant="secondary" icon={<Plus className="size-4" />} onClick={add} className="w-full">Add variable</Button>
        </Field>
        <p className="text-[12px] text-muted">Changing a variable is a draft edit. It goes live the next time you publish.</p>
      </div>
    </div>
  );
}
