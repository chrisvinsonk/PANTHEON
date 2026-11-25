import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  BookOpen,
  Check,
  CircleAlert,
  LoaderCircle,
  Pencil,
  Plus,
  Search,
  Trash2,
  Vault,
} from "lucide-react";
import {
  companyKnowledge,
  getCompany,
  getEvidenceRecords,
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
  "scientific",
  "technical",
  "financial",
  "commercial",
  "regulatory",
  "operational",
];

const emptyDraft = {
  id: null,
  title: "",
  summary: "",
  category: "operational",
  source_reference: "",
  evidence_id: null,
};

export default function KnowledgeVault() {
  const { getToken } = useAuth();
  const [company, setCompany] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [filterText, setFilterText] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const [saving, setSaving] = useState(false);

  const accessToken = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    return token;
  };

  const refresh = async () => {
    const token = await accessToken();
    const [companyData, evidenceData] = await Promise.all([
      getCompany(token),
      getEvidenceRecords(token),
    ]);
    setCompany(companyData);
    setEvidence(evidenceData);
  };

  useEffect(() => {
    refresh()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const knowledge = company?.approved_knowledge || [];
  const linkedEvidenceIds = useMemo(
    () => new Set(knowledge.map((item) => item.evidence_id).filter(Boolean)),
    [knowledge],
  );

  const filteredKnowledge = useMemo(() => {
    const needle = filterText.trim().toLowerCase();
    if (!needle) return knowledge;
    return knowledge.filter((item) =>
      [item.title, item.summary, item.category, item.source_reference]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [knowledge, filterText]);

  const openCreate = () => {
    setDraft(emptyDraft);
    setEditorOpen(true);
  };

  const openEdit = (item) => {
    setDraft({
      id: item.id,
      title: item.title,
      summary: item.summary || "",
      category: item.category || "operational",
      source_reference: item.source_reference || "",
      evidence_id: item.evidence_id ?? null,
    });
    setEditorOpen(true);
  };

  const saveKnowledge = async () => {
    if (!draft.title.trim()) return;
    setSaving(true);
    setError("");
    try {
      const token = await accessToken();
      const body = {
        title: draft.title.trim(),
        summary: draft.summary.trim(),
        category: draft.category,
        source_reference: draft.source_reference.trim(),
        ...(draft.evidence_id ? { evidence_id: draft.evidence_id } : {}),
      };
      if (draft.id) {
        await companyKnowledge.update(draft.id, body, token);
        setNotice("Knowledge entry updated.");
      } else {
        await companyKnowledge.create(body, token);
        setNotice("Knowledge approved into the vault.");
      }
      setEditorOpen(false);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const approveEvidence = async (record) => {
    setBusy(`approve-${record.id}`);
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
      setNotice("Evidence approved into company knowledge.");
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy("");
    }
  };

  const removeKnowledge = async (item) => {
    if (!window.confirm(`Remove "${item.title}" from approved company knowledge?`)) return;
    setBusy(`remove-${item.id}`);
    setError("");
    try {
      const token = await accessToken();
      await companyKnowledge.remove(item.id, token);
      setNotice("Knowledge entry removed.");
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading knowledge vault…
      </div>
    );
  }

  return (
    <section className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Vault request failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h2 className="font-heading text-2xl tracking-wide">Approved company knowledge</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {knowledge.length} entries · this context is injected into every council run.
          </p>
        </div>
        <Button className="gap-2" onClick={openCreate}>
          <Plus className="size-4" /> Add knowledge
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <Search className="size-4 text-muted-foreground" />
        <Input
          value={filterText}
          onChange={(event) => setFilterText(event.target.value)}
          placeholder="Filter approved knowledge…"
          aria-label="Filter knowledge"
        />
      </div>

      {filteredKnowledge.length ? (
        <div className="grid gap-4 md:grid-cols-2">
          {filteredKnowledge.map((item) => (
            <Card key={item.id} className="border-border/70 bg-card/80">
              <CardHeader className="space-y-2 pb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary" className="capitalize">{item.category}</Badge>
                  {item.evidence_id && <Badge variant="outline">Linked evidence #{item.evidence_id}</Badge>}
                </div>
                <CardTitle className="text-base leading-6">{item.title}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {item.summary && <p className="text-sm leading-6 text-muted-foreground">{item.summary}</p>}
                {item.source_reference && (
                  <p className="font-mono text-[10px] tracking-[0.06em] text-muted-foreground">{item.source_reference}</p>
                )}
                {item.approved_at && (
                  <p className="text-xs text-muted-foreground">
                    Approved {new Date(item.approved_at).toLocaleString()}
                  </p>
                )}
                <div className="flex justify-end gap-2 border-t border-border/60 pt-3">
                  <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => openEdit(item)}>
                    <Pencil className="size-3.5" /> Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy === `remove-${item.id}`}
                    className="gap-1.5 text-destructive hover:text-destructive"
                    onClick={() => removeKnowledge(item)}
                  >
                    <Trash2 className="size-3.5" /> Remove
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
              <Vault className="mx-auto size-5 text-muted-foreground" />
              <p className="text-sm font-medium">No approved knowledge yet</p>
              <p className="text-xs text-muted-foreground">
                Approve evidence claims below, or add knowledge directly.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <section className="space-y-4">
        <div>
          <h3 className="font-heading text-xl">Evidence register</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Promote a source-backed claim into approved knowledge so the council treats it as baseline context.
          </p>
        </div>
        {evidence.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {evidence.map((record) => {
              const linked = linkedEvidenceIds.has(record.id);
              return (
                <Card key={record.id} className="border-border/70 bg-card/70">
                  <CardContent className="space-y-3 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="capitalize">{record.classification}</Badge>
                      <Badge variant="secondary" className="capitalize">{record.category}</Badge>
                      {record.evidence_quality && (
                        <Badge variant="outline" className="capitalize">Quality: {record.evidence_quality}</Badge>
                      )}
                    </div>
                    <p className="text-sm font-medium leading-6 text-foreground">{record.claim}</p>
                    {record.source_title && <p className="text-xs text-muted-foreground">{record.source_title}</p>}
                    <div className="flex items-center justify-between gap-2 border-t border-border/60 pt-3">
                      {linked ? (
                        <span className="inline-flex items-center gap-1.5 text-xs text-emerald-300">
                          <Check className="size-3.5" /> In vault
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                          <CircleAlert className="size-3.5" /> Not approved
                        </span>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={linked || busy === `approve-${record.id}`}
                        className="gap-1.5"
                        onClick={() => approveEvidence(record)}
                      >
                        {busy === `approve-${record.id}` ? (
                          <LoaderCircle className="size-3.5 animate-spin" />
                        ) : (
                          <BookOpen className="size-3.5" />
                        )}
                        Approve into vault
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No evidence claims yet. Add claims in the Evidence Register first.
          </p>
        )}
      </section>

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-2xl border-border/80 bg-card">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">
              {draft.id ? "Edit knowledge entry" : "Approve knowledge"}
            </DialogTitle>
            <DialogDescription>
              Approved knowledge becomes part of the company context injected into every council run.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="knowledge-title">Title</Label>
              <Input
                id="knowledge-title"
                value={draft.title}
                maxLength={200}
                onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
                placeholder="A single, specific piece of company knowledge"
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="knowledge-category">Category</Label>
                <select
                  id="knowledge-category"
                  value={draft.category}
                  onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
                >
                  {categories.map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="knowledge-source">Source reference</Label>
                <Input
                  id="knowledge-source"
                  value={draft.source_reference}
                  maxLength={500}
                  onChange={(event) => setDraft((current) => ({ ...current, source_reference: event.target.value }))}
                  placeholder="Document, dataset or evidence link"
                />
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="knowledge-summary">Summary</Label>
              <Textarea
                id="knowledge-summary"
                rows={4}
                maxLength={4000}
                value={draft.summary}
                onChange={(event) => setDraft((current) => ({ ...current, summary: event.target.value }))}
                placeholder="What should the council know and be able to rely on?"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditorOpen(false)}>Cancel</Button>
            <Button disabled={saving || !draft.title.trim()} onClick={saveKnowledge} className="gap-2">
              {saving && <LoaderCircle className="size-4 animate-spin" />}
              {draft.id ? "Save changes" : "Approve knowledge"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
