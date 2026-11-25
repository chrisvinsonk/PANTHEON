import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Crown,
  Download,
  Expand,
  Landmark,
  LoaderCircle,
  ScrollText,
  Shield,
  Sparkles,
  Timer,
  UsersRound,
} from "lucide-react";
import {
  createMeeting,
  getEvidenceRecords,
  getMeetingProgress,
  getMeetings,
  recallMemory,
  recordDecision,
  runMeeting,
} from "../api";
import Sidebar from "./Sidebar";
import CompanySwitcher from "./CompanySwitcher";
import SpotlightCard from "./SpotlightCard";
import CommandCentre from "./CommandCentre";
import { downloadBoardMeetingReport } from "../lib/board-report-pdf";
import {
  formatBoardSynthesis,
  formatExecutiveAssessment,
  formatPositionExtraction,
  formatPositionRevision,
  formatTargetedCrossExamination,
} from "../lib/structured-agent-output";
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
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Textarea } from "@/components/ui/textarea";

const MarkdownContent = lazy(() => import("./MarkdownContent"));
const ModelSources = lazy(() => import("./ModelSources"));
const EvidenceRegister = lazy(() => import("./EvidenceRegister"));
const DecisionRegister = lazy(() => import("./DecisionRegister"));
const KnowledgeVault = lazy(() => import("./KnowledgeVault"));
const Performance = lazy(() => import("./Performance"));
const Configuration = lazy(() => import("./Configuration"));
const Operations = lazy(() => import("./Operations"));
const HowToUse = lazy(() => import("./HowToUse"));

function MarkdownResponse({ children, className = "" }) {
  return (
    <Suspense fallback={<div className={`whitespace-pre-wrap break-words ${className}`}>{children}</div>}>
      <MarkdownContent className={className}>{children}</MarkdownContent>
    </Suspense>
  );
}

const roles = {
  CEO: [
    "Chief Executive Officer",
    "Realm strategy, mortals and growth",
    "Set strategic priorities and growth goals, align the executive team, and ensure the company advances its mission responsibly.",
  ],
  CFO: [
    "Chief Financial Officer",
    "Tribute, coffers and unit economics",
    "Guide financial planning, cash flow, budgets, and unit economics; assess financial risks and allocate capital responsibly.",
  ],
  CTO: [
    "Chief Technology Officer",
    "Temple architecture and craft",
    "Guide technical architecture, engineering execution, security, and scalability while aligning product decisions with technical constraints.",
  ],
  CSO: [
    "Chief Scientific Officer",
    "Celestial omens and sacred validity",
    "Lead scientific rigor, evidence quality, research priorities, and ethical standards; distinguish validated findings from hypotheses.",
  ],
};

const roleIcons = { CEO: Crown, CFO: Landmark, CTO: Shield, CSO: Sparkles };
const viewTitles = {
  chamber: ["Divine Council", "Independent executive oracles. Structured challenge. Founder-controlled decrees."],
  executives: ["Executive Oracles", "Four independent perspectives, aligned to the Pantheon's mission."],
  conclaves: ["Archive of Conclaves", "Recorded council sessions and founder decrees."],
  models: ["Model Sources", "BYOK: bring your own API keys (stored encrypted, never baked in). Connect inference providers and choose a model for each council role."],
  evidence: ["Evidence Register", "Trace claims to sources, assess limitations, and preserve disagreement."],
  decisions: ["Decision Register", "Founder decrees, tracked conditions, outcomes and follow-ups."],
  command_centre: ["Command Centre", "Company status, priorities, decisions and risks"],
  vault: ["Knowledge Vault", "Research, evidence, documents and the company knowledge the council can rely on."],
  performance: ["Performance", "Executive quality and decision outcomes across conclaves."],
  configuration: ["Configuration", "Company context, executive identities, models and governance."],
  operations: ["Operations", "Approval-gated drafts: plans, models, documents, tasks and reviews."],
};

const statusClass = (status) => {
  if (["completed", "approved"].includes(status)) return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  if (["failed", "rejected"].includes(status)) return "border-destructive/40 bg-destructive/10 text-destructive";
  if (["running", "pending", "revision_requested", "working"].includes(status)) return "border-primary/30 bg-primary/10 text-primary";
  return "border-border bg-muted/50 text-muted-foreground";
};

const formatStatus = (status) => (status || "draft").replaceAll("_", " ");

function StatusBadge({ status }) {
  return (
    <Badge variant="outline" className={`shrink-0 capitalize ${statusClass(status)}`}>
      {formatStatus(status)}
    </Badge>
  );
}

function formatDuration(seconds) {
  const totalSeconds = Math.max(0, Math.ceil(seconds || 0));
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function RunProgress({ events, checkpoints, status, error, progress }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(progress?.elapsed_seconds || 0);
  useEffect(() => {
    setElapsedSeconds(progress?.elapsed_seconds || 0);
  }, [progress?.elapsed_seconds]);
  useEffect(() => {
    if (status !== "running") return undefined;
    const timer = window.setInterval(() => {
      setElapsedSeconds((elapsed) => elapsed + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  const attempt = events.reduce((latest, event) => Math.max(latest, event.attempt), 0);
  const currentEvents = events.filter((event) => event.attempt === attempt);
  const latestFailure = [...currentEvents].reverse().find(
    (event) => event.event_type === "agent_failed",
  ) || [...currentEvents].reverse().find((event) => event.event_type === "run_failed");
  const latestPhase = [...currentEvents]
    .reverse()
    .find((event) => event.event_type === "phase_started" || event.event_type === "phase_completed");
  const trackedRoles = [...Object.keys(roles), "BOARD"];
  const phaseLabels = {
    assessment: "Assessment",
    position_extraction: "Position extraction",
    challenge: "Challenge",
    revision: "Position revision",
    synthesis: "Synthesis",
  };
  const phaseOrder = {
    assessment: 0,
    position_extraction: 1,
    challenge: 2,
    revision: 3,
    synthesis: 4,
  };
  const roleStatuses = trackedRoles.map((role) => {
    const latest = [...currentEvents].reverse().find(
      (event) => event.role === role && event.event_type !== "agent_output",
    );
    if (!latest) return { role, detail: "Waiting", state: "waiting" };
    if (latest.event_type === "agent_started") {
      return { role, detail: `Working · ${phaseLabels[latest.phase] || latest.phase}`, state: "working" };
    }
    if (latest.event_type === "agent_failed") {
      return { role, detail: `Failed · ${phaseLabels[latest.phase] || latest.phase}`, state: "failed" };
    }
    if (["checkpoint_saved", "checkpoint_reused"].includes(latest.event_type)) {
      return {
        role,
        detail: `${latest.event_type === "checkpoint_reused" ? "Restored" : "Complete"} · ${phaseLabels[latest.phase] || latest.phase}`,
        state: "completed",
      };
    }
    if (
      latest.event_type === "agent_completed"
      && status === "running"
      && phaseOrder[latestPhase?.phase] > phaseOrder[latest.phase]
    ) {
      return { role, detail: `Queued · ${phaseLabels[latestPhase.phase]}`, state: "waiting" };
    }
    if (latest.event_type === "agent_completed") {
      return { role, detail: `Complete · ${phaseLabels[latest.phase] || latest.phase}`, state: "completed" };
    }
    return {
      role,
      detail: latest.event_type === "agent_completed"
        ? `Queued · ${phaseLabels[latestPhase?.phase] || "next phase"}`
        : "Waiting",
      state: "waiting",
    };
  });
  const checkpointKeys = new Set(
    checkpoints.map((checkpoint) => `${checkpoint.phase}:${checkpoint.role}`),
  );
  const streams = new Map(checkpoints.map((checkpoint) => [
    `checkpoint:${checkpoint.phase}:${checkpoint.role}`,
    {
      phase: checkpoint.phase,
      role: checkpoint.role,
      text: checkpoint.content,
      state: "completed",
      checkpoint: true,
      reused: false,
    },
  ]));
  for (const event of events) {
    if (!["agent_started", "agent_output", "agent_completed", "agent_failed", "checkpoint_reused"].includes(event.event_type)
      || !event.role) continue;
    const pair = `${event.phase}:${event.role}`;
    if (checkpointKeys.has(pair)) {
      if (event.event_type === "checkpoint_reused") {
        streams.get(`checkpoint:${pair}`).reused = true;
      }
      continue;
    }
    const key = `attempt:${event.attempt}:${pair}`;
    const stream = streams.get(key) || {
      phase: event.phase,
      role: event.role,
      text: "",
      state: "waiting",
      error: "",
      attempt: event.attempt,
      checkpoint: false,
      reused: false,
    };
    if (event.event_type === "agent_started") stream.state = "working";
    if (event.event_type === "agent_output") stream.text += event.message;
    if (event.event_type === "agent_completed") stream.state = "completed";
    if (event.event_type === "agent_failed") {
      stream.state = "failed";
      stream.error = event.message;
    }
    if (event.event_type === "checkpoint_reused") {
      stream.state = "completed";
      stream.reused = true;
    }
    streams.set(key, stream);
  }
  const streamPanels = [...streams.values()];
  const progressPercent = Math.min(100, Math.max(0, progress?.progress_percent || 0));

  if (!events.length && status !== "running") return null;

  return (
    <Card className="border-primary/20 bg-background/70 shadow-none">
      <CardHeader className="gap-3 border-b border-border/60 p-4 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {status === "running"
              ? <Activity className="size-4 animate-pulse text-primary" />
              : status === "failed"
                ? <CircleAlert className="size-4 text-destructive" />
                : <CheckCircle2 className="size-4 text-emerald-400" />}
            <CardTitle className="font-heading text-base tracking-wide">Live run activity</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {attempt > 0 && (
              <Badge variant="outline" className="font-mono text-[9px] tracking-wide">
                ATTEMPT {attempt}
              </Badge>
            )}
            <StatusBadge status={status} />
          </div>
        </div>
        <CardDescription>
          {status === "running"
            ? "The run continues in the background. Updates are saved automatically."
            : "Run activity is saved with this meeting and remains available when you return."}
        </CardDescription>
        {error && <p className="text-xs text-destructive">Progress refresh failed; retrying: {error}</p>}
      </CardHeader>
      {latestFailure && (
        <Alert variant="destructive" className="mx-4 mt-4 sm:mx-5">
          <CircleAlert className="size-4" />
          <AlertTitle>
            {latestFailure.role
              ? `${latestFailure.role} · ${phaseLabels[latestFailure.phase] || latestFailure.phase} failed`
              : "Board run failed"}
          </AlertTitle>
          <AlertDescription className="break-words whitespace-pre-wrap">
            {latestFailure.message || "The service did not return an error description."}
          </AlertDescription>
        </Alert>
      )}
      {currentEvents.length > 0 && (
        <CardContent className="grid gap-4 p-4 sm:p-5">
          <section aria-label="Run progress" className="space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-[9px] tracking-[0.16em] text-muted-foreground">
                LIVE DELIBERATION PROGRESS
              </p>
              <span className="font-mono text-xs tabular-nums text-foreground">
                {Math.round(progressPercent)}%
              </span>
            </div>
            <div
              role="progressbar"
              aria-label="Board deliberation progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progressPercent)}
              className="h-2 overflow-hidden rounded-full bg-muted"
            >
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>Elapsed {formatDuration(elapsedSeconds)}</span>
              <span>
                {status === "running" && progress?.eta_seconds != null
                  ? `Approx. ${formatDuration(progress.eta_seconds)} remaining`
                  : status === "completed"
                    ? `Completed in ${formatDuration(elapsedSeconds)}`
                    : status === "failed"
                      ? "Time estimate unavailable after failure"
                      : "Waiting to start"}
              </span>
            </div>
            {status === "running" && (
              <p className="text-[11px] leading-5 text-muted-foreground">
                {progress?.eta_calibrated
                  ? "Estimate recalibrates from this run's completed agent response times."
                  : "Initial estimate uses your configured local-inference baseline and will recalibrate as agents finish."}
              </p>
            )}
          </section>

          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
            {roleStatuses.map(({ role, detail, state }) => (
              <div key={role} className="flex min-w-0 items-center gap-3 rounded-lg border border-border/70 bg-card/60 p-3">
                <span className={`grid size-8 shrink-0 place-items-center rounded-md ${
                  state === "working"
                    ? "bg-primary/10 text-primary"
                    : state === "failed"
                      ? "bg-destructive/10 text-destructive"
                      : state === "completed"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : "bg-muted text-muted-foreground"
                }`}>
                  {state === "working"
                    ? <LoaderCircle className="size-4 animate-spin" />
                    : state === "failed"
                      ? <CircleAlert className="size-4" />
                      : state === "completed"
                        ? <CheckCircle2 className="size-4" />
                        : <Timer className="size-4" />}
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-semibold">{role}</span>
                  <span className="block truncate text-[10px] text-muted-foreground">{detail}</span>
                </span>
              </div>
            ))}
          </div>

          {streamPanels.length > 0 && (
            <section className="space-y-2">
              <div>
                <p className="font-mono text-[9px] tracking-[0.16em] text-muted-foreground">
                  LIVE AGENT RESPONSES
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Streamed generated response text and work status; private reasoning is not exposed.
                </p>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {streamPanels.map((stream) => (
                  <Card
                    key={`${stream.checkpoint ? "checkpoint" : stream.attempt}:${stream.phase}:${stream.role}`}
                    className="border-border/70 bg-background/60 shadow-none"
                  >
                    <CardHeader className="flex-row items-center justify-between gap-3 space-y-0 p-3">
                      <div className="min-w-0">
                        <CardTitle className="text-xs font-semibold">{stream.role}</CardTitle>
                        <CardDescription className="mt-1 text-[10px]">
                          {phaseLabels[stream.phase] || stream.phase}
                          {stream.attempt ? ` · Attempt ${stream.attempt}` : ""}
                        </CardDescription>
                      </div>
                      <Badge
                        variant="outline"
                        className={`shrink-0 text-[9px] capitalize ${statusClass(stream.state)}`}
                      >
                        {stream.reused
                          ? "Checkpoint restored"
                          : stream.checkpoint
                            ? "Saved checkpoint"
                            : stream.state === "working"
                              ? "Streaming"
                              : stream.state}
                      </Badge>
                    </CardHeader>
                    <CardContent className="px-3 pb-3">
                      {stream.error && (
                        <Alert variant="destructive" className="mb-2 px-3 py-2">
                          <AlertDescription className="break-words whitespace-pre-wrap text-xs">
                            {stream.error}
                          </AlertDescription>
                        </Alert>
                      )}
                      <ScrollArea className="h-36 rounded-md border border-border/50 bg-card/60 p-3">
                        <MarkdownResponse className="text-xs leading-5 text-muted-foreground">
                          {stream.text
                            ? stream.phase === "assessment"
                              ? formatExecutiveAssessment(stream.text)
                              : stream.phase === "position_extraction"
                                ? formatPositionExtraction(stream.text)
                              : stream.phase === "revision"
                                ? formatPositionRevision(stream.text)
                                : stream.phase === "challenge"
                                  ? formatTargetedCrossExamination(stream.text, checkpoints)
                                : stream.phase === "synthesis"
                                  ? formatBoardSynthesis(stream.text)
                                  : stream.text
                            : stream.state === "working"
                              ? "Waiting for the model's first response text…"
                              : stream.state === "failed"
                                ? "This agent did not complete."
                                : "No response text was produced."}
                        </MarkdownResponse>
                      </ScrollArea>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </section>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono text-[9px] tracking-[0.16em] text-muted-foreground">PERSISTENT EVENT LOG</p>
              {latestPhase && (
                <Badge variant="secondary" className="text-[10px]">
                  {phaseLabels[latestPhase.phase] || latestPhase.phase}
                </Badge>
              )}
            </div>
            <ScrollArea className="h-52 rounded-lg border border-border/70 bg-background/70">
              <ol className="grid gap-0 p-3">
                {events.filter((event) => event.event_type !== "agent_output").map((event) => (
                  <li key={event.id} className="flex gap-3 border-b border-border/40 py-2.5 last:border-0">
                    <span className={`mt-1 size-1.5 shrink-0 rounded-full ${
                      event.event_type === "agent_failed" || event.event_type === "run_failed"
                        ? "bg-destructive"
                        : event.event_type === "agent_completed" || event.event_type === "run_completed"
                          ? "bg-emerald-400"
                          : "bg-primary"
                    }`} />
                    <span className="min-w-0 flex-1 text-xs leading-5 text-muted-foreground">
                      {event.message}
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <span className="font-mono text-[8px] text-muted-foreground/70">
                        A{event.attempt}
                      </span>
                      <time className="font-mono text-[9px] text-muted-foreground/70">
                        {new Date(event.created_at).toLocaleTimeString()}
                      </time>
                    </span>
                  </li>
                ))}
              </ol>
            </ScrollArea>
          </div>
          {Array.isArray(progress?.evidence_register) && (
            <section className="space-y-2">
              <p className="flex items-center gap-2 font-mono text-[9px] tracking-[0.16em] text-muted-foreground">
                <BookOpen className="size-3.5 text-primary" />
                EVIDENCE SNAPSHOT USED FOR THIS RUN
              </p>
              {progress.evidence_register.length ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  {progress.evidence_register.map((item) => (
                    <div key={item.id} className="rounded-lg border border-border/70 bg-background/60 p-3">
                      <p className="text-xs font-medium leading-5">
                        <span className="mr-1 font-mono text-primary">EVIDENCE-{item.id}</span>
                        {item.claim}
                      </p>
                      <p className="mt-1 text-[10px] capitalize text-muted-foreground">
                        {item.category} · {item.classification} · quality {item.evidence_quality}
                        {item.publication_date ? ` · published ${item.publication_date}` : ""}
                      </p>
                      {item.source_url && (
                        <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 break-all text-[10px] text-primary hover:underline">
                          {item.source_reference || item.source_title || item.source_url}
                          <ArrowUpRight className="size-3 shrink-0" />
                        </a>
                      )}
                      {item.challenged && <p className="mt-1 text-[10px] text-amber-200">Challenged by {(item.challenged_by || []).join(", ") || "the council"}</p>}
                      {item.disputed && <p className="mt-1 text-[10px] text-destructive">Disputed by {(item.disputed_by || []).join(", ") || "the council"}</p>}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg border border-dashed border-border/70 p-3 text-xs text-muted-foreground">
                  No Evidence Register entries were attached when this run started.
                </p>
              )}
            </section>
          )}
          {Array.isArray(progress?.institutional_memory) && progress.institutional_memory.length > 0 && (
            <section className="space-y-2">
              <p className="flex items-center gap-2 font-mono text-[9px] tracking-[0.16em] text-muted-foreground">
                <BookOpen className="size-3.5 text-primary" />
                INSTITUTIONAL MEMORY RECALLED FOR THIS RUN · CONTROLLED RETRIEVAL
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {progress.institutional_memory.map((item) => (
                  <div key={item.id} className="rounded-lg border border-border/70 bg-background/60 p-3">
                    <p className="text-xs font-medium leading-5">
                      <span className="mr-1 font-mono text-primary">DECISION-{item.id}</span>
                      {item.decision}
                    </p>
                    <p className="mt-1 text-[10px] capitalize text-muted-foreground">
                      Decree {item.founder_decision || "recorded"} · {item.lifecycle}
                      {item.review_date ? ` · review ${item.review_date}` : ""}
                    </p>
                    {item.actual_outcome && (
                      <p className="mt-1 text-[10px] leading-4 text-muted-foreground">{item.actual_outcome}</p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </CardContent>
      )}
    </Card>
  );
}

export default function Dashboard() {
  const { getToken } = useAuth();
  const [dashboardView, setDashboardView] = useState("chamber");
  const [meetings, setMeetings] = useState([]);
  const [evidenceRecords, setEvidenceRecords] = useState([]);
  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState([]);
  const [selected, setSelected] = useState(null);
  const [title, setTitle] = useState("");
  const [agenda, setAgenda] = useState("");
  const [context, setContext] = useState("");
  const [decisionComments, setDecisionComments] = useState("");
  const [includeMemory, setIncludeMemory] = useState(true);
  const [memoryPreview, setMemoryPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState(null);
  const [meetingDialogOpen, setMeetingDialogOpen] = useState(false);
  const [responseDialog, setResponseDialog] = useState(null);
  const [runEvents, setRunEvents] = useState([]);
  const [runCheckpoints, setRunCheckpoints] = useState([]);
  const [progressError, setProgressError] = useState("");
  const [progressSummary, setProgressSummary] = useState(null);
  const progressCursor = useRef(0);
  const shouldDrainProgress = useRef(false);

  const getAccessToken = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    return token;
  };

  const refresh = async (id = selected?.id) => {
    const token = await getAccessToken();
    const [items, evidence] = await Promise.all([
      getMeetings(token),
      getEvidenceRecords(token),
    ]);
    setMeetings(items);
    setEvidenceRecords(evidence);
    const targetId =
      id
      || items.find((meeting) => meeting.status === "running")?.id
      || items.find((meeting) => meeting.status === "failed")?.id;
    if (targetId) setSelected(items.find((meeting) => meeting.id === targetId) || null);
  };

  useEffect(() => {
    refresh()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const selectedId = selected?.id;
  const selectedStatus = selected?.status;
  const activeRun = selected?.status === "running"
    ? selected
    : meetings.find((meeting) => meeting.status === "running");
  const progressMeetingId = activeRun?.id || selectedId;
  const progressMeetingStatus = activeRun?.status || selectedStatus;

  useEffect(() => {
    progressCursor.current = 0;
    shouldDrainProgress.current = false;
    setRunEvents([]);
    setRunCheckpoints([]);
    setProgressError("");
    setProgressSummary(null);
  }, [progressMeetingId]);

  useEffect(() => {
    if (!includeMemory) {
      setMemoryPreview(null);
      return undefined;
    }
    const query = [title, agenda, context].map((part) => part.trim()).filter(Boolean).join("\n");
    if (query.replaceAll(/\s/g, "").length < 12) {
      setMemoryPreview(null);
      return undefined;
    }
    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      try {
        const token = await getAccessToken();
        if (cancelled) return;
        const result = await recallMemory(query, { limit: 3 }, token);
        if (!cancelled) setMemoryPreview(result);
      } catch {
        if (!cancelled) setMemoryPreview(null);
      }
    }, 500);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeMemory, title, agenda, context]);

  useEffect(() => {
    if (!progressMeetingId) return undefined;
    let cancelled = false;
    let timeout;

    const pollProgress = async () => {
      try {
        const token = await getAccessToken();
        const progress = await getMeetingProgress(progressMeetingId, progressCursor.current, token);
        if (cancelled) return;

        if (progress.events.length > 0) {
          progressCursor.current = Math.max(...progress.events.map((event) => event.id));
          setRunEvents((current) => [...current, ...progress.events]);
        }
        if (progress.checkpoints?.length) {
          setRunCheckpoints((current) => {
            const byCheckpoint = new Map(
              current.map((checkpoint) => [
                `${checkpoint.phase}:${checkpoint.role}`,
                checkpoint,
              ]),
            );
            for (const checkpoint of progress.checkpoints) {
              byCheckpoint.set(`${checkpoint.phase}:${checkpoint.role}`, checkpoint);
            }
            return [...byCheckpoint.values()];
          });
        }
        setProgressSummary(progress);
        setSelected((current) =>
          current?.id === progressMeetingId ? progress.meeting : current,
        );
        setMeetings((current) =>
          current.map((meeting) =>
            meeting.id === progressMeetingId ? progress.meeting : meeting,
          ),
        );
        setProgressError("");

        shouldDrainProgress.current =
          progress.meeting.status === "running" || progress.has_more;
        if (shouldDrainProgress.current) {
          timeout = window.setTimeout(pollProgress, progress.has_more ? 250 : 1200);
        }
      } catch (requestError) {
        if (cancelled) return;
        setProgressError(requestError.message);
        if (progressMeetingStatus === "running" || shouldDrainProgress.current) {
          timeout = window.setTimeout(pollProgress, 3000);
        }
      }
    };

    pollProgress();
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [progressMeetingId, progressMeetingStatus]);

  const create = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    let meetingId;
    try {
      const token = await getAccessToken();
      const meeting = await createMeeting(
        {
          title,
          agenda,
          founder_context: context,
          evidence_ids: selectedEvidenceIds,
          include_memory: includeMemory,
        },
        token,
      );
      meetingId = meeting.id;
      setTitle("");
      setAgenda("");
      setContext("");
      setSelectedEvidenceIds([]);
      setMemoryPreview(null);
      setDashboardView("chamber");
      setSelected(meeting);
      await runMeeting(meeting.id, token);
      await refresh(meeting.id);
    } catch (requestError) {
      setError(requestError.message);
      if (meetingId) {
        try {
          await refresh(meetingId);
        } catch (refreshError) {
          setError(`${requestError.message} Refresh failed: ${refreshError.message}`);
        }
      }
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const token = await getAccessToken();
      const meeting = await runMeeting(selected.id, token);
      setSelected(meeting);
      setMeetingDialogOpen(false);
      setResponseDialog(null);
      setDashboardView("chamber");
      await refresh(meeting.id);
    } catch (requestError) {
      setError(requestError.message);
      try {
        await refresh(selected.id);
      } catch (refreshError) {
        setError(`${requestError.message} Refresh failed: ${refreshError.message}`);
      }
    } finally {
      setBusy(false);
    }
  };

  const decide = async (action) => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const token = await getAccessToken();
      const meeting = await recordDecision(
        selected.id,
        { action, comments: decisionComments, actor: "Founder" },
        token,
      );
      setSelected(meeting);
      setDecisionComments("");
      await refresh(meeting.id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const downloadReport = async () => {
    if (!selected || selected.status !== "completed") return;
    setPdfBusy(true);
    setError("");
    try {
      await downloadBoardMeetingReport(selected, progressSummary?.evidence_register || []);
    } catch (downloadError) {
      setError(`Could not create the meeting report PDF: ${downloadError.message}`);
    } finally {
      setPdfBusy(false);
    }
  };

  const contribution = (role, phase) =>
    selected?.contributions?.find((item) => item.role === role && item.phase === phase);
  const status =
    selected?.resolution?.decision_status || selected?.status || "draft";
  const pageTitle = viewTitles[dashboardView] || viewTitles.chamber;
  const openProfile = (role) => setProfile(roles[role]);
  const runningMeeting = meetings.find((meeting) => meeting.status === "running");

  const meetingRows = meetings.map((meeting) => (
    <button
      type="button"
      key={meeting.id}
      onClick={() => {
        setSelected(meeting);
        setDashboardView("conclaves");
        setMeetingDialogOpen(true);
      }}
      className={`group flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors hover:border-primary/35 hover:bg-accent/40 ${
        selected?.id === meeting.id ? "border-primary/40 bg-primary/5" : "border-transparent"
      }`}
    >
      <span className="grid size-9 shrink-0 place-items-center rounded-md border border-border bg-background text-muted-foreground transition-colors group-hover:text-primary">
        <ScrollText className="size-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-foreground">{meeting.title}</span>
        <span className="mt-1 block text-xs text-muted-foreground">
          {new Date(meeting.created_at).toLocaleString()}
        </span>
      </span>
      <StatusBadge status={meeting.resolution?.decision_status || meeting.status} />
    </button>
  ));

  return (
    <SidebarProvider defaultOpen>
      <Sidebar
        activeView={dashboardView}
        onNavigate={(view) => {
          setDashboardView(view);
          if (view !== "conclaves" && view !== "command_centre") {
            setMeetingDialogOpen(false);
            setResponseDialog(null);
          }
        }}
      />
      <SidebarInset className="min-w-0 bg-background">
        <header className="sticky top-0 z-10 flex min-h-16 items-center gap-4 border-b border-border/70 bg-background/85 px-4 backdrop-blur-xl sm:px-6">
          <SidebarTrigger aria-label="Toggle navigation" className="text-muted-foreground" />
          <Separator orientation="vertical" className="!h-7" />
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[9px] tracking-[0.2em] text-primary/80">THE PANTHEON</p>
            <h1 className="truncate text-sm font-semibold text-foreground sm:text-base">{pageTitle[0]}</h1>
          </div>
          <CompanySwitcher onManage={() => setDashboardView("configuration")} />
          {runningMeeting && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSelected(runningMeeting);
                setDashboardView("chamber");
                setMeetingDialogOpen(false);
                setResponseDialog(null);
              }}
              className="max-w-[45vw] gap-2 border-primary/30 text-primary"
            >
              <Activity className="size-3.5 shrink-0 animate-pulse" />
              <span className="truncate">Run active · {runningMeeting.title}</span>
            </Button>
          )}
          <Badge variant="outline" className="hidden gap-2 border-primary/25 font-mono text-[9px] tracking-[0.1em] text-primary sm:flex">
            <span className="size-1.5 rounded-full bg-primary shadow-[0_0_8px_var(--primary)]" />
            FOUNDER AUTHORITY
          </Badge>
        </header>

        <main className="mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
          {error && (
            <Alert variant="destructive">
              <AlertTitle>Council request failed</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {(dashboardView === "chamber" || dashboardView === "conclaves") && (
            <>
              {dashboardView === "chamber" && (
                <>
              <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
                <div className="space-y-2">
                  <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.16em] text-primary">
                    COUNCIL CHAMBER
                  </Badge>
                  <h2 className="font-heading text-2xl tracking-wide sm:text-3xl">{pageTitle[0]}</h2>
                  <p className="max-w-2xl text-sm leading-6 text-muted-foreground">{pageTitle[1]}</p>
                </div>
                <Badge variant="secondary" className="w-fit gap-2 py-1.5 text-xs">
                  <span className="size-1.5 rounded-full bg-primary" />
                  Mortal authority enabled
                </Badge>
              </section>

              <section aria-label="Executive council" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {Object.entries(roles).map(([role, details]) => {
                  const Icon = roleIcons[role];
                  return (
                    <SpotlightCard
                      key={role}
                      spotlightColor="#d4af37"
                      intensity={0.16}
                      className="rounded-xl p-0 transition-transform hover:-translate-y-0.5"
                      style={{
                        padding: 0,
                        background: "var(--card)",
                        border: "1px solid color-mix(in oklab, var(--border) 80%, transparent)",
                        borderRadius: "var(--radius)",
                      }}
                    >
                      <Card className="h-full border-0 bg-transparent shadow-none">
                        <CardContent className="p-4">
                          <button
                            type="button"
                            onClick={() => openProfile(role)}
                            className="flex min-h-40 w-full flex-col text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <span className="flex w-full items-center justify-between">
                              <span className="grid size-10 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                                <Icon className="size-5" />
                              </span>
                              <Badge variant="outline" className="border-emerald-500/25 bg-emerald-500/5 font-mono text-[9px] tracking-[0.12em] text-emerald-300">
                                READY
                              </Badge>
                            </span>
                            <span className="mt-4 font-heading text-lg tracking-wide">{role}</span>
                            <span className="mt-1 text-xs text-muted-foreground">{details[0]}</span>
                            <span className="mt-4 flex items-center gap-1 font-mono text-[9px] tracking-[0.12em] text-primary/70">
                              VIEW MANDATE <ArrowUpRight className="size-3" />
                            </span>
                          </button>
                        </CardContent>
                      </Card>
                    </SpotlightCard>
                  );
                })}
              </section>
                </>
              )}

              {dashboardView === "chamber" && (
                <section className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)]">
                <Card className="border-border/70 bg-card/85 shadow-lg shadow-black/10">
                  <CardHeader className="gap-3 border-b border-border/60 px-5 pb-5 sm:px-6">
                    <div className="flex items-center justify-between gap-3">
                      <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.14em] text-primary">
                        NEW CONCLAVE
                      </Badge>
                      <span className="font-mono text-[9px] tracking-[0.12em] text-muted-foreground">01 / AGENDA</span>
                    </div>
                    <div>
                      <CardTitle className="font-heading text-xl tracking-wide">Convene the Pantheon</CardTitle>
                      <CardDescription className="mt-2">
                        Set the agenda and context, then start the live council run.
                      </CardDescription>
                    </div>
                  </CardHeader>
                  <CardContent className="p-5 sm:p-6">
                    <form onSubmit={create} className="grid gap-5">
                      <div className="grid gap-2">
                        <Label htmlFor="meeting-title">Council title</Label>
                        <Input
                          id="meeting-title"
                          required
                          minLength={3}
                          value={title}
                          onChange={(event) => setTitle(event.target.value)}
                          placeholder="e.g. Product scope and launch readiness"
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="meeting-agenda">Agenda / oracle question</Label>
                        <Textarea
                          id="meeting-agenda"
                          required
                          minLength={10}
                          rows={5}
                          value={agenda}
                          onChange={(event) => setAgenda(event.target.value)}
                          placeholder="What does the Pantheon need to evaluate or decree?"
                        />
                      </div>
                      <div className="grid gap-2">
                        <div className="flex items-center gap-2">
                          <Label htmlFor="meeting-context">Founder context</Label>
                          <span className="font-mono text-[9px] tracking-[0.1em] text-muted-foreground">OPTIONAL</span>
                        </div>
                        <Textarea
                          id="meeting-context"
                          rows={3}
                          value={context}
                          onChange={(event) => setContext(event.target.value)}
                          placeholder="Constraints, known omens, previous decrees, tribute..."
                        />
                      </div>
                      <fieldset className="grid gap-2">
                        <legend className="text-sm font-medium">Evidence for this council</legend>
                        <p className="text-xs leading-5 text-muted-foreground">
                          Selected records are frozen into this run’s evidence snapshot. Search excerpts are treated as leads, not proof.
                        </p>
                        {evidenceRecords.length ? (
                          <div className="grid max-h-48 gap-2 overflow-y-auto rounded-lg border border-border/70 bg-background/40 p-3">
                            {evidenceRecords.map((record) => {
                              const checked = selectedEvidenceIds.includes(record.id);
                              return (
                                <label key={record.id} className="flex items-start gap-2 text-xs">
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    disabled={!checked && selectedEvidenceIds.length >= 12}
                                    onChange={() => setSelectedEvidenceIds((current) => (
                                      checked
                                        ? current.filter((id) => id !== record.id)
                                        : [...current, record.id]
                                    ))}
                                    className="mt-0.5 accent-primary"
                                  />
                                  <span className="min-w-0">
                                    <span className="mr-1 font-mono text-primary">EVIDENCE-{record.id}</span>
                                    <span className="font-medium">{record.claim}</span>
                                    <span className="ml-1 capitalize text-muted-foreground">
                                      · {record.category} · {record.classification}
                                    </span>
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="rounded-lg border border-dashed border-border/70 p-3">
                            <p className="text-xs text-muted-foreground">No records saved yet.</p>
                            <Button
                              type="button"
                              variant="link"
                              className="h-auto px-0 py-1 text-xs"
                              onClick={() => setDashboardView("evidence")}
                            >
                              Open Evidence Register
                            </Button>
                          </div>
                        )}
                        <p className="text-[10px] text-muted-foreground">
                          {selectedEvidenceIds.length}/12 attached · changing the register later does not change this run’s snapshot
                        </p>
                      </fieldset>
                      <fieldset className="grid gap-2">
                        <legend className="text-sm font-medium">Institutional memory</legend>
                        <label className="flex items-start gap-2 text-xs">
                          <input
                            type="checkbox"
                            checked={includeMemory}
                            onChange={(event) => setIncludeMemory(event.target.checked)}
                            className="mt-0.5 accent-primary"
                          />
                          <span>
                            Let this council recall relevant prior decisions, rejected alternatives,
                            failed assumptions and financial constraints (bounded to 3 records, controlled retrieval).
                          </span>
                        </label>
                        {includeMemory && (
                          memoryPreview?.records?.length ? (
                            <div className="grid gap-2 rounded-lg border border-primary/25 bg-primary/5 p-3">
                              <p className="font-mono text-[9px] tracking-[0.12em] text-primary">
                                MEMORY THAT WILL BE INJECTED · {memoryPreview.total_matches} MATCHING RECORD{memoryPreview.total_matches === 1 ? "" : "S"} · BOUNDED TO {memoryPreview.records.length}
                              </p>
                              {memoryPreview.records.map((item) => (
                                <div key={item.id} className="rounded-md border border-border/60 bg-background/70 p-2">
                                  <p className="text-xs font-medium leading-5">
                                    <span className="mr-1 font-mono text-primary">DECISION-{item.id}</span>
                                    {item.decision}
                                  </p>
                                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                                    Decree {item.founder_decision || "recorded"} · {(item.lifecycle || "open").replaceAll("_", " ")}
                                    {item.actual_outcome ? ` · outcome: ${item.actual_outcome}` : " · not yet reviewed"}
                                  </p>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="rounded-lg border border-dashed border-border/70 p-3 text-xs text-muted-foreground">
                              No relevant prior decisions found for this agenda yet.
                            </p>
                          )
                        )}
                      </fieldset>
                      <Button type="submit" disabled={busy} className="h-11 gap-2">
                        {busy ? <LoaderCircle className="size-4 animate-spin" /> : <ChevronRight className="size-4" />}
                        Start council run
                      </Button>
                    </form>
                  </CardContent>
                </Card>

                <Card className="border-border/70 bg-card/85 shadow-lg shadow-black/10">
                  <CardHeader className="gap-3 border-b border-border/60 px-5 pb-5 sm:px-6">
                    <div className="flex items-center justify-between gap-3">
                      <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.14em] text-primary">
                        LIVE CHAMBER
                      </Badge>
                      {runningMeeting && <StatusBadge status={runningMeeting.status} />}
                    </div>
                    <div>
                      <CardTitle className="font-heading text-xl tracking-wide">
                        {runningMeeting ? runningMeeting.title : "No active deliberation"}
                      </CardTitle>
                      <CardDescription className="mt-2">
                        {runningMeeting
                          ? "Follow the current run here. Past meetings and decisions live in Conclaves."
                          : "Convene a council to start a live run. History and completed meetings are in Conclaves."}
                      </CardDescription>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 p-4 sm:p-5">
                    {runningMeeting ? (
                      selected?.id === runningMeeting.id ? (
                        <RunProgress
                          events={runEvents}
                          checkpoints={runCheckpoints}
                          status={runningMeeting.status}
                          error={progressError}
                          progress={progressSummary}
                        />
                      ) : (
                        <Button
                          variant="outline"
                          className="gap-2 border-primary/30 text-primary"
                          onClick={() => {
                            setSelected(runningMeeting);
                            setMeetingDialogOpen(false);
                            setResponseDialog(null);
                          }}
                        >
                          <Activity className="size-4 animate-pulse" />
                          Open live progress
                        </Button>
                      )
                    ) : (
                      <div className="grid min-h-40 place-items-center rounded-lg border border-dashed border-border/70 p-6 text-center">
                        <p className="max-w-sm text-sm leading-6 text-muted-foreground">
                          No council is running right now. Start a new conclave here or review previous runs in the archive.
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
                </section>
              )}

              {dashboardView === "conclaves" && (
                <section className="space-y-6">
                  <div className="space-y-2">
                    <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.16em] text-primary">
                      SESSION ARCHIVE
                    </Badge>
                    <h2 className="font-heading text-2xl tracking-wide sm:text-3xl">{pageTitle[0]}</h2>
                    <p className="text-sm text-muted-foreground">{pageTitle[1]}</p>
                  </div>
                  <Card className="border-border/70 bg-card/80">
                    <CardHeader className="border-b border-border/60">
                      <CardTitle className="font-heading text-xl">Recent conclaves</CardTitle>
                      <CardDescription>
                        {meetings.length} saved meetings · select one to review its report and decisions
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="p-3 sm:p-4">
                      {loading ? (
                        <div className="grid gap-3 p-2" aria-label="Loading council history">
                          {[0, 1, 2].map((item) => (
                            <div key={item} className="h-[68px] animate-pulse rounded-lg bg-muted/70" />
                          ))}
                        </div>
                      ) : meetings.length ? (
                        <ScrollArea className="max-h-[70vh] pr-3">
                          <div className="grid gap-1">{meetingRows}</div>
                        </ScrollArea>
                      ) : (
                        <div className="grid min-h-48 place-items-center rounded-lg border border-dashed border-border/80 p-6 text-center">
                          <div className="space-y-3">
                            <span className="mx-auto grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
                              <ScrollText className="size-4" />
                            </span>
                            <p className="text-sm font-medium">No conclaves yet</p>
                            <p className="text-xs text-muted-foreground">
                              Start a council run in the Chamber to create the first archive record.
                            </p>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </section>
              )}

              {dashboardView === "conclaves" && selected && (
                <Dialog
                  open={meetingDialogOpen}
                  onOpenChange={(open) => {
                    setMeetingDialogOpen(open);
                    if (!open) setResponseDialog(null);
                  }}
                >
                  <DialogContent className="h-[92vh] w-[96vw] max-h-[92vh] max-w-[96vw] overflow-hidden border-border/80 bg-background p-0 sm:max-w-[96vw]">
                    <DialogHeader className="sr-only">
                      <DialogTitle>Conclave report: {selected.title}</DialogTitle>
                      <DialogDescription>
                        Meeting agenda, board responses, synthesis, and founder decision.
                      </DialogDescription>
                    </DialogHeader>
                    <ScrollArea className="h-[86vh]">
                <Card className="overflow-hidden border-border/70 bg-card/85">
                  <CardHeader className="gap-4 border-b border-border/60 bg-muted/10 p-5 pr-12 sm:p-6 sm:pr-12">
                    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                      <div className="min-w-0 space-y-3">
                        <Badge variant="outline" className="max-w-full truncate border-primary/25 font-mono text-[9px] tracking-[0.12em] text-primary">
                          COUNCIL RECORD #{selected.id}
                        </Badge>
                        <div>
                          <CardTitle className="font-heading text-xl tracking-wide">{selected.title}</CardTitle>
                          <CardDescription className="mt-2 max-w-3xl whitespace-pre-wrap leading-6">
                            {selected.agenda}
                          </CardDescription>
                        </div>
                        <StatusBadge status={status} />
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        {selected.status === "completed" ? (
                          <Button
                            variant="outline"
                            onClick={downloadReport}
                            disabled={pdfBusy}
                            className="gap-2"
                          >
                            {pdfBusy
                              ? <LoaderCircle className="size-4 animate-spin" />
                              : <Download className="size-4" />}
                            {pdfBusy ? "Preparing PDF" : "Download report PDF"}
                          </Button>
                        ) : (
                          <Button
                            onClick={run}
                            disabled={busy || selected.status === "running"}
                            className="gap-2"
                          >
                            {busy || selected.status === "running"
                              ? <LoaderCircle className="size-4 animate-spin" />
                              : <Sparkles className="size-4" />}
                            {selected.status === "running"
                              ? "Running in background"
                              : selected.status === "failed"
                                ? "Retry consecration"
                                : "Convene the Pantheon"}
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-7 p-5 sm:p-6">
                    {(!runningMeeting || selected.id === runningMeeting.id) ? (
                      <RunProgress
                        events={runEvents}
                        checkpoints={runCheckpoints}
                        status={selected.status}
                        error={progressError}
                        progress={progressSummary}
                      />
                    ) : (
                      <Alert>
                        <Activity className="size-4" />
                        <AlertTitle>Another conclave is running</AlertTitle>
                        <AlertDescription>
                          Its live progress remains available in the Council Chamber.
                        </AlertDescription>
                      </Alert>
                    )}
                    {selected.status === "completed" ? (
                      <>
                        <section className="space-y-3">
                          <div className="flex items-center gap-3">
                            <Badge variant="outline" className="font-mono text-[9px] tracking-[0.12em]">01</Badge>
                            <h3 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground">
                              INDEPENDENT ORACLE ASSESSMENTS
                            </h3>
                          </div>
                          <div className="grid gap-3 md:grid-cols-2">
                            {Object.keys(roles).map((role) => {
                              const item = contribution(role, "assessment");
                              return (
                                <Card key={role} className="border-border/70 bg-background/60 shadow-none">
                                  <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 space-y-0 p-4">
                                    <CardTitle className="font-heading text-base">{role}</CardTitle>
                                    <div className="flex items-center gap-2">
                                      <span className="max-w-[120px] truncate font-mono text-[9px] text-muted-foreground">
                                        {item?.model_provider || "—"} / {item?.model_name || "—"}
                                      </span>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="gap-1.5 text-primary"
                                        onClick={() => setResponseDialog({
                                          title: `${role} assessment`,
                                          phase: "Independent assessment",
                                          content: formatExecutiveAssessment(item?.assessment || "No oracle spoke."),
                                        })}
                                      >
                                        <Expand className="size-3.5" />
                                        Read
                                      </Button>
                                    </div>
                                  </CardHeader>
                                  <CardContent className="px-4 pb-4">
                                    <ScrollArea className="max-h-64">
                                      <MarkdownResponse className="text-sm leading-6 text-muted-foreground">
                                        {formatExecutiveAssessment(item?.assessment || "No oracle spoke.")}
                                      </MarkdownResponse>
                                    </ScrollArea>
                                  </CardContent>
                                </Card>
                              );
                            })}
                          </div>
                        </section>

                        <section className="space-y-3">
                          <div className="flex items-center gap-3">
                            <Badge variant="outline" className="font-mono text-[9px] tracking-[0.12em]">02</Badge>
                            <h3 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground">
                              CHALLENGE ROUND
                            </h3>
                          </div>
                          <div className="grid gap-3 md:grid-cols-2">
                            {Object.keys(roles).map((role) => {
                              const item = contribution(role, "challenge");
                              const challengeAndRevision = [
                                formatTargetedCrossExamination(
                                  item?.critique || "No challenge returned.",
                                  selected?.contributions,
                                ),
                                item?.revision
                                  ? `---\n\n## Position reconsideration\n\n${formatPositionRevision(item.revision)}`
                                  : "",
                              ].filter(Boolean).join("\n\n");
                              return (
                              <Card key={role} className="border-border/70 bg-background/60 shadow-none">
                                <CardHeader className="flex-row items-center justify-between gap-3 p-4">
                                  <CardTitle className="font-heading text-base">{role} · Challenge</CardTitle>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="shrink-0 gap-1.5 text-primary"
                                    onClick={() => setResponseDialog({
                                      title: `${role} challenge & position revision`,
                                      phase: "Challenge and reconsideration",
                                      content: challengeAndRevision,
                                    })}
                                  >
                                    <Expand className="size-3.5" />
                                    Read
                                  </Button>
                                </CardHeader>
                                <CardContent className="px-4 pb-4">
                                  <ScrollArea className="max-h-64">
                                    <MarkdownResponse className="text-sm leading-6 text-muted-foreground">
                                    {formatTargetedCrossExamination(
                                      item?.critique || "No challenge returned.",
                                      selected?.contributions,
                                    )}
                                    </MarkdownResponse>
                                    {item?.revision && (
                                      <div className="mt-4 border-t border-border/70 pt-4">
                                        <p className="mb-2 font-mono text-[9px] tracking-[0.14em] text-primary">
                                          POSITION RECONSIDERATION
                                        </p>
                                        <MarkdownResponse className="text-sm leading-6 text-muted-foreground">
                                          {formatPositionRevision(item.revision)}
                                        </MarkdownResponse>
                                      </div>
                                    )}
                                  </ScrollArea>
                                </CardContent>
                              </Card>
                              );
                            })}
                          </div>
                        </section>

                        <section className="space-y-3">
                          <div className="flex items-center gap-3">
                            <Badge variant="outline" className="font-mono text-[9px] tracking-[0.12em]">03</Badge>
                            <h3 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground">
                              PANTHEON SYNTHESIS
                            </h3>
                          </div>
                          <Card className="border-primary/20 bg-primary/[0.035] shadow-none">
                            <CardContent className="p-5">
                              <MarkdownResponse className="text-sm leading-7 text-foreground">
                                {selected.resolution?.recommendation || "No synthesis was returned."}
                              </MarkdownResponse>
                            </CardContent>
                          </Card>
                        </section>

                        <section className="space-y-4 rounded-xl border border-border/70 bg-muted/15 p-4 sm:p-5">
                          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                            <div className="space-y-2">
                              <p className="font-mono text-[10px] tracking-[0.16em] text-primary">FOUNDER DECREE</p>
                              <StatusBadge status={status} />
                              <p className="max-w-2xl whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                                {selected.resolution?.founder_notes || "No founder decree recorded."}
                              </p>
                            </div>
                          </div>
                          {selected.resolution?.decision_status === "pending" && (
                            <div className="grid gap-4 border-t border-border/60 pt-4">
                              <div className="grid gap-2">
                                <Label htmlFor="founder-comments">Founder notes <span className="font-normal text-muted-foreground">(optional)</span></Label>
                                <Textarea
                                  id="founder-comments"
                                  rows={3}
                                  value={decisionComments}
                                  onChange={(event) => setDecisionComments(event.target.value)}
                                  placeholder="Add context to your decree..."
                                />
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <Button disabled={busy} onClick={() => decide("approve")} className="gap-2">
                                  <Check className="size-4" /> Issue Decree
                                </Button>
                                <Button disabled={busy} variant="outline" onClick={() => decide("revise")}>
                                  Request Revision
                                </Button>
                                <Button disabled={busy} variant="outline" onClick={() => decide("defer")}>
                                  Defer
                                </Button>
                                <Button disabled={busy} variant="destructive" onClick={() => decide("reject")}>
                                  Reject
                                </Button>
                              </div>
                            </div>
                          )}
                        </section>
                      </>
                    ) : (
                      <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-background/50 p-4">
                        <LoaderCircle className={`mt-0.5 size-4 shrink-0 text-primary ${selected.status === "running" ? "animate-spin" : ""}`} />
                        <div className="space-y-1">
                          <p className="text-sm font-medium">
                            {selected.status === "running"
                              ? "The council is deliberating"
                              : selected.status === "failed"
                                ? "The last run did not complete"
                                : "Ready for deliberation"}
                          </p>
                          <p className="text-sm leading-6 text-muted-foreground">
                            {selected.status === "running"
                              ? "Agent activity is being recorded below; you can navigate away and return while it runs."
                              : selected.status === "failed"
                                ? "Review the run activity above, then retry when the model service is ready."
                                : "Start the session to collect independent assessments and a Pantheon synthesis."}
                          </p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
                    </ScrollArea>
                    <Dialog
                      open={Boolean(responseDialog)}
                      onOpenChange={(open) => !open && setResponseDialog(null)}
                    >
                      {responseDialog && (
                        <DialogContent className="h-[85vh] w-[92vw] max-h-[85vh] max-w-[92vw] overflow-hidden border-border/80 bg-card sm:max-w-[92vw]">
                          <DialogHeader className="pr-8">
                            <Badge
                              variant="outline"
                              className="w-fit border-primary/25 font-mono text-[9px] tracking-[0.14em] text-primary"
                            >
                              {responseDialog.phase}
                            </Badge>
                            <DialogTitle className="font-heading text-xl tracking-wide">
                              {responseDialog.title}
                            </DialogTitle>
                            <DialogDescription>
                              Full response from the selected council member.
                            </DialogDescription>
                          </DialogHeader>
                          <ScrollArea className="max-h-[calc(85vh-150px)] pr-4">
                            <MarkdownResponse className="text-sm leading-7 text-foreground">
                              {responseDialog.content}
                            </MarkdownResponse>
                          </ScrollArea>
                        </DialogContent>
                      )}
                    </Dialog>
                  </DialogContent>
                </Dialog>
              )}
            </>
          )}

          {dashboardView === "executives" && (
            <section className="space-y-6">
              <div className="space-y-2">
                <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.16em] text-primary">
                  THE COUNCIL
                </Badge>
                <h2 className="font-heading text-2xl tracking-wide sm:text-3xl">{pageTitle[0]}</h2>
                <p className="text-sm text-muted-foreground">{pageTitle[1]}</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {Object.entries(roles).map(([role, details]) => {
                  const Icon = roleIcons[role];
                  return (
                    <Card key={role} className="border-border/70 bg-card/80 transition-colors hover:border-primary/30">
                      <CardHeader className="flex-row items-start gap-4 space-y-0 p-5">
                        <span className="grid size-11 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                          <Icon className="size-5" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-3">
                            <CardTitle className="font-heading text-lg tracking-wide">{role}</CardTitle>
                            <StatusBadge status="ready" />
                          </div>
                          <CardDescription className="mt-1">{details[0]}</CardDescription>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-4 px-5 pb-5">
                        <Separator />
                        <p className="text-sm leading-6 text-muted-foreground">{details[1]}</p>
                        <Button variant="outline" size="sm" onClick={() => openProfile(role)} className="gap-2">
                          View mandate <ArrowUpRight className="size-3.5" />
                        </Button>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </section>
          )}

          {dashboardView === "models" && (
            <Suspense fallback={<div className="text-sm text-muted-foreground">Loading model sources…</div>}>
              <ModelSources />
            </Suspense>
          )}
          {dashboardView === "how_to_use" && (
            <Suspense fallback={<div className="text-sm text-muted-foreground">Loading guide…</div>}>
              <HowToUse />
            </Suspense>
          )}
          {dashboardView === "command_centre" && (
            <CommandCentre onNavigate={setDashboardView} />
          )}
          {dashboardView === "vault" && (
            <Suspense fallback={<div className="text-sm text-muted-foreground">Loading knowledge vault…</div>}>
              <KnowledgeVault />
            </Suspense>
          )}
          {dashboardView === "performance" && (
            <Suspense fallback={<div className="text-sm text-muted-foreground">Loading performance…</div>}>
              <Performance />
            </Suspense>
          )}
          {dashboardView === "configuration" && (
            <Suspense fallback={<div className="text-sm text-muted-foreground">Loading configuration…</div>}>
              <Configuration />
            </Suspense>
          )}
          {dashboardView === "operations" && (
            <Suspense fallback={<div className="text-sm text-muted-foreground">Loading operations…</div>}>
              <Operations />
            </Suspense>
          )}
          {dashboardView === "evidence" && (
            <Suspense fallback={<div className="text-sm text-muted-foreground">Loading evidence register…</div>}>
              <EvidenceRegister meetings={meetings} />
            </Suspense>
          )}
          {dashboardView === "decisions" && (
            <Suspense fallback={<div className="text-sm text-muted-foreground">Loading decision register…</div>}>
              <DecisionRegister />
            </Suspense>
          )}

        </main>
      </SidebarInset>

      <Dialog open={Boolean(profile)} onOpenChange={(open) => !open && setProfile(null)}>
        {profile && (
          <DialogContent className="max-h-[85vh] max-w-2xl overflow-hidden border-border/80 bg-card p-0">
            <DialogHeader className="border-b border-border/70 bg-muted/10 p-6 pr-12">
              <div className="flex items-center gap-4">
                <div className="grid size-12 shrink-0 place-items-center rounded-xl border border-primary/25 bg-primary/10 font-heading text-lg text-primary">
                  {profile[0][0]}
                </div>
                <div className="min-w-0">
                  <Badge variant="outline" className="mb-2 border-primary/25 font-mono text-[9px] tracking-[0.14em] text-primary">
                    EXECUTIVE ORACLE
                  </Badge>
                  <DialogTitle className="font-heading text-xl tracking-wide">{profile[0]}</DialogTitle>
                  <DialogDescription className="mt-1">{profile[1]}</DialogDescription>
                </div>
              </div>
            </DialogHeader>
            <ScrollArea className="max-h-[calc(85vh-120px)]">
              <div className="grid gap-5 p-6">
                <Card className="border-border/70 bg-background/60 shadow-none">
                  <CardHeader className="p-4 pb-2">
                    <CardTitle className="font-mono text-[10px] tracking-[0.14em] text-primary">MANDATE</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <p className="text-sm leading-7 text-foreground">{profile[2]}</p>
                  </CardContent>
                </Card>
                <Card className="border-border/70 bg-background/60 shadow-none">
                  <CardHeader className="p-4 pb-2">
                    <CardTitle className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground">
                      SYSTEM INSTRUCTION
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <p className="text-sm leading-7 text-muted-foreground">
                      You are the {profile[0]} of an early-stage neurotechnology company.{" "}
                      {profile[2].toLowerCase()}
                    </p>
                  </CardContent>
                </Card>
              </div>
            </ScrollArea>
          </DialogContent>
        )}
      </Dialog>
    </SidebarProvider>
  );
}
