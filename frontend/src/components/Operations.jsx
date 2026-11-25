import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  Calculator,
  CalendarCheck,
  CheckCircle2,
  ClipboardList,
  Eye,
  FileText,
  LayoutTemplate,
  LoaderCircle,
  Lock,
  Network,
  Plus,
  Presentation,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import {
  approveOperationalArtifact,
  createOperationalArtifact,
  deleteOperationalArtifact,
  getOperationalArtifacts,
  getOperationsCapabilities,
  regenerateOperationalArtifact,
  rejectOperationalArtifact,
  submitOperationalArtifact,
} from "../api";
import MarkdownContent from "./MarkdownContent";
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
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";

const kindIcons = {
  project_plan: LayoutTemplate,
  financial_model: Calculator,
  investor_document: Presentation,
  task_list: ClipboardList,
  architecture_document: Network,
  milestone_review: CalendarCheck,
  company_review: FileText,
};

const statusStyles = {
  draft: "border-border bg-muted/40 text-muted-foreground",
  pending_approval: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  approved: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
  rejected: "border-destructive/40 bg-destructive/10 text-destructive",
};

const statusLabel = (status) => (status || "draft").replaceAll("_", " ");

export default function Operations() {
  const { getToken } = useAuth();
  const [capabilities, setCapabilities] = useState([]);
  const [policy, setPolicy] = useState({});
  const [artifacts, setArtifacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState({ kind: "project_plan", title: "", brief: "" });
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState(null);
  const [viewOpen, setViewOpen] = useState(false);
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState("");

  const accessToken = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    return token;
  };

  const load = async () => {
    const token = await accessToken();
    const [capabilityData, artifactData] = await Promise.all([
      getOperationsCapabilities(token),
      getOperationalArtifacts(token),
    ]);
    setCapabilities(capabilityData.capabilities || []);
    setPolicy(capabilityData.policy || {});
    setArtifacts(artifactData);
  };

  useEffect(() => {
    load()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const capabilityByKind = useMemo(
    () => Object.fromEntries(capabilities.map((item) => [item.kind, item])),
    [capabilities],
  );

  const openCreate = (kind = "project_plan") => {
    const capability = capabilityByKind[kind];
    setDraft({
      kind,
      title: capability ? `${capability.label} draft` : "Operational draft",
      brief: "",
    });
    setCreateOpen(true);
  };

  const create = async () => {
    if (!draft.title.trim()) return;
    setCreating(true);
    setError("");
    try {
      const token = await accessToken();
      const artifact = await createOperationalArtifact(
        { kind: draft.kind, title: draft.title.trim(), brief: draft.brief.trim() },
        token,
      );
      setCreateOpen(false);
      setNotice("Draft generated. It has no external effect until you approve it.");
      await load();
      setSelected(artifact);
      setComments("");
      setViewOpen(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCreating(false);
    }
  };

  const runAction = async (label, action) => {
    if (!selected) return;
    setBusy(label);
    setError("");
    try {
      const token = await accessToken();
      await action(selected.id, token);
      const refreshed = await getOperationalArtifacts(token);
      const updated = refreshed.find((item) => item.id === selected.id) || null;
      setArtifacts(refreshed);
      setSelected(updated);
      if (!updated) setViewOpen(false);
      if (label !== "delete") setNotice(`Artifact ${label}.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy("");
    }
  };

  const remove = async () => {
    if (!selected) return;
    if (!window.confirm(`Delete "${selected.title}"?`)) return;
    await runAction("delete", (id, token) => deleteOperationalArtifact(id, token));
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading operations…
      </div>
    );
  }

  return (
    <section className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Operations request failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <Card className="border-primary/20 bg-primary/5">
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
              <Lock className="size-4" />
            </span>
            <div>
              <p className="text-sm font-medium text-foreground">Approval-gated, draft-only execution</p>
              <p className="mt-1 text-sm leading-5 text-muted-foreground">
                {policy.execution_scope || "Generating an artifact performs no external action."} {policy.external_actions_require || ""}
              </p>
            </div>
          </div>
          <Badge variant="outline" className="w-fit shrink-0 border-primary/30 text-primary">
            ALWAYS REQUIRES FOUNDER APPROVAL
          </Badge>
        </CardContent>
      </Card>

      <section className="space-y-3">
        <div>
          <h3 className="font-heading text-xl">Capabilities</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Each capability produces an internal draft from the company context.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {capabilities.map((capability) => {
            const Icon = kindIcons[capability.kind] || FileText;
            return (
              <Card key={capability.kind} className="border-border/70 bg-card/80">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <span className="grid size-8 place-items-center rounded-md border border-primary/25 bg-primary/10 text-primary">
                      <Icon className="size-4" />
                    </span>
                    {capability.label}
                  </CardTitle>
                  <CardDescription className="leading-5">{capability.description}</CardDescription>
                </CardHeader>
                <CardContent className="flex items-center justify-between gap-2 pt-0">
                  <span className="font-mono text-[9px] tracking-[0.06em] text-muted-foreground">{capability.permission}</span>
                  <Button variant="outline" size="sm" className="gap-1.5" onClick={() => openCreate(capability.kind)}>
                    <Plus className="size-3.5" /> Draft
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="font-heading text-xl">Artifacts</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {artifacts.length} draft(s) and approvals. Nothing leaves this workspace.
            </p>
          </div>
          <Button className="gap-2" onClick={() => openCreate()}>
            <Plus className="size-4" /> New draft
          </Button>
        </div>

        {artifacts.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {artifacts.map((artifact) => {
              const Icon = kindIcons[artifact.kind] || FileText;
              return (
                <Card key={artifact.id} className="border-border/70 bg-card/70">
                  <CardContent className="space-y-3 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="grid size-8 shrink-0 place-items-center rounded-md border border-border bg-background text-muted-foreground">
                          <Icon className="size-4" />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">{artifact.title}</p>
                          <p className="text-[11px] capitalize text-muted-foreground">
                            {capabilityByKind[artifact.kind]?.label || artifact.kind.replaceAll("_", " ")}
                          </p>
                        </div>
                      </div>
                      <Badge variant="outline" className={`shrink-0 capitalize ${statusStyles[artifact.status] || ""}`}>
                        {statusLabel(artifact.status)}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Updated {new Date(artifact.updated_at).toLocaleString()}
                      {artifact.approved_by ? ` · Approved by ${artifact.approved_by}` : ""}
                    </p>
                    {artifact.rejection_reason && (
                      <p className="text-xs text-destructive">{artifact.rejection_reason}</p>
                    )}
                    <div className="flex justify-end border-t border-border/60 pt-3">
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        onClick={() => {
                          setSelected(artifact);
                          setComments("");
                          setViewOpen(true);
                        }}
                      >
                        <Eye className="size-3.5" /> Review
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : (
          <Card className="border-dashed border-border/80 bg-card/40">
            <CardContent className="grid min-h-36 place-items-center text-center">
              <div className="space-y-2">
                <ShieldCheck className="mx-auto size-5 text-muted-foreground" />
                <p className="text-sm font-medium">No operational drafts yet</p>
                <p className="text-xs text-muted-foreground">Start from a capability above. Every draft waits for founder approval.</p>
              </div>
            </CardContent>
          </Card>
        )}
      </section>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-xl border-border/80 bg-card">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">Generate a draft</DialogTitle>
            <DialogDescription>
              Built from the current company context. This action has no external effect.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="artifact-kind">Capability</Label>
              <select
                id="artifact-kind"
                value={draft.kind}
                onChange={(event) => setDraft((current) => ({ ...current, kind: event.target.value }))}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
              >
                {capabilities.map((capability) => (
                  <option key={capability.kind} value={capability.kind}>{capability.label}</option>
                ))}
              </select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="artifact-title">Title</Label>
              <Input
                id="artifact-title"
                value={draft.title}
                maxLength={200}
                onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="artifact-brief">Brief</Label>
              <Textarea
                id="artifact-brief"
                rows={3}
                maxLength={6000}
                value={draft.brief}
                onChange={(event) => setDraft((current) => ({ ...current, brief: event.target.value }))}
                placeholder="What should this draft focus on?"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button onClick={create} disabled={creating || !draft.title.trim()} className="gap-2">
              {creating ? <LoaderCircle className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
              Generate draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={viewOpen} onOpenChange={setViewOpen}>
        <DialogContent className="max-h-[92vh] max-w-3xl overflow-hidden border-border/80 bg-card p-0">
          {selected && (
            <>
              <DialogHeader className="border-b border-border/70 bg-muted/10 p-5 pr-12">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className={`capitalize ${statusStyles[selected.status] || ""}`}>
                    {statusLabel(selected.status)}
                  </Badge>
                  <Badge variant="outline" className="font-mono text-[9px] text-muted-foreground">
                    {selected.kind.replaceAll("_", " ")}
                  </Badge>
                  <Badge variant="outline" className="gap-1 border-primary/25 text-primary">
                    {selected.permissions?.external ? <XCircle className="size-3" /> : <Lock className="size-3" />}
                    {selected.permissions?.external ? "External requested" : "Internal only"}
                  </Badge>
                </div>
                <DialogTitle className="mt-2 font-heading text-xl">{selected.title}</DialogTitle>
                <DialogDescription>
                  {selected.approved_by
                    ? `Approved by ${selected.approved_by} on ${new Date(selected.approved_at).toLocaleString()}.`
                    : "Awaiting founder approval. Approval does not trigger any external action."}
                </DialogDescription>
              </DialogHeader>
              <ScrollArea className="max-h-[calc(92vh-320px)]">
                <div className="p-5">
                  <MarkdownContent className="text-sm leading-7 text-foreground">
                    {selected.payload?.markdown || "No content generated."}
                  </MarkdownContent>
                  <div className="mt-5 space-y-2 border-t border-border/60 pt-4">
                    <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">Audit trail</p>
                    {(selected.events || []).map((event) => (
                      <p key={event.id} className="text-xs text-muted-foreground">
                        {new Date(event.created_at).toLocaleString()} · {event.action} · {event.actor}
                        {event.comments ? ` — ${event.comments}` : ""}
                      </p>
                    ))}
                  </div>
                </div>
              </ScrollArea>
              <div className="space-y-3 border-t border-border/70 p-4">
                <Textarea
                  rows={2}
                  maxLength={2000}
                  value={comments}
                  onChange={(event) => setComments(event.target.value)}
                  placeholder="Approval or rejection note (optional)"
                />
                <div className="flex flex-wrap justify-end gap-2">
                  {selected.status === "draft" && (
                    <>
                      <Button variant="ghost" size="sm" className="gap-1.5 text-destructive hover:text-destructive" disabled={Boolean(busy)} onClick={remove}>
                        <Trash2 className="size-3.5" /> Delete
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        disabled={Boolean(busy)}
                        onClick={() => runAction("regenerated", (id, token) => regenerateOperationalArtifact(id, token))}
                      >
                        <RefreshCw className="size-3.5" /> Regenerate
                      </Button>
                      <Button
                        size="sm"
                        className="gap-1.5"
                        disabled={Boolean(busy)}
                        onClick={() => runAction("submitted", (id, token) => submitOperationalArtifact(id, token))}
                      >
                        <Send className="size-3.5" /> Submit for approval
                      </Button>
                    </>
                  )}
                  {selected.status === "rejected" && (
                    <>
                      <Button variant="ghost" size="sm" className="gap-1.5 text-destructive hover:text-destructive" disabled={Boolean(busy)} onClick={remove}>
                        <Trash2 className="size-3.5" /> Delete
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        disabled={Boolean(busy)}
                        onClick={() => runAction("regenerated", (id, token) => regenerateOperationalArtifact(id, token))}
                      >
                        <RefreshCw className="size-3.5" /> Regenerate
                      </Button>
                    </>
                  )}
                  {selected.status === "pending_approval" && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5 border-destructive/40 text-destructive hover:text-destructive"
                        disabled={Boolean(busy)}
                        onClick={() => runAction("rejected", (id, token) => rejectOperationalArtifact(id, { comments }, token))}
                      >
                        <XCircle className="size-3.5" /> Reject
                      </Button>
                      <Button
                        size="sm"
                        className="gap-1.5"
                        disabled={Boolean(busy)}
                        onClick={() => runAction("approved", (id, token) => approveOperationalArtifact(id, { comments }, token))}
                      >
                        <CheckCircle2 className="size-3.5" /> Approve
                      </Button>
                    </>
                  )}
                  {selected.status === "approved" && (
                    <span className="inline-flex items-center gap-1.5 text-xs text-emerald-300">
                      <ShieldCheck className="size-3.5" /> Approved for internal use only
                    </span>
                  )}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
