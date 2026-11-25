import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  AlertTriangle,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  Compass,
  Gavel,
  LoaderCircle,
  ScrollText,
  Settings2,
  ShieldAlert,
  Target,
  Vault,
} from "lucide-react";
import { getCompanyContext } from "../api";
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

const priorityBadge = {
  active: "border-primary/40 text-primary",
  paused: "border-amber-400/40 text-amber-300",
  achieved: "border-emerald-400/40 text-emerald-300",
};

const severityBadge = {
  high: "border-destructive/40 bg-destructive/10 text-destructive",
  medium: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  low: "border-border bg-muted/40 text-muted-foreground",
};

const riskIcon = (kind) => {
  if (kind === "constraint") return ShieldAlert;
  if (kind === "decision_condition_breached") return CircleAlert;
  if (kind === "decision_review_due") return CalendarClock;
  return AlertTriangle;
};

const riskLabel = (kind) => ({
  decision_condition_breached: "Condition breached",
  decision_review_due: "Review due",
  decision_target_overdue: "Target overdue",
  constraint: "Constraint",
}[kind] || "Risk");

const lifecycleBadge = {
  open: "border-primary/40 text-primary",
  under_review: "border-amber-400/40 text-amber-300",
  closed: "border-emerald-400/40 text-emerald-300",
  superseded: "border-muted-foreground/40 text-muted-foreground",
};

function Stat({ label, value, icon: Icon, tone = "text-foreground" }) {
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

export default function CommandCentre({ onNavigate }) {
  const { getToken } = useAuth();
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const token = await getToken();
        if (!token) throw new Error("Your session has expired. Sign in again.");
        const next = await getCompanyContext(token);
        if (!cancelled) setContext(next);
      } catch (requestError) {
        if (!cancelled) setError(requestError.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  const company = context?.company;
  const counts = context?.counts || {};
  const risks = context?.risks || [];
  const priorities = useMemo(
    () => (company?.strategic_priorities || []).filter((item) => item.status !== "achieved"),
    [company],
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading company status…
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Command Centre unavailable</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <section className="space-y-6">
      <Card className="overflow-hidden border-border/70 bg-gradient-to-br from-card to-background">
        <CardContent className="flex flex-col gap-5 p-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.16em] text-primary">
                COMPANY CONTEXT
              </Badge>
              {company?.stage && <Badge variant="secondary" className="capitalize">{company.stage}</Badge>}
              {company?.owner && <Badge variant="outline">Owner: {company.owner}</Badge>}
            </div>
            <h2 className="font-heading text-2xl tracking-wide sm:text-3xl">{company?.name || "Unnamed company"}</h2>
            <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
              {company?.mission || "Add a mission in Configuration so every council run starts from the same baseline."}
            </p>
            {company?.strategic_context && (
              <p className="max-w-3xl text-sm leading-6 text-muted-foreground/80">{company.strategic_context}</p>
            )}
          </div>
          <Button variant="outline" className="gap-2 self-start" onClick={() => onNavigate?.("configuration")}>
            <Settings2 className="size-4" /> Configure company
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Active priorities" value={priorities.length} icon={Target} tone="text-primary" />
        <Stat label="Open decisions" value={counts.decisions_open ?? 0} icon={Gavel} />
        <Stat
          label="Reviews due"
          value={counts.decisions_due ?? 0}
          icon={CalendarClock}
          tone={counts.decisions_due ? "text-amber-300" : "text-foreground"}
        />
        <Stat label="Conclaves completed" value={`${counts.meetings_completed ?? 0}/${counts.meetings_total ?? 0}`} icon={ScrollText} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card className="border-border/70 bg-card/80">
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="font-heading text-xl">Strategic priorities</CardTitle>
                <CardDescription>What the company is currently trying to achieve.</CardDescription>
              </div>
              <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => onNavigate?.("configuration")}>
                Manage <ArrowUpRight className="size-3.5" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {priorities.length ? (
                priorities.map((priority) => (
                  <div key={priority.id} className="rounded-lg border border-border/60 bg-background/40 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm font-medium leading-6 text-foreground">{priority.title}</p>
                      <Badge variant="outline" className={`shrink-0 capitalize ${priorityBadge[priority.status] || ""}`}>
                        {priority.status}
                      </Badge>
                    </div>
                    {priority.description && (
                      <p className="mt-1 text-sm leading-5 text-muted-foreground">{priority.description}</p>
                    )}
                    {priority.target_date && (
                      <p className="mt-2 font-mono text-[10px] tracking-[0.08em] text-muted-foreground">
                        TARGET {priority.target_date}
                      </p>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No active priorities yet. Add them in Configuration.</p>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80">
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="font-heading text-xl">Decisions</CardTitle>
                <CardDescription>Recent decrees and their lifecycle.</CardDescription>
              </div>
              <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => onNavigate?.("decisions")}>
                Register <ArrowUpRight className="size-3.5" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {(context?.recent_decisions || []).length ? (
                context.recent_decisions.map((decision) => (
                  <div key={decision.id} className="rounded-lg border border-border/60 bg-background/40 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm font-medium leading-6 text-foreground">{decision.decision}</p>
                      <Badge variant="outline" className={`shrink-0 capitalize ${lifecycleBadge[decision.lifecycle] || ""}`}>
                        {(decision.lifecycle || "open").replaceAll("_", " ")}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Founder: {decision.founder_decision || "pending"}
                      {decision.owner ? ` · Owner: ${decision.owner}` : ""}
                      {decision.review_date ? ` · Review ${decision.review_date}` : ""}
                      {decision.is_review_due ? " · review due" : ""}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No decisions recorded yet.</p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="border-border/70 bg-card/80">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 font-heading text-xl">
                <ShieldAlert className="size-4 text-amber-300" /> Risks
              </CardTitle>
              <CardDescription>Breached conditions, overdue reviews and critical constraints.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {risks.length ? (
                risks.map((risk, index) => {
                  const Icon = riskIcon(risk.kind);
                  return (
                    <div
                      key={`${risk.kind}-${risk.decision_id ?? risk.constraint_id ?? index}`}
                      className={`rounded-lg border p-3 ${severityBadge[risk.severity] || severityBadge.low}`}
                    >
                      <div className="flex items-start gap-2">
                        <Icon className="mt-0.5 size-4 shrink-0" />
                        <div className="min-w-0">
                          <p className="font-mono text-[9px] uppercase tracking-[0.14em]">{riskLabel(risk.kind)}</p>
                          <p className="mt-1 text-sm font-medium leading-5 text-foreground">{risk.title}</p>
                          {risk.detail && <p className="mt-1 text-xs leading-5 text-muted-foreground">{risk.detail}</p>}
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="size-4 text-emerald-400" /> No active risks detected.
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80">
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="flex items-center gap-2 font-heading text-xl">
                  <Vault className="size-4 text-primary" /> Knowledge
                </CardTitle>
                <CardDescription>{counts.knowledge_approved ?? 0} approved · {counts.evidence_total ?? 0} claims.</CardDescription>
              </div>
              <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => onNavigate?.("vault")}>
                Vault <ArrowUpRight className="size-3.5" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-2">
              {(company?.approved_knowledge || []).slice(0, 4).map((item) => (
                <div key={item.id} className="rounded-md border border-border/60 bg-background/40 p-2.5">
                  <p className="text-sm font-medium leading-5 text-foreground">{item.title}</p>
                  <p className="mt-0.5 text-[11px] capitalize text-muted-foreground">{item.category}</p>
                </div>
              ))}
              {!(company?.approved_knowledge || []).length && (
                <p className="text-sm text-muted-foreground">Approve evidence into the vault to anchor future councils.</p>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 font-heading text-xl">
                <Compass className="size-4 text-primary" /> Recent conclaves
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {(context?.recent_meetings || []).slice(0, 4).map((meeting) => (
                <button
                  key={meeting.id}
                  type="button"
                  onClick={() => onNavigate?.("chamber")}
                  className="flex w-full items-center justify-between gap-2 rounded-md border border-border/60 bg-background/40 p-2.5 text-left transition-colors hover:border-primary/35"
                >
                  <span className="min-w-0 truncate text-sm text-foreground">{meeting.title}</span>
                  <Badge variant="outline" className="shrink-0 capitalize">{meeting.status}</Badge>
                </button>
              ))}
              {!(context?.recent_meetings || []).length && (
                <p className="text-sm text-muted-foreground">No conclaves yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
