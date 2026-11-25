import { ArrowRight, Crown, Github, Landmark, ScrollText, Shield, Sparkles, Target } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import Aurora from "./Aurora";

const GITHUB_URL = "https://github.com/chrisvinsonk/PANTHEON";

const steps = [
  { n: "01", title: "Ask a strategic question", body: "The Founder poses an agenda to the council." },
  { n: "02", title: "Four executives assess", body: "CEO, CFO, CTO and CSO reason independently." },
  { n: "03", title: "Claims are cross-examined", body: "Positions are extracted and challenged." },
  { n: "04", title: "Positions are revised", body: "Executives refine their stance." },
  { n: "05", title: "Pantheon Chair synthesizes", body: "A consolidated recommendation is produced." },
  { n: "06", title: "Founder records the decree", body: "Only the Founder finalizes the decision." },
];

const features = [
  { icon: Target, title: "Independent assessments", body: "Four distinct executive lenses, never a single model's answer." },
  { icon: Landmark, title: "Structured deliberation", body: "Assess, extract, cross-examine, revise, synthesize — deterministic workflow." },
  { icon: Crown, title: "Board-chair synthesis", body: "One consolidated recommendation from competing views." },
  { icon: ScrollText, title: "Founder decrees", body: "Decisions are recorded and tracked with review dates." },
  { icon: Shield, title: "BYOK & encrypted keys", body: "Bring your own keys; stored encrypted, never baked in." },
  { icon: Sparkles, title: "Open source", body: "MIT licensed. Fork, self-host, contribute." },
];

export default function Landing() {
  const homeUrl = `${window.location.origin}/`;

  return (
    <main className="relative isolate min-h-svh overflow-hidden bg-background">
      <div className="pointer-events-none absolute inset-0 -z-10 opacity-25" aria-hidden="true">
        <Aurora colorStops={["#765d20", "#d4af37", "#f3df86"]} amplitude={0.5} blend={0.7} speed={0.2} brightness={0.45} layers={1} mouseInteraction={false} />
      </div>
      <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-background/20 via-background/60 to-background" aria-hidden="true" />

      {/* Nav */}
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6 sm:px-10">
        <div className="flex items-center gap-3">
          <div className="grid size-9 place-items-center rounded-lg border border-primary/30 bg-primary/10 font-heading text-lg text-primary">P</div>
          <span className="font-heading text-sm tracking-[0.14em] text-foreground">THE PANTHEON</span>
        </div>
        <div className="flex items-center gap-3">
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="hidden items-center gap-2 text-sm text-muted-foreground hover:text-foreground sm:flex">
            <Github className="size-4" /> GitHub
          </a>
          <a href="/sign-in">
            <Button size="sm" variant="outline" className="border-border/80">Sign in</Button>
          </a>
          <a href="/sign-up">
            <Button size="sm">Get started</Button>
          </a>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto w-full max-w-6xl px-6 pb-16 pt-10 sm:px-10 sm:pt-16">
        <Badge variant="outline" className="border-primary/30 bg-primary/5 px-3 py-1 font-mono text-[10px] tracking-[0.16em] text-primary">
          OPEN SOURCE · DIVINE COUNCIL · DECISION SUPPORT
        </Badge>
        <h1 className="mt-6 font-heading text-5xl leading-tight tracking-[0.06em] text-primary sm:text-6xl lg:text-7xl">
          Your strategic questions, deliberated by a council of AI executives.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
          Pantheon convenes four executive oracles — CEO, CFO, CTO and CSO — to
          assess, challenge and revise their positions, then the Pantheon Chair
          synthesizes a recommendation. The Founder alone records the final decree.
          Bring your own keys. Your data stays yours.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <a href="/sign-up">
            <Button size="lg" className="h-12 gap-3 px-6 font-semibold">
              Get started <ArrowRight className="size-4" />
            </Button>
          </a>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            <Button size="lg" variant="outline" className="h-12 gap-3 border-border/80 px-6">
              <Github className="size-4" /> View on GitHub
            </Button>
          </a>
        </div>
        <p className="mt-4 text-xs text-muted-foreground">
          Free and open source under the MIT license. Self-host or use the live demo at{" "}
          <a href="https://pantheon.kunnankada.in" className="text-primary hover:underline">pantheon.kunnankada.in</a>.
        </p>
      </section>

      {/* How it works */}
      <section className="mx-auto w-full max-w-6xl px-6 py-16 sm:px-10">
        <h2 className="font-heading text-2xl tracking-wide text-primary sm:text-3xl">How it works</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          A deterministic LangGraph workflow turns a Founder question into a recorded decree.
        </p>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {steps.map((step) => (
            <Card key={step.n} className="border-border/60 bg-card/60">
              <CardContent className="p-5">
                <p className="font-mono text-[10px] tracking-[0.16em] text-primary/70">{step.n}</p>
                <p className="mt-2 text-sm font-semibold text-foreground">{step.title}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{step.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto w-full max-w-6xl px-6 py-16 sm:px-10">
        <h2 className="font-heading text-2xl tracking-wide text-primary sm:text-3xl">Features</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map(({ icon: Icon, title, body }) => (
            <Card key={title} className="border-border/60 bg-card/60">
              <CardContent className="flex gap-4 p-5">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                  <Icon className="size-5" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-foreground">{title}</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{body}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Open source CTA */}
      <section className="mx-auto w-full max-w-6xl px-6 py-16 sm:px-10">
        <Card className="border-primary/25 bg-primary/5">
          <CardContent className="flex flex-col items-start gap-4 p-8 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="font-heading text-xl text-primary">Open source. Built to be forked.</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                MIT licensed. Read the code, self-host, or contribute on GitHub.
              </p>
            </div>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">
              <Button size="lg" className="h-12 gap-3 px-6 font-semibold">
                <Github className="size-4" /> Star on GitHub
              </Button>
            </a>
          </CardContent>
        </Card>
      </section>

      {/* Footer */}
      <footer className="mx-auto w-full max-w-6xl border-t border-border/40 px-6 py-8 sm:px-10">
        <div className="flex flex-col items-center justify-between gap-3 text-xs text-muted-foreground sm:flex-row">
          <p>© THE PANTHEON. Open source under MIT.</p>
          <div className="flex gap-4">
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="hover:text-foreground">GitHub</a>
            <a href="/sign-in" className="hover:text-foreground">Sign in</a>
            <a href="/sign-up" className="hover:text-foreground">Get started</a>
          </div>
        </div>
      </footer>
    </main>
  );
}
