import { useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  AlertCircle,
  BookOpen,
  Check,
  ExternalLink,
  LoaderCircle,
  Pencil,
  Plus,
  Search,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import {
  companyKnowledge,
  createEvidenceRecord,
  deleteEvidenceRecord,
  getCompany,
  getEvidenceRecords,
  getResearchSettings,
  searchResearchSources,
  updateEvidenceRecord,
  updateTavilyKey,
} from "../api";
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

const categories = [
  ["scientific", "Scientific"],
  ["technical", "Technical"],
  ["financial", "Financial"],
  ["commercial", "Commercial"],
  ["regulatory", "Regulatory"],
  ["operational", "Operational"],
];
const classifications = [
  ["unknown", "Unknown"],
  ["founder-provided", "Founder-provided"],
  ["assumption", "Assumption"],
  ["estimate", "Estimate"],
  ["hypothesis", "Hypothesis"],
  ["verified", "Verified"],
];
const qualities = [
  ["unassessed", "Unassessed"],
  ["low", "Low"],
  ["moderate", "Moderate"],
  ["high", "High"],
];
const executives = ["CEO", "CFO", "CTO", "CSO"];
const researchProviders = [
  ["pubmed", "PubMed"],
  ["clinicaltrials", "ClinicalTrials.gov"],
  ["openfda", "FDA 510(k)"],
  ["tavily", "Web search"],
];

const blankDraft = () => ({
  claim: "",
  category: "scientific",
  classification: "unknown",
  source_provider: "manual",
  source_title: "",
  source_reference: "",
  source_url: "",
  publication_date: "",
  retrieved_at: "",
  evidence_quality: "unassessed",
  limitations: "",
  source_excerpt: "",
  relying_executives: [],
  challenged: false,
  challenged_by: [],
  disputed: false,
  disputed_by: [],
  dispute_notes: "",
  verification_note: "",
  meeting_ids: [],
});

function SelectField({ id, label, value, options, onChange }) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
      >
        {options.map(([option, title]) => (
          <option value={option} key={option}>{title}</option>
        ))}
      </select>
    </div>
  );
}

function RecordEditor({ open, onOpenChange, draft, setDraft, meetings, onSave, saving }) {
  const isLockedMeeting = (meetingId) => {
    const meeting = meetings.find((item) => item.id === meetingId);
    return meeting && meeting.status !== "draft";
  };
  const toggleArrayValue = (field, value) => {
    setDraft((current) => ({
      ...current,
      [field]: current[field].includes(value)
        ? current[field].filter((item) => item !== value)
        : [...current[field], value],
    }));
  };
  const update = (field, value) => setDraft((current) => ({ ...current, [field]: value }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-3xl overflow-hidden border-border/80 bg-card">
        <DialogHeader>
          <DialogTitle className="font-heading text-xl">
            {draft.id ? "Update evidence claim" : "Add evidence claim"}
          </DialogTitle>
          <DialogDescription>
            Keep the claim distinct from its source. A result snippet is a lead, not proof.
          </DialogDescription>
        </DialogHeader>
        <div className="grid max-h-[calc(92vh-150px)] gap-5 overflow-y-auto pr-2 sm:grid-cols-2">
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="evidence-claim">Claim text</Label>
            <Textarea
              id="evidence-claim"
              rows={3}
              maxLength={4000}
              value={draft.claim}
              onChange={(event) => update("claim", event.target.value)}
              placeholder="State one specific claim, not a summary of the source."
            />
          </div>
          <SelectField id="evidence-category" label="Claim category" value={draft.category} options={categories} onChange={(value) => update("category", value)} />
          <SelectField id="evidence-classification" label="Evidence classification" value={draft.classification} options={classifications} onChange={(value) => update("classification", value)} />
          <div className="grid gap-2">
            <Label htmlFor="source-title">Source title</Label>
            <Input id="source-title" value={draft.source_title} onChange={(event) => update("source_title", event.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="source-reference">Source reference (PMID, DOI, NCT, etc.)</Label>
            <Input id="source-reference" value={draft.source_reference} onChange={(event) => update("source_reference", event.target.value)} />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="source-url">Source URL</Label>
            <Input id="source-url" type="url" value={draft.source_url} onChange={(event) => update("source_url", event.target.value)} placeholder="https://…" />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="publication-date">Publication / decision date</Label>
            <Input id="publication-date" type="date" value={draft.publication_date} onChange={(event) => update("publication_date", event.target.value)} />
          </div>
          <SelectField id="evidence-quality" label="Evidence quality" value={draft.evidence_quality} options={qualities} onChange={(value) => update("evidence_quality", value)} />
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="evidence-limitations">Quality notes and limitations</Label>
            <Textarea id="evidence-limitations" rows={2} value={draft.limitations} onChange={(event) => update("limitations", event.target.value)} placeholder="Study population, design, jurisdiction, scope, possible bias…" />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="verification-note">Why is this classified as verified?</Label>
            <Textarea id="verification-note" rows={2} value={draft.verification_note} onChange={(event) => update("verification_note", event.target.value)} placeholder="Required when classification is Verified. Explain how the source supports this exact claim." />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="source-excerpt">Research excerpt (discovery aid only)</Label>
            <Textarea id="source-excerpt" rows={3} value={draft.source_excerpt} onChange={(event) => update("source_excerpt", event.target.value)} />
          </div>
          <fieldset className="grid gap-2 sm:col-span-2">
            <legend className="mb-1 text-sm font-medium">Executives relying on this claim</legend>
            <div className="flex flex-wrap gap-2">
              {executives.map((role) => (
                <Button
                  type="button"
                  key={role}
                  size="sm"
                  variant={draft.relying_executives.includes(role) ? "default" : "outline"}
                  onClick={() => toggleArrayValue("relying_executives", role)}
                >
                  {role}
                </Button>
              ))}
            </div>
          </fieldset>
          <fieldset className="grid gap-2 sm:col-span-2">
            <legend className="mb-1 text-sm font-medium">Attach to draft conclaves</legend>
            <div className="grid max-h-32 gap-2 overflow-y-auto rounded-md border border-border p-3 sm:grid-cols-2">
              {meetings.map((meeting) => {
                const checked = draft.meeting_ids.includes(meeting.id);
                const locked = isLockedMeeting(meeting.id);
                return (
                  <label key={meeting.id} className="flex items-start gap-2 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={locked && !checked}
                      onChange={() => toggleArrayValue("meeting_ids", meeting.id)}
                      className="mt-0.5 accent-primary"
                    />
                    <span>{meeting.title} <span className="capitalize">({meeting.status})</span></span>
                  </label>
                );
              })}
              {!meetings.length && <span className="text-xs text-muted-foreground">Create a draft conclave to attach evidence to its run.</span>}
            </div>
          </fieldset>
          <fieldset className="grid gap-3 sm:col-span-2 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={draft.challenged} onChange={(event) => update("challenged", event.target.checked)} className="accent-primary" />
              Challenged
              {draft.challenged_by?.length ? ` · ${draft.challenged_by.join(", ")}` : ""}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={draft.disputed} onChange={(event) => update("disputed", event.target.checked)} className="accent-primary" />
              Disputed
              {draft.disputed_by?.length ? ` · ${draft.disputed_by.join(", ")}` : ""}
            </label>
            <div className="grid gap-2 sm:col-span-2">
              <Label htmlFor="dispute-notes">Dispute notes</Label>
              <Textarea id="dispute-notes" rows={2} value={draft.dispute_notes} onChange={(event) => update("dispute_notes", event.target.value)} />
            </div>
          </fieldset>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={saving || !draft.claim.trim()} onClick={onSave} className="gap-2">
            {saving ? <LoaderCircle className="size-4 animate-spin" /> : <Check className="size-4" />}
            Save claim
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function EvidenceRegister({ meetings = [] }) {
  const { getToken } = useAuth();
  const [records, setRecords] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [providers, setProviders] = useState(["pubmed", "clinicaltrials", "openfda"]);
  const [researchResults, setResearchResults] = useState([]);
  const [researchWarnings, setResearchWarnings] = useState([]);
  const [researchBusy, setResearchBusy] = useState(false);
  const [tavilyKey, setTavilyKey] = useState("");
  const [keyBusy, setKeyBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState(blankDraft());
  const [editorOpen, setEditorOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filterText, setFilterText] = useState("");
  const [vaultIds, setVaultIds] = useState(new Set());
  const [vaultBusy, setVaultBusy] = useState("");

  const accessToken = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    return token;
  };

  const refresh = async () => {
    const token = await accessToken();
    const [nextRecords, nextSettings, company] = await Promise.all([
      getEvidenceRecords(token),
      getResearchSettings(token),
      getCompany(token),
    ]);
    setRecords(nextRecords);
    setSettings(nextSettings);
    setVaultIds(
      new Set(
        (company?.approved_knowledge || [])
          .map((item) => item.evidence_id)
          .filter(Boolean),
      ),
    );
  };

  const approveToVault = async (record) => {
    setVaultBusy(record.id);
    setError("");
    try {
      const token = await accessToken();
      await companyKnowledge.create(
        {
          title: (record.claim || "Evidence claim").slice(0, 200),
          summary: [record.limitations, record.source_title].filter(Boolean).join(" · ").slice(0, 4000),
          category: record.category || "operational",
          source_reference: (record.source_reference || record.source_url || "").slice(0, 500),
          evidence_id: record.id,
        },
        token,
      );
      setVaultIds((current) => new Set([...current, record.id]));
      setNotice("Evidence approved into company knowledge.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setVaultBusy("");
    }
  };

  useEffect(() => {
    refresh()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const toggleProvider = (provider) => {
    setProviders((current) => current.includes(provider)
      ? current.filter((item) => item !== provider)
      : [...current, provider]);
  };
  const openNew = (source = null) => {
    const initial = blankDraft();
    if (source) {
      initial.source_provider = source.provider;
      initial.source_title = source.title || "";
      initial.source_reference = source.source_reference || "";
      initial.source_url = source.url || "";
      initial.publication_date = source.publication_date || "";
      initial.retrieved_at = source.retrieved_at || "";
      initial.source_excerpt = source.excerpt || "";
      initial.limitations = source.limitations || "";
      initial.category = source.provider === "openfda"
        ? "regulatory"
        : source.provider === "tavily" ? "commercial" : "scientific";
      initial.meeting_ids = meetings
        .filter((meeting) => meeting.status === "draft")
        .slice(0, 1)
        .map((meeting) => meeting.id);
    }
    setEditing(null);
    setDraft(initial);
    setEditorOpen(true);
  };
  const openEdit = (record) => {
    setEditing(record.id);
    setDraft({
      ...record,
      publication_date: record.publication_date || "",
      retrieved_at: record.retrieved_at || "",
      meeting_ids: record.meeting_ids || [],
    });
    setEditorOpen(true);
  };
  const closeEditor = () => {
    setEditorOpen(false);
    setEditing(null);
    setDraft(blankDraft());
  };

  const search = async (event) => {
    event.preventDefault();
    setResearchBusy(true);
    setError("");
    setResearchWarnings([]);
    try {
      const token = await accessToken();
      const result = await searchResearchSources(
        { query, providers, limit_per_provider: 5 },
        token,
      );
      setResearchResults(result.results);
      setResearchWarnings(result.warnings);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setResearchBusy(false);
    }
  };

  const saveKey = async (clear = false) => {
    setKeyBusy(true);
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      const next = await updateTavilyKey(
        clear ? { clear_api_key: true } : { api_key: tavilyKey },
        token,
      );
      setSettings(next);
      setTavilyKey("");
      setNotice(clear ? "Web search key removed." : "Web search key saved encrypted.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setKeyBusy(false);
    }
  };

  const saveRecord = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    const body = {
      ...draft,
      publication_date: draft.publication_date || null,
      retrieved_at: draft.retrieved_at || null,
      source_excerpt: draft.source_excerpt || "",
    };
    delete body.id;
    delete body.created_at;
    delete body.updated_at;
    try {
      const token = await accessToken();
      if (editing) await updateEvidenceRecord(editing, body, token);
      else await createEvidenceRecord(body, token);
      await refresh();
      closeEditor();
      setNotice(editing ? "Evidence claim updated." : "Evidence claim added.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const removeRecord = async (record) => {
    if (!window.confirm(`Delete evidence claim "${record.claim}"? Meeting run snapshots will remain saved.`)) return;
    setBusy(true);
    setError("");
    try {
      const token = await accessToken();
      await deleteEvidenceRecord(record.id, token);
      await refresh();
      setNotice("Evidence claim removed.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const filteredRecords = records.filter((record) => {
    const haystack = [
      record.claim,
      record.category,
      record.classification,
      record.source_title,
      record.source_reference,
      record.source_url,
    ].join(" ").toLowerCase();
    return haystack.includes(filterText.toLowerCase());
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div className="space-y-2">
          <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.16em] text-primary">
            RESEARCH & PROVENANCE
          </Badge>
          <h2 className="font-heading text-2xl tracking-wide sm:text-3xl">Evidence Register</h2>
          <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
            Separate claims from sources. Research results are leads; the council sees attached records and must assess their applicability.
          </p>
        </div>
        <Button onClick={() => openNew()} className="gap-2">
          <Plus className="size-4" /> Add claim
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertTitle>Evidence request failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <Check className="size-4" />
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,0.8fr)]">
        <Card className="border-border/70 bg-card/80">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 font-heading text-lg"><Search className="size-4 text-primary" /> Research sources</CardTitle>
            <CardDescription>
              Search PubMed, ClinicalTrials.gov, FDA 510(k) records, and optionally the web. Results are not automatically verified.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={search} className="flex flex-col gap-2 sm:flex-row">
              <Input value={query} onChange={(event) => setQuery(event.target.value)} minLength={2} maxLength={300} placeholder="e.g. wearable seizure detection validation" required />
              <Button type="submit" disabled={researchBusy || !providers.length} className="gap-2">
                {researchBusy ? <LoaderCircle className="size-4 animate-spin" /> : <Search className="size-4" />}
                Search
              </Button>
            </form>
            <div className="flex flex-wrap gap-2">
              {researchProviders.map(([provider, label]) => (
                <Button
                  type="button"
                  key={provider}
                  size="sm"
                  variant={providers.includes(provider) ? "secondary" : "outline"}
                  onClick={() => toggleProvider(provider)}
                >
                  {label}
                  {provider === "tavily" && !settings?.web_search_configured ? " · key needed" : ""}
                </Button>
              ))}
            </div>
            {researchWarnings.map((warning) => (
              <Alert key={warning} className="border-amber-500/30 bg-amber-500/5">
                <ShieldAlert className="size-4 text-amber-300" />
                <AlertDescription>{warning}</AlertDescription>
              </Alert>
            ))}
            <div className="space-y-3">
              {researchResults.map((source, index) => (
                <article key={`${source.provider}:${source.url}:${index}`} className="rounded-lg border border-border/70 bg-background/50 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Badge variant="outline" className="capitalize">{source.provider.replaceAll("_", " ")}</Badge>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      Retrieved {new Date(source.retrieved_at).toLocaleDateString()}
                    </span>
                  </div>
                  <h3 className="mt-3 text-sm font-semibold leading-6">{source.title}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {source.source_reference || source.url}
                    {source.publication_date ? ` · Published ${source.publication_date}` : ""}
                  </p>
                  {source.excerpt && <p className="mt-2 text-sm leading-6 text-muted-foreground">{source.excerpt}</p>}
                  <p className="mt-2 text-xs leading-5 text-amber-200/80">{source.limitations}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => openNew(source)} className="gap-1.5">
                      <Plus className="size-3.5" /> Create claim from source
                    </Button>
                    <Button asChild size="sm" variant="outline" className="gap-1.5">
                      <a href={source.url} target="_blank" rel="noreferrer">
                        Open source <ExternalLink className="size-3.5" />
                      </a>
                    </Button>
                  </div>
                </article>
              ))}
              {!researchResults.length && !researchBusy && (
                <p className="rounded-lg border border-dashed border-border p-5 text-center text-sm text-muted-foreground">
                  Search results will appear here with their source references and retrieval date.
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="h-fit border-border/70 bg-card/80">
          <CardHeader>
            <CardTitle className="font-heading text-lg">Web search configuration</CardTitle>
            <CardDescription>
              Tavily is optional and enables broad web discovery such as market research. Its API key is encrypted at rest.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between gap-3 rounded-lg border border-border/70 p-3">
              <span className="text-sm">Tavily web search</span>
              <Badge variant="outline" className={settings?.web_search_configured ? "text-emerald-300" : ""}>
                {settings?.web_search_configured ? "Configured" : "Not configured"}
              </Badge>
            </div>
            {!settings?.encryption_key_ready && (
              <p className="text-xs leading-5 text-amber-200/80">
                Configure a valid LLM_CONFIG_ENCRYPTION_KEY on the backend to store a search key securely.
              </p>
            )}
            <div className="grid gap-2">
              <Label htmlFor="tavily-key">Tavily API key</Label>
              <Input id="tavily-key" type="password" autoComplete="new-password" value={tavilyKey} onChange={(event) => setTavilyKey(event.target.value)} placeholder="Stored encrypted; never returned" />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button disabled={keyBusy || !settings?.encryption_key_ready || !tavilyKey.trim()} onClick={() => saveKey(false)}>
                {keyBusy ? <LoaderCircle className="size-4 animate-spin" /> : "Save key"}
              </Button>
              {settings?.web_search_configured && (
                <Button variant="outline" disabled={keyBusy} onClick={() => saveKey(true)}>Remove key</Button>
              )}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h3 className="font-heading text-xl">Company claims</h3>
            <p className="mt-1 text-sm text-muted-foreground">{records.length} saved claims · attach relevant claims to draft conclaves before running.</p>
          </div>
          <div className="w-full sm:max-w-xs">
            <Input value={filterText} onChange={(event) => setFilterText(event.target.value)} placeholder="Filter claims…" aria-label="Filter evidence claims" />
          </div>
        </div>
        {loading ? (
          <div className="grid gap-3 md:grid-cols-2">
            {[0, 1].map((item) => <div key={item} className="h-48 animate-pulse rounded-xl bg-muted/70" />)}
          </div>
        ) : filteredRecords.length ? (
          <div className="grid gap-4 md:grid-cols-2">
            {filteredRecords.map((record) => (
              <Card key={record.id} className="border-border/70 bg-card/80">
                <CardHeader className="space-y-3 pb-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="capitalize">{record.classification}</Badge>
                    <Badge variant="outline" className="capitalize">{record.source_provider || "manual"}</Badge>
                    <Badge variant="secondary" className="capitalize">{record.category}</Badge>
                    <Badge variant="outline" className="capitalize">Quality: {record.evidence_quality}</Badge>
                    {record.challenged && <Badge variant="outline" className="border-amber-500/30 text-amber-200">Challenged</Badge>}
                    {record.disputed && <Badge variant="outline" className="border-destructive/40 text-destructive">Disputed</Badge>}
                  </div>
                  <CardTitle className="text-base leading-6">{record.claim}</CardTitle>
                  {record.source_title && <CardDescription>{record.source_title}</CardDescription>}
                </CardHeader>
                <CardContent className="space-y-3">
                  {(record.source_reference || record.source_url) && (
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      {record.source_reference && <span className="font-mono text-muted-foreground">{record.source_reference}</span>}
                      {record.source_url && (
                        <a href={record.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                          Source <ExternalLink className="size-3" />
                        </a>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Published: {record.publication_date || "unknown"} · Retrieved: {record.retrieved_at ? new Date(record.retrieved_at).toLocaleDateString() : "not recorded"}
                  </p>
                  {record.limitations && <p className="text-sm leading-5 text-muted-foreground">{record.limitations}</p>}
                  <div className="flex flex-wrap gap-1">
                    {(record.relying_executives || []).map((role) => <Badge key={role} variant="outline" className="font-mono text-[9px]">{role} relies</Badge>)}
                    {(record.challenged_by || []).map((role) => <Badge key={`challenged-${role}`} variant="outline" className="font-mono text-[9px] text-amber-200">{role} challenged</Badge>)}
                    {(record.disputed_by || []).map((role) => <Badge key={`disputed-${role}`} variant="outline" className="font-mono text-[9px] text-destructive">{role} disputes</Badge>)}
                  </div>
                  {record.meeting_ids?.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Attached to {record.meeting_ids.map((id) => meetings.find((meeting) => meeting.id === id)?.title || `conclave #${id}`).join(", ")}
                    </p>
                  )}
                  <div className="flex justify-end gap-2 border-t border-border/60 pt-3">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="gap-1.5"
                      disabled={vaultIds.has(record.id) || vaultBusy === record.id}
                      onClick={() => approveToVault(record)}
                    >
                      {vaultBusy === record.id ? (
                        <LoaderCircle className="size-3.5 animate-spin" />
                      ) : vaultIds.has(record.id) ? (
                        <Check className="size-3.5 text-emerald-300" />
                      ) : (
                        <BookOpen className="size-3.5" />
                      )}
                      {vaultIds.has(record.id) ? "In vault" : "Approve into vault"}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openEdit(record)} className="gap-1.5">
                      <Pencil className="size-3.5" /> Edit
                    </Button>
                    <Button variant="ghost" size="sm" disabled={busy} onClick={() => removeRecord(record)} className="gap-1.5 text-destructive hover:text-destructive">
                      <Trash2 className="size-3.5" /> Delete
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <Card className="border-dashed border-border/80 bg-card/40">
            <CardContent className="grid min-h-40 place-items-center text-center">
              <div className="space-y-2">
                <BookOpen className="mx-auto size-5 text-muted-foreground" />
                <p className="text-sm font-medium">No evidence claims yet</p>
                <p className="text-xs text-muted-foreground">Search a source or add a claim with its provenance and limitations.</p>
              </div>
            </CardContent>
          </Card>
        )}
      </section>

      <RecordEditor
        open={editorOpen}
        onOpenChange={(open) => !open && closeEditor()}
        draft={draft}
        setDraft={setDraft}
        meetings={meetings}
        onSave={saveRecord}
        saving={saving}
      />
    </div>
  );
}
