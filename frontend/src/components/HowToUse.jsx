import { BookOpen, Cpu, Landmark, ScrollText, Shield, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const steps = [
  { icon: Shield, title: "1. Sign in & onboard", body: "Create an account, then complete onboarding to name your company and set its mission/strategy. Each user gets an isolated workspace." },
  { icon: Cpu, title: "2. Configure LLMs (Model Sources)", body: "Open Model Sources in the sidebar. Add a local server (LM Studio/Ollama) or a hosted provider, paste your API key (BYOK, stored encrypted), test connectivity, then assign a source+model to each role (CEO, CFO, CTO, CSO, Board)." },
  { icon: Target, title: "3. Shape company context", body: "In Configuration, add priorities, constraints, financial assumptions and approved knowledge so the council is anchored to your strategy." },
  { icon: Landmark, title: "4. Convene a council", body: "Go to Council Chamber, enter an agenda, and run. Four executives assess, cross-examine, revise, and the Pantheon Chair synthesizes a recommendation." },
  { icon: ScrollText, title: "5. Record the decree", body: "Review the recommendation, then record your founder decision. Track it in the Decision Register with review dates." },
  { icon: BookOpen, title: "6. Explore features", body: "Use Knowledge Vault, Evidence Register, Operations, and Performance to manage knowledge, claims, operational drafts and executive quality." },
];

export default function HowToUse() {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="font-heading text-2xl tracking-wide text-primary sm:text-3xl">How to Use Pantheon</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          End-to-end guide: from first login to recording a decree.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {steps.map(({ icon: Icon, title, body }) => (
          <Card key={title} className="border-border/60 bg-card/60">
            <CardHeader className="flex flex-row items-center gap-3 space-y-0">
              <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                <Icon className="size-4" />
              </span>
              <CardTitle className="text-sm font-semibold text-foreground">{title}</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-xs leading-5 text-muted-foreground">{body}</CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
