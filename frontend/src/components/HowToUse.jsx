import { useState } from "react";
import { BookOpen, ChevronDown, Cpu, Landmark, ScrollText, Shield, Target, Vault } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const flow = [
  { title: "Sign in", detail: "Create an account or sign in with SSO." },
  { title: "Onboard company", detail: "Name, stage, mission and strategic context." },
  { title: "Configure LLMs", detail: "Add sources, test, assign to roles." },
  { title: "Shape context", detail: "Priorities, constraints, assumptions, knowledge." },
  { title: "Convene council", detail: "Enter agenda, run deliberation." },
  { title: "Record decree", detail: "Finalize founder decision." },
  { title: "Track & review", detail: "Decisions, evidence, operations, performance." },
];

const sections = [
  {
    id: "onboard",
    icon: Shield,
    title: "Onboarding",
    body: "On first login you are guided to create your company: name, stage, mission and strategic context. Your data is isolated to your account.",
  },
  {
    id: "llm",
    icon: Cpu,
    title: "LLM Setup (BYOK)",
    body: "Open Model Sources → Add source → choose provider (LM Studio, Ollama, OpenAI, Anthropic, Gemini, etc.) → paste API key → Test → assign a source + model to each role (CEO, CFO, CTO, CSO, Board). Keys are encrypted and never returned.",
  },
  {
    id: "context",
    icon: Target,
    title: "Company Context",
    body: "In Configuration, maintain strategic priorities, constraints, financial assumptions and approved knowledge. These anchor every council run.",
  },
  {
    id: "council",
    icon: Landmark,
    title: "Council Chamber",
    body: "Enter an agenda and run. Four executives assess independently, positions are extracted and cross-examined, revised, then the Pantheon Chair synthesizes a recommendation.",
  },
  {
    id: "decree",
    icon: ScrollText,
    title: "Decision Register",
    body: "Record the founder decree (approve/reject/defer/revise), set review dates and track outcomes. Sync resolutions from conclaves.",
  },
  {
    id: "vault",
    icon: Vault,
    title: "Knowledge & Evidence",
    body: "Knowledge Vault stores approved knowledge; Evidence Register tracks source-backed claims with provenance and dispute state.",
  },
];

export default function HowToUse() {
  const [open, setOpen] = useState("onboard");

  return (
    <section className="space-y-6">
      <div>
        <h2 className="font-heading text-2xl tracking-wide text-primary sm:text-3xl">How to Use Pantheon</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Interactive end-to-end guide. Follow the flow or expand a topic.
        </p>
      </div>

      {/* Visual flow */}
      <Card className="border-border/60 bg-card/60">
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-foreground">End-to-end flow</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-2">
            {flow.map((s, i) => (
              <div key={s.title} className="flex items-center gap-3">
                <div className="grid size-8 shrink-0 place-items-center rounded-full border border-primary/30 bg-primary/10 font-mono text-[10px] text-primary">
                  {i + 1}
                </div>
                <div className="flex-1 rounded-lg border border-border/40 bg-background/40 px-3 py-2">
                  <p className="text-xs font-semibold text-foreground">{s.title}</p>
                  <p className="text-[11px] text-muted-foreground">{s.detail}</p>
                </div>
                {i < flow.length - 1 && (
                  <div className="hidden sm:block text-primary/40">↓</div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Interactive accordion */}
      <div className="space-y-2">
        {sections.map(({ id, icon: Icon, title, body }) => (
          <Card key={id} className="border-border/60 bg-card/60">
            <button
              type="button"
              className="flex w-full items-center gap-3 p-4 text-left"
              onClick={() => setOpen(open === id ? "" : id)}
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                <Icon className="size-4" />
              </span>
              <span className="flex-1 text-sm font-semibold text-foreground">{title}</span>
              <ChevronDown className={`size-4 text-muted-foreground transition ${open === id ? "rotate-180" : ""}`} />
            </button>
            {open === id && (
              <CardContent className="pt-0 text-xs leading-6 text-muted-foreground">{body}</CardContent>
            )}
          </Card>
        ))}
      </div>

      <Badge variant="outline" className="border-primary/25 font-mono text-[9px] tracking-[0.16em] text-primary">
        TIP: Start in Model Sources before running your first conclave.
      </Badge>
    </section>
  );
}
