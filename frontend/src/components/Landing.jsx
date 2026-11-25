import { ArrowRight, Crown, ScrollText, Swords, Target } from "lucide-react";
import { SignInButton, SignUpButton } from "@clerk/react";
import Aurora from "./Aurora";
import BlurText from "./BlurText";
import SpotlightCard from "./SpotlightCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const features = [
  { icon: Target, label: "Independent executive assessments" },
  { icon: Swords, label: "Structured challenge round" },
  { icon: Crown, label: "Pantheon Chair synthesis" },
  { icon: ScrollText, label: "Founder-controlled decrees" },
];

export default function Landing() {
  // Complete OAuth and password flows on the origin that served this page, not
  // on whatever home URL the Clerk instance happens to be configured with.
  const homeUrl = `${window.location.origin}/`;

  return (
    <main className="relative isolate flex min-h-svh items-center overflow-hidden bg-background px-6 py-16 sm:px-10">
      <div className="pointer-events-none absolute inset-0 -z-10 opacity-30" aria-hidden="true">
        <Aurora
          colorStops={["#765d20", "#d4af37", "#f3df86"]}
          amplitude={0.55}
          blend={0.75}
          speed={0.22}
          brightness={0.5}
          layers={1}
          mouseInteraction={false}
        />
      </div>
      <div
        className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-background/10 via-background/50 to-background"
        aria-hidden="true"
      />
      <div className="mx-auto grid w-full max-w-6xl items-center gap-14 lg:grid-cols-[1.05fr_0.95fr]">
        <section className="space-y-7">
          <Badge
            variant="outline"
            className="border-primary/30 bg-primary/5 px-3 py-1 font-mono text-[10px] tracking-[0.16em] text-primary"
          >
            DIVINE COUNCIL · DECISION SUPPORT
          </Badge>
          <div
            role="heading"
            aria-level={1}
            className="font-heading text-5xl leading-tight tracking-[0.09em] text-primary sm:text-6xl lg:text-7xl"
          >
            <BlurText
              text="THE PANTHEON"
              animateBy="words"
              direction="top"
              trigger="view"
              delay={110}
              stepDuration={0.5}
              className="gap-x-4"
            />
          </div>
          <p className="max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
            A local-first, hybrid-LLM divine council. Four executive oracles — CEO, CFO,
            CTO, and CSO — deliberate independently on your agenda, challenge one another,
            and the Pantheon Chair synthesizes a recommendation. The Founder alone records
            the final decree.
          </p>
          <div className="flex flex-wrap gap-3">
            <SignInButton mode="redirect" forceRedirectUrl={homeUrl}>
              <Button size="lg" className="h-12 gap-3 px-6 font-semibold">
                Sign in to enter <ArrowRight className="size-4" />
              </Button>
            </SignInButton>
            <SignUpButton mode="redirect" forceRedirectUrl={homeUrl}>
              <Button size="lg" variant="outline" className="h-12 border-border/80 px-6">
                Create an account
              </Button>
            </SignUpButton>
          </div>
        </section>

        <section aria-label="Council features" className="grid gap-4 sm:grid-cols-2">
          {features.map(({ icon: Icon, label }, index) => (
            <SpotlightCard
              key={label}
              intensity={0.14}
              spotlightColor="#d4af37"
              ambient={index === 0}
              className="min-h-36 rounded-xl p-0"
              style={{
                padding: 0,
                background: "rgba(15, 15, 13, 0.78)",
                border: "1px solid rgba(212, 175, 55, 0.14)",
              }}
            >
              <Card className="h-full border-0 bg-transparent shadow-none">
                <CardContent className="flex h-full min-h-36 items-start gap-4 p-5">
                  <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                    <Icon className="size-5" />
                  </span>
                  <div className="space-y-2 pt-0.5">
                    <p className="font-mono text-[10px] tracking-[0.16em] text-primary/70">
                      COUNCIL {String(index + 1).padStart(2, "0")}
                    </p>
                    <p className="text-sm font-medium leading-6 text-foreground">{label}</p>
                  </div>
                </CardContent>
              </Card>
            </SpotlightCard>
          ))}
        </section>
      </div>
    </main>
  );
}
