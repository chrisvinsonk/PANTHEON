import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  Activity,
  Award,
  CalendarClock,
  CheckCircle2,
  Gauge,
  LoaderCircle,
  MessageSquarePlus,
  ScrollText,
  TrendingDown,
  TrendingUp,
  UsersRound,
} from "lucide-react";
import {
  getPerformance,
  getPerformanceContributions,
  submitExecutiveFeedback,
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const lifecycles = {
  open: "border-primary/40 text-primary",
  under_review: "border-amber-400/40 text-amber-300",
  closed: "border-emerald-400/40 text-emerald-300",
  superseded: "border-muted-foreground/40 text-muted-foreground",
};

const dimensionLabels = {
  evidence_discipline: "Evidence discipline",
  mandate_adherence: "Mandate adherence",
  challenge_quality: "Challenge quality",
  position_integrity: "Position integrity",
  specificity: "Specificity",
  forecast_accuracy: "Forecast accuracy",
  decision_usefulness: "Decision usefulness",
};

const roles = ["CEO", "CFO", "CTO", "CSO"];

const scoreColor = (score) => {
  if (score == null) return "text-muted-foreground";
  if (score >= 75) return "text-emerald-300";
  if (score >= 50) return "text-amber-300";
  return "text-destructive";
};

const scoreBar = (score) => {
  if (score == null) return "bg-muted-foreground/30";
  if (score >= 75) return "bg-emerald-400/70";
  if (score >= 50) return "bg-amber-400/70";
  return "bg-destructive/70";
};

function Metric({ label, value, icon: Icon, tone = "text-foreground" }) {
  return (
    <Card className="border-border/70 bg-card/70">
      <CardContent className="flex items-center gap-4 p-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-border bg-background text-muted-foreground">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0">
          <p className={`font-heading text-2xl leading-none ${tone}`}>{value}</p>
          <p className="mt-1 truncate text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function Scorecard({ card }) {
  const trend = card.trend;
  return (
    <Card className="border-border/70 bg-card/80">
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 font-heading text-xl">
            <Badge variant="outline" className="border-primary/30 font-mono text-[9px] tracking-[0.12em] text-primary">
              {card.role}
            </Badge>
            <span className={`font-heading text-2xl ${scoreColor(card.overall_score)}`}>
              {card.overall_score == null ? "—" : card.overall_score}
            </span>
            <span className="text-xs font-normal text-muted-foreground">/ 100</span>
          </CardTitle>
          <CardDescription>
            {card.contributions} contribution(s) · {card.feedback_count} founder rating(s)
          </CardDescription>
        </div>
        {trend != null && (
          <Badge variant="outline" className={`gap-1 ${trend >= 0 ? "border-emerald-400/40 text-emerald-300" : "border-destructive/40 text-destructive"}`}>
            {trend >= 0 ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
            {trend >= 0 ? "+" : ""}{trend}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {card.metrics.map((metric) => (
          <div key={metric.key} className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-foreground">{metric.label}</span>
              <span className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground">
                  {metric.signal}
                </Badge>
                <span className={`font-mono text-xs ${scoreColor(metric.score)}`}>
                  {metric.score == null ? "unrated" : metric.score}
                </span>
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted/60">
              <div
                className={`h-full rounded-full ${scoreBar(metric.score)}`}
                style={{ width: `${metric.score == null ? 0 : Math.max(4, metric.score)}%` }}
              />
            </div>
            <p className="text-[10px] leading-4 text-muted-foreground">{metric.note}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function Performance() {
  const { getToken } = useAuth();
  const [data, setData] = useState(null);
  const [contributions, setContributions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [feedbackTarget, setFeedbackTarget] = useState(null);
  const [feedbackDraft, setFeedbackDraft] = useState({
    dimension: "decision_usefulness",
    rating: 4,
    notes: "",
  });
  const [savingFeedback, setSavingFeedback] = useState(false);

  const accessToken = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    return token;
  };

  const load = async () => {
    const token = await accessToken();
    const [performance, reviews] = await Promise.all([
      getPerformance(token),
      getPerformanceContributions(token, { limit: 25 }),
    ]);
    setData(performance);
    setContributions(reviews);
  };

  useEffect(() => {
    load()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const filteredContributions = useMemo(
    () => (roleFilter ? contributions.filter((review) => review.role === roleFilter) : contributions),
    [contributions, roleFilter],
  );

  const openFeedback = (review) => {
    const existing = (review.feedback || []).find(
      (row) => row.dimension === feedbackDraft.dimension,
    );
    setFeedbackTarget(review);
    setFeedbackDraft({
      dimension: existing?.dimension || "decision_usefulness",
      rating: existing?.rating || 4,
      notes: existing?.notes || "",
    });
  };

  const saveFeedback = async () => {
    if (!feedbackTarget) return;
    setSavingFeedback(true);
    setError("");
    try {
      const token = await accessToken();
      await submitExecutiveFeedback(
        {
          role: feedbackTarget.role,
          dimension: feedbackDraft.dimension,
          rating: feedbackDraft.rating,
          meeting_id: feedbackTarget.meeting_id,
          contribution_id: feedbackTarget.contribution_id,
          notes: feedbackDraft.notes,
        },
        token,
      );
      setNotice("Founder feedback saved.");
      setFeedbackTarget(null);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingFeedback(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading performance…
      </div>
    );
  }

  if (error && !data) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Performance unavailable</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  const executives = data?.executives || [];
  const outcomes = data?.recent_outcomes || [];
  const scorecards = data?.scorecards || [];
  const decided = (data?.approved ?? 0) + (data?.rejected ?? 0) + (data?.deferred ?? 0) + (data?.revision_requested ?? 0);
  const approvalRate = decided ? Math.round(((data.approved ?? 0) / decided) * 100) : 0;

  return (
    <section className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Performance request failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Decisions recorded" value={data?.decisions_total ?? 0} icon={Gauge} />
        <Metric label="With recorded outcome" value={data?.decisions_with_outcome ?? 0} icon={CheckCircle2} tone="text-emerald-300" />
        <Metric label="Open decisions" value={data?.open_decisions ?? 0} icon={Activity} tone="text-primary" />
        <Metric
          label="Reviews due"
          value={data?.due_decisions ?? 0}
          icon={CalendarClock}
          tone={data?.due_decisions ? "text-amber-300" : "text-foreground"}
        />
      </div>

      <section className="space-y-3">
        <div>
          <h3 className="flex items-center gap-2 font-heading text-xl">
            <Gauge className="size-4 text-primary" /> Executive scorecard
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Seven quality dimensions. Agreement with the founder is never measured or rewarded.
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {scorecards.map((card) => (
            <Scorecard key={card.role} card={card} />
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <h3 className="flex items-center gap-2 font-heading text-xl">
              <MessageSquarePlus className="size-4 text-primary" /> Founder feedback
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Rate individual contributions on usefulness and forecast accuracy. These are quality judgements, not agreement checks.
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            {["", ...roles].map((role) => (
              <Button
                key={role || "all"}
                variant={roleFilter === role ? "default" : "outline"}
                size="sm"
                onClick={() => setRoleFilter(role)}
              >
                {role || "All"}
              </Button>
            ))}
          </div>
        </div>

        {filteredContributions.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {filteredContributions.map((review) => (
              <Card key={review.contribution_id} className="border-border/70 bg-card/70">
                <CardHeader className="space-y-2 pb-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="border-primary/30 font-mono text-[9px] text-primary">
                        {review.role}
                      </Badge>
                      <span className="truncate text-sm font-medium text-foreground">{review.meeting_title}</span>
                    </div>
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {new Date(review.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <CardDescription className="leading-5">{review.assessment_excerpt}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {review.challenge_excerpt && (
                    <p className="text-xs leading-5 text-muted-foreground">
                      <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-primary/80">Challenge</span>{" "}
                      {review.challenge_excerpt}
                    </p>
                  )}
                  {review.revision_excerpt && (
                    <p className="text-xs leading-5 text-muted-foreground">
                      <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-primary/80">Revision</span>{" "}
                      {review.revision_excerpt}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-1">
                    {(review.feedback || []).map((row) => (
                      <Badge key={row.id} variant="secondary" className="text-[10px]">
                        {dimensionLabels[row.dimension] || row.dimension}: {row.rating}/5
                      </Badge>
                    ))}
                    {!(review.feedback || []).length && (
                      <span className="text-[11px] text-muted-foreground">No founder feedback yet.</span>
                    )}
                  </div>
                  <div className="flex justify-end border-t border-border/60 pt-3">
                    <Button variant="outline" size="sm" className="gap-1.5" onClick={() => openFeedback(review)}>
                      <MessageSquarePlus className="size-3.5" /> Rate contribution
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <Card className="border-dashed border-border/80 bg-card/40">
            <CardContent className="grid min-h-32 place-items-center text-center">
              <div className="space-y-2">
                <UsersRound className="mx-auto size-5 text-muted-foreground" />
                <p className="text-sm font-medium">No contributions to review yet</p>
                <p className="text-xs text-muted-foreground">Run a conclave to generate executive contributions.</p>
              </div>
            </CardContent>
          </Card>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="border-border/70 bg-card/80">
          <CardHeader>
            <CardTitle className="font-heading text-xl">Founder outcomes</CardTitle>
            <CardDescription>How the founder has resolved council recommendations.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              ["Approved", data?.approved ?? 0, "text-emerald-300"],
              ["Rejected", data?.rejected ?? 0, "text-destructive"],
              ["Deferred", data?.deferred ?? 0, "text-amber-300"],
              ["Revision requested", data?.revision_requested ?? 0, "text-primary"],
            ].map(([label, value, tone]) => (
              <div key={label} className="flex items-center justify-between border-b border-border/50 pb-2 text-sm last:border-0 last:pb-0">
                <span className="text-muted-foreground">{label}</span>
                <span className={`font-heading text-lg ${tone}`}>{value}</span>
              </div>
            ))}
            <div className="rounded-lg border border-border/60 bg-background/40 p-3">
              <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">Approval rate</p>
              <p className="mt-1 font-heading text-2xl text-foreground">{approvalRate}%</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {data?.meetings_completed ?? 0} of {data?.meetings_total ?? 0} conclaves completed
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/70 bg-card/80 lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 font-heading text-xl">
              <UsersRound className="size-4 text-primary" /> Council activity
            </CardTitle>
            <CardDescription>Contributions, challenges and revisions by role.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {executives.map((executive) => (
              <div key={executive.role} className="rounded-lg border border-border/60 bg-background/40 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="border-primary/30 font-mono text-[9px] tracking-[0.12em] text-primary">
                      {executive.role}
                    </Badge>
                    {executive.models?.length ? (
                      executive.models.map((model) => (
                        <Badge key={model} variant="secondary" className="font-mono text-[9px]">{model}</Badge>
                      ))
                    ) : (
                      <span className="text-xs text-muted-foreground">No model activity yet</span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {executive.last_active_at ? new Date(executive.last_active_at).toLocaleString() : "Never active"}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  {[
                    ["Assessments", executive.assessments],
                    ["Challenges", executive.challenges],
                    ["Revisions", executive.revisions],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-md border border-border/50 bg-card/60 p-2">
                      <p className="font-heading text-lg leading-none">{value}</p>
                      <p className="mt-1 text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{label}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {!executives.length && <p className="text-sm text-muted-foreground">No executive activity recorded yet.</p>}
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/70 bg-card/80">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-heading text-xl">
            <Award className="size-4 text-amber-300" /> Decision outcomes
          </CardTitle>
          <CardDescription>Closed decisions and their recorded results.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {outcomes.length ? (
            outcomes.map((outcome) => (
              <div key={outcome.decision_id} className="rounded-lg border border-border/60 bg-background/40 p-3">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-medium leading-6 text-foreground">{outcome.decision}</p>
                  <Badge variant="outline" className={`shrink-0 capitalize ${lifecycles[outcome.lifecycle] || ""}`}>
                    {(outcome.lifecycle || "open").replaceAll("_", " ")}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Founder: {outcome.founder_decision || "pending"}
                  {outcome.review_date ? ` · Review ${outcome.review_date}` : ""}
                  {` · Updated ${new Date(outcome.updated_at).toLocaleDateString()}`}
                </p>
                {outcome.actual_outcome && (
                  <p className="mt-2 text-sm leading-5 text-muted-foreground">
                    <ScrollText className="mr-1 inline size-3.5" />
                    {outcome.actual_outcome}
                  </p>
                )}
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">
              No outcomes recorded yet. Close a decision and record its result in the Decision Register.
            </p>
          )}
        </CardContent>
      </Card>

      <Dialog open={Boolean(feedbackTarget)} onOpenChange={(open) => !open && setFeedbackTarget(null)}>
        <DialogContent className="max-w-xl border-border/80 bg-card">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">
              Rate {feedbackTarget?.role} contribution
            </DialogTitle>
            <DialogDescription>
              {feedbackTarget?.meeting_title}. Ratings feed the scorecard's founder dimensions only.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="feedback-dimension">Dimension</Label>
              <select
                id="feedback-dimension"
                value={feedbackDraft.dimension}
                onChange={(event) => setFeedbackDraft((current) => ({ ...current, dimension: event.target.value }))}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
              >
                {Object.entries(dimensionLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                Evidence discipline, mandate adherence, challenge quality, position integrity and specificity are scored automatically. Use founder feedback for judgement-based dimensions.
              </p>
            </div>
            <div className="grid gap-2">
              <Label>Rating</Label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map((rating) => (
                  <Button
                    key={rating}
                    type="button"
                    variant={feedbackDraft.rating === rating ? "default" : "outline"}
                    size="sm"
                    className="w-10"
                    onClick={() => setFeedbackDraft((current) => ({ ...current, rating }))}
                  >
                    {rating}
                  </Button>
                ))}
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="feedback-notes">Notes</Label>
              <Textarea
                id="feedback-notes"
                rows={3}
                maxLength={2000}
                value={feedbackDraft.notes}
                onChange={(event) => setFeedbackDraft((current) => ({ ...current, notes: event.target.value }))}
                placeholder="Why this rating? Specificity, evidence, usefulness…"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFeedbackTarget(null)}>Cancel</Button>
            <Button onClick={saveFeedback} disabled={savingFeedback} className="gap-2">
              {savingFeedback && <LoaderCircle className="size-4 animate-spin" />} Save feedback
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
