import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  BookOpen,
  CalendarClock,
  Check,
  CircleAlert,
  Gavel,
  History,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import {
  createDecisionRecord,
  deleteDecisionRecord,
  getDecisionRecords,
  getDueDecisionRecords,
  recallMemory,
  reviewDecisionRecord,
  syncDecisionRecords,
  updateDecisionRecord,
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

const lifecycles = [
  ["open", "Open"],
  ["under_review", "Under review"],
  ["closed", "Closed"],
  ["superseded", "Superseded"],
];
const conditionStatuses = [
  ["pending", "Pending"],
  ["met", "Met"],
  ["breached", "Breached"],
];

const lifecycleBadge = (value) => ({
  open: "border-primary/40 text-primary",
  under_review: "border-amber-400/40 text-amber-300",
  closed: "border-emerald-400/40 text-emerald-300",
  superseded: "border-muted-foreground/40 text-muted-foreground",
}[value] || "border-border text-muted-foreground");

const conditionDot = (status) => ({
  pending: "bg-muted-foreground/60",
  met: "bg-emerald-400",
  breached: "bg-destructive",
}[status] || "bg-muted-foreground/60");

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

const blankDraft = () => ({
  meeting_id: null,
  decision: "",
  rationale: "",
  board_recommendation: "",
  founder_decision: "",
  founder_notes: "",
  conditions: [],
  owner: "",
  target_date: "",
  success_criteria: "",
  review_date: "",
  actual_outcome: "",
  lifecycle: "open",
});

function updateCondition(draft, index, patch) {
  return draft.conditions.map((condition, idx) =>
    idx === index ? { ...condition, ...patch } : condition,
  );
}

function DecisionEditor({ open, onOpenChange, draft, setDraft, onSave, onDelete, saving }) {
  const update = (field, value) => setDraft((current) => ({ ...current, [field]: value }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-3xl overflow-hidden border-border/80 bg-card">
        <DialogHeader>
          <DialogTitle className="font-heading text-xl">
            {draft.id ? "Update decision record" : "Add decision record"}
          </DialogTitle>
          <DialogDescription>
            Every founder decree becomes a structured record: rationale, the board's
            recommendation, the decree, conditions, ownership and review.
          </DialogDescription>
        </DialogHeader>
        <div className="grid max-h-[calc(92vh-150px)] gap-5 overflow-y-auto pr-2 sm:grid-cols-2">
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="decision-text">Decision and rationale</Label>
            <Textarea
              id="decision-text"
              rows={3}
              required
              maxLength={2000}
              value={draft.decision}
              onChange={(event) => update("decision", event.target.value)}
              placeholder="What was decreed, and why?"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="board-recommendation">Original board recommendation</Label>
            <Textarea
              id="board-recommendation"
              rows={2}
              value={draft.board_recommendation}
              onChange={(event) => update("board_recommendation", event.target.value)}
              placeholder="What the council recommended before the decree"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="founder-decision">Founder decision</Label>
            <Input
              id="founder-decision"
              value={draft.founder_decision}
              onChange={(event) => update("founder_decision", event.target.value)}
              placeholder="approve / reject / revise / defer"
            />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="founder-notes">Founder notes and constraints</Label>
            <Textarea
              id="founder-notes"
              rows={2}
              value={draft.founder_notes}
              onChange={(event) => update("founder_notes", event.target.value)}
              placeholder="Conditions, constraints or caveats attached to the decree"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="decision-owner">Owner</Label>
            <Input
              id="decision-owner"
              value={draft.owner}
              onChange={(event) => update("owner", event.target.value)}
              placeholder="Who carries this decision?"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="decision-success">Success criteria</Label>
            <Input
              id="decision-success"
              value={draft.success_criteria}
              onChange={(event) => update("success_criteria", event.target.value)}
              placeholder="How will we know it worked?"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="decision-target">Target date</Label>
            <Input
              id="decision-target"
              type="date"
              value={draft.target_date || ""}
              onChange={(event) => update("target_date", event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="decision-review">Review date</Label>
            <Input
              id="decision-review"
              type="date"
              value={draft.review_date || ""}
              onChange={(event) => update("review_date", event.target.value)}
            />
          </div>
          <fieldset className="grid gap-2 sm:col-span-2">
            <legend className="text-sm font-medium">Conditions and constraints</legend>
            <p className="text-xs leading-5 text-muted-foreground">
              A condition changing to met or breached makes the decision due for review.
            </p>
            {draft.conditions.map((condition, index) => (
              <div key={condition.id || index} className="grid gap-2 rounded-md border border-border/70 p-3 sm:grid-cols-[minmax(0,1fr)_140px_auto]">
                <Input
                  aria-label="Condition label"
                  value={condition.label}
                  onChange={(event) => setDraft((current) => ({
                    ...current,
                    conditions: updateCondition(current, index, { label: event.target.value }),
                  }))}
                  placeholder="e.g. Dataset access obtained"
                />
                <select
                  aria-label="Condition status"
                  value={condition.status}
                  onChange={(event) => setDraft((current) => ({
                    ...current,
                    conditions: updateCondition(current, index, { status: event.target.value }),
                  }))}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
                >
                  {conditionStatuses.map(([value, title]) => (
                    <option value={value} key={value}>{title}</option>
                  ))}
                </select>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Remove condition"
                  onClick={() => setDraft((current) => ({
                    ...current,
                    conditions: current.conditions.filter((_, idx) => idx !== index),
                  }))}
                >
                  <Trash2 className="size-4" />
                </Button>
                <Input
                  aria-label="Condition note"
                  className="sm:col-span-3"
                  value={condition.note || ""}
                  onChange={(event) => setDraft((current) => ({
                    ...current,
                    conditions: updateCondition(current, index, { note: event.target.value }),
                  }))}
                  placeholder="Optional note — what proves this condition changed?"
                />
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-fit gap-1.5"
              onClick={() => setDraft((current) => ({
                ...current,
                conditions: [
                  ...current.conditions,
                  { id: `new-${Date.now()}-${current.conditions.length}`, label: "", status: "pending", note: "" },
                ],
              }))}
            >
              <Plus className="size-3.5" /> Add condition
            </Button>
          </fieldset>
          <div className="grid gap-2">
            <Label htmlFor="decision-outcome">Actual outcome</Label>
            <Textarea
              id="decision-outcome"
              rows={2}
              value={draft.actual_outcome}
              onChange={(event) => update("actual_outcome", event.target.value)}
              placeholder="Recorded after review: what actually happened"
            />
          </div>
          <SelectField
            id="decision-lifecycle"
            label="Lifecycle"
            value={draft.lifecycle}
            options={lifecycles}
            onChange={(value) => update("lifecycle", value)}
          />
        </div>
        <DialogFooter className="flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={!draft.id || saving}
            onClick={() => onDelete(draft)}
          >
            <Trash2 className="size-3.5" /> Delete
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="button" disabled={saving || !draft.decision.trim()} onClick={() => onSave(draft)}>
              {saving ? <LoaderCircle className="size-4 animate-spin" /> : <Check className="size-4" />}
              {draft.id ? "Save changes" : "Add decision"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReviewDialog({ open, onOpenChange, record, draft, setDraft, onSave, saving }) {
  if (!record) return null;
  const setCondition = (index, patch) => setDraft((current) => ({
    ...current,
    conditions: current.conditions.map((condition, idx) =>
      idx === index ? { ...condition, ...patch } : condition,
    ),
  }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-2xl overflow-hidden border-border/80 bg-card">
        <DialogHeader>
          <DialogTitle className="font-heading text-xl">
            Review DECISION-{record.id}
          </DialogTitle>
          <DialogDescription>
            Record the actual outcome, re-assess each tracked condition, and set the next review date. Closing a decision stops future follow-ups.
          </DialogDescription>
        </DialogHeader>
        <div className="grid max-h-[calc(92vh-150px)] gap-5 overflow-y-auto pr-2 sm:grid-cols-2">
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="review-outcome">Actual outcome</Label>
            <Textarea
              id="review-outcome"
              rows={3}
              value={draft.outcome}
              onChange={(event) => setDraft((current) => ({ ...current, outcome: event.target.value }))}
              placeholder="What actually happened versus the success criteria?"
            />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="review-notes">Review notes</Label>
            <Textarea
              id="review-notes"
              rows={2}
              value={draft.notes}
              onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
              placeholder="What changed, what you learned, what to do next"
            />
          </div>
          <fieldset className="grid gap-2 sm:col-span-2">
            <legend className="text-sm font-medium">Condition re-assessment</legend>
            {draft.conditions.map((condition, index) => (
              <div key={condition.id || index} className="flex items-center gap-3">
                <span className={`size-2 shrink-0 rounded-full ${conditionDot(condition.status)}`} />
                <span className="min-w-0 flex-1 truncate text-sm">{condition.label}</span>
                <select
                  aria-label={`Status for ${condition.label}`}
                  value={condition.status}
                  onChange={(event) => setCondition(index, { status: event.target.value })}
                  className="h-9 w-36 rounded-md border border-input bg-background px-3 text-sm text-foreground"
                >
                  {conditionStatuses.map(([value, title]) => (
                    <option value={value} key={value}>{title}</option>
                  ))}
                </select>
              </div>
            ))}
            {!draft.conditions.length && (
              <p className="text-xs text-muted-foreground">No tracked conditions on this decision.</p>
            )}
          </fieldset>
          <div className="grid gap-2">
            <Label htmlFor="review-next-date">Next review date</Label>
            <Input
              id="review-next-date"
              type="date"
              value={draft.new_review_date || ""}
              onChange={(event) => setDraft((current) => ({ ...current, new_review_date: event.target.value }))}
            />
          </div>
          <SelectField
            id="review-lifecycle"
            label="Lifecycle after review"
            value={draft.lifecycle}
            options={[["", "Keep current"], ...lifecycles]}
            onChange={(value) => setDraft((current) => ({ ...current, lifecycle: value }))}
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" disabled={saving} onClick={() => onSave(record, draft)}>
            {saving ? <LoaderCircle className="size-4 animate-spin" /> : <Check className="size-4" />}
            Save review
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function DecisionRegister() {
  const { getToken } = useAuth();
  const [records, setRecords] = useState([]);
  const [dueRecords, setDueRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filterText, setFilterText] = useState("");
  const [lifecycleFilter, setLifecycleFilter] = useState("all");
  const [dueOnly, setDueOnly] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState(blankDraft());
  const [saving, setSaving] = useState(false);
  const [reviewRecord, setReviewRecord] = useState(null);
  const [reviewDraft, setReviewDraft] = useState({ outcome: "", notes: "", conditions: [], new_review_date: "", lifecycle: "" });
  const [reviewing, setReviewing] = useState(false);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [memoryResults, setMemoryResults] = useState(null);
  const [memoryBusy, setMemoryBusy] = useState(false);

  const accessToken = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    return token;
  };

  const refresh = async () => {
    const token = await accessToken();
    const [next, due] = await Promise.all([
      getDecisionRecords(token),
      getDueDecisionRecords(token),
    ]);
    setRecords(next);
    setDueRecords(due);
  };

  useEffect(() => {
    refresh()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const needle = filterText.trim().toLowerCase();
    return records.filter((record) => {
      if (lifecycleFilter !== "all" && record.lifecycle !== lifecycleFilter) return false;
      if (dueOnly && !record.is_review_due) return false;
      if (!needle) return true;
      const haystack = [
        record.decision, record.rationale, record.board_recommendation,
        record.founder_notes, record.success_criteria, record.actual_outcome,
        record.owner, record.meeting_title,
        ...(record.conditions || []).map((condition) => condition.label),
      ].join(" ").toLowerCase();
      return haystack.includes(needle);
    });
  }, [records, filterText, lifecycleFilter, dueOnly]);

  const stats = useMemo(() => ({
    open: records.filter((record) => record.lifecycle === "open").length,
    under_review: records.filter((record) => record.lifecycle === "under_review").length,
    due: dueRecords.length,
    closed: records.filter((record) => record.lifecycle === "closed" || record.lifecycle === "superseded").length,
  }), [records, dueRecords]);

  const openNew = () => { setDraft(blankDraft()); setEditorOpen(true); };
  const openEdit = (record) => {
    setDraft({
      ...record,
      target_date: record.target_date || "",
      review_date: record.review_date || "",
      conditions: (record.conditions || []).map((condition) => ({ ...condition })),
    });
    setEditorOpen(true);
  };
  const closeEditor = () => { setEditorOpen(false); setDraft(blankDraft()); };
  const openReview = (record) => {
    setReviewRecord(record);
    setReviewDraft({
      outcome: record.actual_outcome || "",
      notes: "",
      conditions: (record.conditions || []).map((condition) => ({ ...condition })),
      new_review_date: record.review_date || "",
      lifecycle: "",
    });
  };
  const closeReview = () => setReviewRecord(null);

  const saveRecord = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      const body = {
        ...draft,
        target_date: draft.target_date || null,
        review_date: draft.review_date || null,
      };
      if (draft.id) await updateDecisionRecord(draft.id, body, token);
      else await createDecisionRecord(body, token);
      await refresh();
      closeEditor();
      setNotice(draft.id ? "Decision record updated." : "Decision record added.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const saveReview = async (record, review) => {
    setReviewing(true);
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      await reviewDecisionRecord(record.id, {
        outcome: review.outcome,
        notes: review.notes,
        new_review_date: review.new_review_date || null,
        lifecycle: review.lifecycle || undefined,
        conditions: review.conditions,
      }, token);
      await refresh();
      closeReview();
      setNotice(`Review recorded for DECISION-${record.id}.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setReviewing(false);
    }
  };

  const removeRecord = async (record) => {
    if (!window.confirm(`Delete decision record "${record.decision}"? Its conclave link remains in the archive.`)) return;
    setBusy(true);
    setError("");
    try {
      const token = await accessToken();
      await deleteDecisionRecord(record.id, token);
      await refresh();
      setNotice("Decision record removed.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const syncAll = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      const result = await syncDecisionRecords(token);
      await refresh();
      setNotice(`Backfilled register from conclave resolutions: ${result.created} created, ${result.updated} updated.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const searchMemory = async (event) => {
    event.preventDefault();
    setMemoryBusy(true);
    setError("");
    try {
      const token = await accessToken();
      const result = await recallMemory(memoryQuery, { limit: 5 }, token);
      setMemoryResults(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setMemoryBusy(false);
    }
  };

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[9px] tracking-[0.2em] text-primary/80">PROGRAMME 3 · DECISION INTELLIGENCE</p>
          <h2 className="mt-1 font-heading text-xl tracking-wide">Decision Register</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Every founder decree, its board recommendation, tracked conditions and actual outcome —
            revisited automatically when the review date arrives or a condition changes.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={syncAll} disabled={busy} className="gap-1.5">
            <RefreshCw className={`size-3.5 ${busy ? "animate-spin" : ""}`} /> Sync from conclaves
          </Button>
          <Button size="sm" onClick={openNew} className="gap-1.5">
            <Plus className="size-3.5" /> New decision record
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <CircleAlert className="size-4" />
          <AlertTitle>Decision register error</AlertTitle>
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

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Open", stats.open, "text-primary"],
          ["Under review", stats.under_review, "text-amber-300"],
          ["Review due now", stats.due, "text-amber-300"],
          ["Closed / superseded", stats.closed, "text-emerald-300"],
        ].map(([label, value, tone]) => (
          <Card key={label} className="border-border/70 bg-card/80">
            <CardContent className="p-4">
              <p className="font-mono text-[9px] tracking-[0.14em] text-muted-foreground">{label.toUpperCase()}</p>
              <p className={`mt-1 font-heading text-2xl ${tone}`}>{value}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.85fr)]">
        <Card className="border-border/70 bg-card/80">
          <CardHeader className="gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="flex items-center gap-2 font-heading text-lg">
                <Gavel className="size-4 text-primary" /> Register
              </CardTitle>
              <Badge variant="outline" className="font-mono text-[9px] tracking-[0.12em]">
                {filtered.length} RECORDS
              </Badge>
            </div>
            <CardDescription>
              Filter the register; open a record to edit its fields, conditions and outcome.
            </CardDescription>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                value={filterText}
                onChange={(event) => setFilterText(event.target.value)}
                placeholder="Search decisions, owners, conditions, outcomes…"
                className="h-9"
              />
              <select
                aria-label="Lifecycle filter"
                value={lifecycleFilter}
                onChange={(event) => setLifecycleFilter(event.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground sm:w-44"
              >
                <option value="all">All lifecycles</option>
                {lifecycles.map(([value, title]) => (
                  <option value={value} key={value}>{title}</option>
                ))}
              </select>
              <Button
                type="button"
                variant={dueOnly ? "secondary" : "outline"}
                size="sm"
                className="h-9 w-full sm:w-auto"
                onClick={() => setDueOnly((current) => !current)}
              >
                <CalendarClock className="size-3.5" /> Review due only
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" /> Loading the register…
              </div>
            ) : !filtered.length ? (
              <p className="rounded-lg border border-dashed border-border/70 p-5 text-center text-sm text-muted-foreground">
                No decision records match. Add one manually, or sync from existing conclave decrees.
              </p>
            ) : (
              <div className="grid gap-3">
                {filtered.map((record) => (
                  <article key={record.id} className="rounded-lg border border-border/70 bg-background/50 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[10px] text-primary">DECISION-{record.id}</span>
                      <Badge variant="outline" className={`text-[9px] uppercase tracking-[0.1em] ${lifecycleBadge(record.lifecycle)}`}>
                        {(record.lifecycle || "open").replaceAll("_", " ")}
                      </Badge>
                      {record.founder_decision && (
                        <Badge variant="outline" className="text-[9px] uppercase tracking-[0.1em]">
                          Decree · {record.founder_decision}
                        </Badge>
                      )}
                      {record.is_review_due && (
                        <Badge className="bg-amber-400/15 text-amber-300 text-[9px] uppercase tracking-[0.1em]">
                          <CalendarClock className="mr-1 size-3" /> Review due
                        </Badge>
                      )}
                      <span className="ml-auto font-mono text-[9px] text-muted-foreground">
                        {new Date(record.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                    <h3 className="mt-2 text-sm font-semibold leading-6">{record.decision}</h3>
                    {record.rationale && (
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{record.rationale}</p>
                    )}
                    <div className="mt-2 grid gap-1 text-[11px] text-muted-foreground sm:grid-cols-2">
                      {record.board_recommendation && (
                        <p className="truncate"><span className="font-medium text-foreground">Board rec:</span> {record.board_recommendation}</p>
                      )}
                      {record.owner && <p><span className="font-medium text-foreground">Owner:</span> {record.owner}</p>}
                      {record.target_date && <p><span className="font-medium text-foreground">Target:</span> {record.target_date}</p>}
                      {record.review_date && <p><span className="font-medium text-foreground">Review:</span> {record.review_date}</p>}
                      {record.meeting_title && (
                        <p className="sm:col-span-2"><span className="font-medium text-foreground">From conclave:</span> {record.meeting_title}</p>
                      )}
                    </div>
                    {record.conditions?.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {record.conditions.map((condition) => (
                          <span key={condition.id} className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-background/60 px-2 py-0.5 text-[10px]">
                            <span className={`size-1.5 rounded-full ${conditionDot(condition.status)}`} />
                            {condition.label}
                            <span className="capitalize text-muted-foreground">· {condition.status}</span>
                          </span>
                        ))}
                      </div>
                    )}
                    {record.actual_outcome && (
                      <p className="mt-2 rounded-md border-l-2 border-primary/40 bg-primary/5 p-2 text-[11px] leading-5 text-muted-foreground">
                        <span className="font-medium text-foreground">Outcome: </span>{record.actual_outcome}
                      </p>
                    )}
                    <div className="mt-3 flex gap-2">
                      <Button size="sm" variant="outline" className="gap-1.5" onClick={() => openEdit(record)}>
                        <Pencil className="size-3.5" /> Edit
                      </Button>
                      <Button size="sm" variant="outline" className="gap-1.5" onClick={() => openReview(record)}>
                        <History className="size-3.5" /> Review
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid h-fit gap-5">
          <Card className="border-border/70 bg-card/80">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 font-heading text-lg">
                <BookOpen className="size-4 text-primary" /> Institutional memory
              </CardTitle>
              <CardDescription>
                Controlled retrieval: ask the register for the prior decisions relevant to a
                future meeting. Nothing is injected anywhere automatically.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={searchMemory} className="flex flex-col gap-2 sm:flex-row">
                <Input
                  value={memoryQuery}
                  onChange={(event) => setMemoryQuery(event.target.value)}
                  minLength={2}
                  maxLength={300}
                  required
                  placeholder="e.g. seizure detection pilot"
                />
                <Button type="submit" disabled={memoryBusy} className="gap-1.5">
                  {memoryBusy ? <LoaderCircle className="size-4 animate-spin" /> : <Search className="size-4" />}
                  Recall
                </Button>
              </form>
              {memoryResults && (
                <div className="space-y-3">
                  <p className="font-mono text-[9px] tracking-[0.12em] text-muted-foreground">
                    {memoryResults.total_matches} MATCHING RECORD{memoryResults.total_matches === 1 ? "" : "S"} · BOUNDED TO {memoryResults.records.length}
                  </p>
                  {memoryResults.records.map((record) => (
                    <article key={record.id} className="rounded-lg border border-border/70 bg-background/50 p-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[10px] text-primary">DECISION-{record.id}</span>
                        <Badge variant="outline" className="ml-auto font-mono text-[9px]">
                          {(record.score * 100).toFixed(0)}% MATCH
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs font-medium leading-5">{record.decision}</p>
                      <p className="mt-1 text-[10px] text-muted-foreground">
                        {record.meeting_title || "No conclave link"}
                        {record.review_date ? ` · review ${record.review_date}` : ""}
                        {record.actual_outcome ? ` · outcome: ${record.actual_outcome}` : " · not yet reviewed"}
                      </p>
                    </article>
                  ))}
                  {!memoryResults.records.length && (
                    <p className="rounded-lg border border-dashed border-border/70 p-3 text-xs text-muted-foreground">
                      No prior decisions match that query yet.
                    </p>
                  )}
                  <details className="rounded-md border border-border/60 bg-background/40 p-2">
                    <summary className="cursor-pointer font-mono text-[9px] tracking-[0.12em] text-muted-foreground">
                      CONTEXT BLOCK INJECTED INTO PROMPTS
                    </summary>
                    <pre className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-[10px] leading-4 text-muted-foreground">
                      {memoryResults.context_block}
                    </pre>
                  </details>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 font-heading text-lg">
                <CalendarClock className="size-4 text-primary" /> Follow-up queue
              </CardTitle>
              <CardDescription>
                Decisions whose review date arrived or whose tracked conditions changed.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {dueRecords.length ? (
                <div className="grid gap-2">
                  {dueRecords.slice(0, 5).map((record) => (
                    <div key={record.id} className="flex items-start gap-2 rounded-md border border-border/70 bg-background/50 p-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium leading-5">{record.decision}</p>
                        <p className="mt-0.5 font-mono text-[9px] text-muted-foreground">
                          DECISION-{record.id} · {(record.lifecycle || "open").replaceAll("_", " ")}
                          {record.review_date ? ` · review ${record.review_date}` : " · condition changed"}
                        </p>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => openReview(record)}>
                        Review
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg border border-dashed border-border/70 p-3 text-xs text-muted-foreground">
                  Nothing is due for review right now.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      <DecisionEditor
        open={editorOpen}
        onOpenChange={(open) => { if (!open) closeEditor(); }}
        draft={draft}
        setDraft={setDraft}
        onSave={saveRecord}
        onDelete={removeRecord}
        saving={saving}
      />

      <ReviewDialog
        open={!!reviewRecord}
        onOpenChange={(open) => { if (!open) closeReview(); }}
        record={reviewRecord}
        draft={reviewDraft}
        setDraft={setReviewDraft}
        onSave={saveReview}
        saving={reviewing}
      />
    </div>
  );
}
