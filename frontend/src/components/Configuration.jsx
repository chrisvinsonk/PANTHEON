import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  Building2,
  Cpu,
  Gavel,
  Landmark,
  LoaderCircle,
  Pencil,
  Plus,
  Shield,
  Trash2,
  UsersRound,
} from "lucide-react";
import {
  companyConstraints,
  companyFinancialAssumptions,
  companyPriorities,
  getCompany,
  getExecutives,
  getGovernance,
  updateCompany,
} from "../api";
import ModelSources from "./ModelSources";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const tabs = [
  ["company", "Company", Building2],
  ["executives", "Executive identities", UsersRound],
  ["models", "Models", Cpu],
  ["governance", "Governance", Gavel],
];

const priorityStatuses = [
  ["active", "Active"],
  ["paused", "Paused"],
  ["achieved", "Achieved"],
];
const severities = [
  ["high", "High"],
  ["medium", "Medium"],
  ["low", "Low"],
];

const priorityFields = [
  { name: "title", label: "Title", type: "text", required: true, placeholder: "What the company is trying to achieve" },
  { name: "description", label: "Description", type: "textarea", placeholder: "Why this matters now" },
  { name: "status", label: "Status", type: "select", options: priorityStatuses },
  { name: "target_date", label: "Target date", type: "date" },
];

const constraintFields = [
  { name: "label", label: "Constraint", type: "text", required: true, placeholder: "e.g. Runway discipline" },
  { name: "description", label: "Description", type: "textarea", placeholder: "What the council must respect" },
  { name: "severity", label: "Severity", type: "select", options: severities },
];

const assumptionFields = [
  { name: "label", label: "Assumption", type: "text", required: true, placeholder: "e.g. Monthly burn" },
  { name: "value", label: "Value", type: "text", placeholder: "e.g. 25000" },
  { name: "unit", label: "Unit", type: "text", placeholder: "e.g. USD / months" },
  { name: "note", label: "Note", type: "textarea", placeholder: "Where this assumption comes from" },
];

const blankDraft = (fields) =>
  Object.fromEntries(fields.map((field) => [field.name, field.type === "select" ? field.options[0][0] : ""]));

function Field({ field, value, onChange }) {
  const id = `field-${field.name}`;
  if (field.type === "textarea") {
    return (
      <div className="grid gap-2 sm:col-span-2">
        <Label htmlFor={id}>{field.label}</Label>
        <Textarea id={id} rows={2} value={value ?? ""} placeholder={field.placeholder} onChange={(event) => onChange(event.target.value)} />
      </div>
    );
  }
  if (field.type === "select") {
    return (
      <div className="grid gap-2">
        <Label htmlFor={id}>{field.label}</Label>
        <select
          id={id}
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value)}
          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
        >
          {field.options.map(([option, label]) => (
            <option key={option} value={option}>{label}</option>
          ))}
        </select>
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{field.label}</Label>
      <Input
        id={id}
        type={field.type === "date" ? "date" : "text"}
        value={value ?? ""}
        placeholder={field.placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function EntitySection({ title, description, items, fields, renderSummary, api, onChanged, onError, onNotice }) {
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState(blankDraft(fields));
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState("");

  const openCreate = () => {
    setDraft(blankDraft(fields));
    setEditorOpen(true);
  };
  const openEdit = (item) => {
    setDraft({ ...blankDraft(fields), ...item });
    setEditorOpen(true);
  };

  const save = async () => {
    setSaving(true);
    onError("");
    try {
      const token = await api.token();
      const body = Object.fromEntries(
        fields.map((field) => [field.name, draft[field.name] ? draft[field.name] : field.type === "date" ? null : ""]),
      );
      fields.forEach((field) => {
        if (field.type === "date") body[field.name] = draft[field.name] || null;
      });
      if (draft.id) {
        await api.update(draft.id, body, token);
        onNotice(`${title} updated.`);
      } else {
        await api.create(body, token);
        onNotice(`${title} added.`);
      }
      setEditorOpen(false);
      await onChanged();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item) => {
    const label = item.title || item.label || "item";
    if (!window.confirm(`Remove "${label}"?`)) return;
    setBusy(item.id);
    onError("");
    try {
      const token = await api.token();
      await api.remove(item.id, token);
      onNotice(`${title} removed.`);
      await onChanged();
    } catch (requestError) {
      onError(requestError.message);
    } finally {
      setBusy("");
    }
  };

  return (
    <Card className="border-border/70 bg-card/80">
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="font-heading text-xl">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={openCreate}>
          <Plus className="size-3.5" /> Add
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length ? (
          items.map((item) => (
            <div key={item.id} className="flex items-start justify-between gap-3 rounded-lg border border-border/60 bg-background/40 p-3">
              <div className="min-w-0 flex-1">{renderSummary(item)}</div>
              <div className="flex shrink-0 gap-1">
                <Button variant="ghost" size="icon" className="size-8" aria-label="Edit" onClick={() => openEdit(item)}>
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8 text-destructive hover:text-destructive"
                  aria-label="Remove"
                  disabled={busy === item.id}
                  onClick={() => remove(item)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">Nothing added yet.</p>
        )}
      </CardContent>

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-xl border-border/80 bg-card">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">
              {draft.id ? `Edit ${title.toLowerCase()}` : `Add ${title.toLowerCase()}`}
            </DialogTitle>
            <DialogDescription>This becomes part of the company context used by the council.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            {fields.map((field) => (
              <Field
                key={field.name}
                field={field}
                value={draft[field.name]}
                onChange={(value) => setDraft((current) => ({ ...current, [field.name]: value }))}
              />
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditorOpen(false)}>Cancel</Button>
            <Button
              onClick={save}
              disabled={saving || fields.some((field) => field.required && !String(draft[field.name] || "").trim())}
              className="gap-2"
            >
              {saving && <LoaderCircle className="size-4 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export default function Configuration() {
  const { getToken } = useAuth();
  const [activeTab, setActiveTab] = useState("company");
  const [company, setCompany] = useState(null);
  const [executives, setExecutives] = useState([]);
  const [governance, setGovernance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [form, setForm] = useState({ name: "", owner: "", stage: "", mission: "", strategic_context: "" });
  const [savingCompany, setSavingCompany] = useState(false);

  const accessToken = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    return token;
  };

  const loadCompany = async () => {
    const token = await accessToken();
    const next = await getCompany(token);
    setCompany(next);
    setForm({
      name: next.name || "",
      owner: next.owner || "",
      stage: next.stage || "",
      mission: next.mission || "",
      strategic_context: next.strategic_context || "",
    });
  };

  useEffect(() => {
    const load = async () => {
      try {
        const token = await accessToken();
        const [companyData, executiveData, governanceData] = await Promise.all([
          getCompany(token),
          getExecutives(token),
          getGovernance(token),
        ]);
        setCompany(companyData);
        setForm({
          name: companyData.name || "",
          owner: companyData.owner || "",
          stage: companyData.stage || "",
          mission: companyData.mission || "",
          strategic_context: companyData.strategic_context || "",
        });
        setExecutives(executiveData);
        setGovernance(governanceData);
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [getToken]);

  const saveCompany = async () => {
    setSavingCompany(true);
    setError("");
    try {
      const token = await accessToken();
      const next = await updateCompany(
        {
          name: form.name,
          owner: form.owner,
          stage: form.stage,
          mission: form.mission,
          strategic_context: form.strategic_context,
        },
        token,
      );
      setCompany(next);
      setNotice("Company context saved.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingCompany(false);
    }
  };

  const priorityApi = useMemo(() => ({ ...companyPriorities, token: accessToken }), []);
  const constraintApi = useMemo(() => ({ ...companyConstraints, token: accessToken }), []);
  const assumptionApi = useMemo(() => ({ ...companyFinancialAssumptions, token: accessToken }), []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading configuration…
      </div>
    );
  }

  return (
    <section className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Configuration request failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap gap-2">
        {tabs.map(([key, label, Icon]) => (
          <Button
            key={key}
            variant={activeTab === key ? "default" : "outline"}
            size="sm"
            className="gap-2"
            onClick={() => setActiveTab(key)}
          >
            <Icon className="size-3.5" /> {label}
          </Button>
        ))}
      </div>

      {activeTab === "company" && (
        <div className="space-y-6">
          <Card className="border-border/70 bg-card/80">
            <CardHeader>
              <CardTitle className="font-heading text-xl">Company identity</CardTitle>
              <CardDescription>
                The profile of the active company selected in the top bar. Switching companies switches this entire workspace.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="company-name">Company name</Label>
                <Input id="company-name" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="company-owner">Owner</Label>
                <Input id="company-owner" value={form.owner} onChange={(event) => setForm((current) => ({ ...current, owner: event.target.value }))} placeholder="Founder or accountable owner" />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="company-stage">Stage</Label>
                <Input id="company-stage" value={form.stage} onChange={(event) => setForm((current) => ({ ...current, stage: event.target.value }))} placeholder="e.g. pre-seed, seed, series-a" />
              </div>
              <div className="grid gap-2 sm:col-span-2">
                <Label htmlFor="company-mission">Mission</Label>
                <Textarea id="company-mission" rows={3} value={form.mission} onChange={(event) => setForm((current) => ({ ...current, mission: event.target.value }))} placeholder="Why this company exists" />
              </div>
              <div className="grid gap-2 sm:col-span-2">
                <Label htmlFor="company-context">Strategic context</Label>
                <Textarea id="company-context" rows={3} value={form.strategic_context} onChange={(event) => setForm((current) => ({ ...current, strategic_context: event.target.value }))} placeholder="Current situation, stage and strategic frame" />
              </div>
              <div className="sm:col-span-2">
                <Button onClick={saveCompany} disabled={savingCompany} className="gap-2">
                  {savingCompany && <LoaderCircle className="size-4 animate-spin" />} Save company context
                </Button>
              </div>
            </CardContent>
          </Card>

          <EntitySection
            title="Strategic priorities"
            description="What the company is actively pursuing. Injected into every council run."
            items={company?.strategic_priorities || []}
            fields={priorityFields}
            api={priorityApi}
            onChanged={loadCompany}
            onError={setError}
            onNotice={setNotice}
            renderSummary={(item) => (
              <>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium leading-6 text-foreground">{item.title}</p>
                  <Badge variant="outline" className="capitalize">{item.status}</Badge>
                </div>
                {item.description && <p className="mt-1 text-sm leading-5 text-muted-foreground">{item.description}</p>}
                {item.target_date && <p className="mt-1 font-mono text-[10px] text-muted-foreground">TARGET {item.target_date}</p>}
              </>
            )}
          />

          <EntitySection
            title="Constraints"
            description="Hard limits the council must respect when recommending action."
            items={company?.constraints || []}
            fields={constraintFields}
            api={constraintApi}
            onChanged={loadCompany}
            onError={setError}
            onNotice={setNotice}
            renderSummary={(item) => (
              <>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium leading-6 text-foreground">{item.label}</p>
                  <Badge variant="outline" className="capitalize">{item.severity}</Badge>
                </div>
                {item.description && <p className="mt-1 text-sm leading-5 text-muted-foreground">{item.description}</p>}
              </>
            )}
          />

          <EntitySection
            title="Financial assumptions"
            description="The numbers the council should reason against until superseded."
            items={company?.financial_assumptions || []}
            fields={assumptionFields}
            api={assumptionApi}
            onChanged={loadCompany}
            onError={setError}
            onNotice={setNotice}
            renderSummary={(item) => (
              <>
                <p className="text-sm font-medium leading-6 text-foreground">
                  {item.label}
                  {(item.value || item.unit) && (
                    <span className="ml-2 font-mono text-xs text-primary">
                      {[item.value, item.unit].filter(Boolean).join(" ")}
                    </span>
                  )}
                </p>
                {item.note && <p className="mt-1 text-sm leading-5 text-muted-foreground">{item.note}</p>}
              </>
            )}
          />
        </div>
      )}

      {activeTab === "executives" && (
        <div className="grid gap-4 sm:grid-cols-2">
          {executives.map((executive) => (
            <Card key={executive.role} className="border-border/70 bg-card/80">
              <CardHeader className="flex-row items-start gap-4 space-y-0 p-5">
                <span className="grid size-11 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                  {executive.role === "CFO" ? <Landmark className="size-5" /> : executive.role === "CTO" ? <Shield className="size-5" /> : executive.role === "CSO" ? <Gavel className="size-5" /> : <UsersRound className="size-5" />}
                </span>
                <div className="min-w-0 flex-1">
                  <CardTitle className="font-heading text-lg tracking-wide">{executive.role}</CardTitle>
                  <CardDescription className="mt-1">{executive.title}</CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 px-5 pb-5">
                <p className="text-sm leading-6 text-muted-foreground">{executive.mandate}</p>
                <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.12em] text-primary">
                  GOVERNANCE-DEFINED IDENTITY
                </Badge>
              </CardContent>
            </Card>
          ))}
          {!executives.length && <p className="text-sm text-muted-foreground">No executives configured.</p>}
        </div>
      )}

      {activeTab === "models" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Connect inference providers and choose the model each council role uses.
          </p>
          <ModelSources />
        </div>
      )}

      {activeTab === "governance" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="border-border/70 bg-card/80">
            <CardHeader>
              <CardTitle className="font-heading text-xl">Operating policy</CardTitle>
              <CardDescription>How authority and limits are enforced.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(governance?.policy || {}).map(([key, value]) => (
                <div key={key} className="rounded-md border border-border/60 bg-background/40 p-2.5">
                  <p className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{key.replaceAll("_", " ")}</p>
                  <p className="mt-1 text-sm text-foreground">{value}</p>
                </div>
              ))}
              <div className="flex flex-wrap gap-1 pt-1">
                {Object.entries(governance?.counts || {}).map(([action, count]) => (
                  <Badge key={action} variant="secondary" className="capitalize">{action}: {count}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 lg:col-span-2">
            <CardHeader>
              <CardTitle className="font-heading text-xl">Approval history</CardTitle>
              <CardDescription>Founder actions recorded against council recommendations.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {(governance?.events || []).length ? (
                governance.events.map((event) => (
                  <div key={event.id} className="rounded-lg border border-border/60 bg-background/40 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="capitalize">{event.action}</Badge>
                        <span className="truncate text-sm text-foreground">{event.meeting_title}</span>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {new Date(event.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">Actor: {event.actor}</p>
                    {event.comments && <p className="mt-1 text-sm leading-5 text-muted-foreground">{event.comments}</p>}
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No approval events recorded yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </section>
  );
}
