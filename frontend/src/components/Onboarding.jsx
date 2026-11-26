import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { createCompanyProfile, updateCompanyProfile } from "../api";
import { setActiveCompanyId } from "../company";

const STEPS = ["Company", "Strategy", "Review"];

export default function Onboarding({ getToken, blankCompanyId, onComplete }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    name: "",
    mission: "",
    stage: "seed",
    strategic_context: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const update = (field, value) => setForm((f) => ({ ...f, [field]: value }));

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const token = await getToken();
      if (!token) throw new Error("Your session has expired. Sign in again.");
      const payload = {
        name: form.name.trim(),
        mission: form.mission.trim(),
        stage: form.stage.trim(),
        strategic_context: form.strategic_context.trim(),
        onboarded: true,
      };
      // Fill an existing unnamed row in place; otherwise create one. Either
      // way there is exactly one named, onboarded company at the end.
      const company = blankCompanyId
        ? await updateCompanyProfile(blankCompanyId, payload, token)
        : await createCompanyProfile(payload, token);
      if (company?.id) setActiveCompanyId(company.id);
      onComplete?.();
    } catch (e) {
      setError(e.message || "Failed to save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="app-shell flex min-h-svh items-center justify-center px-6 py-16">
      <Card className="w-full max-w-xl border-border/60 bg-card/80">
        <CardHeader>
          <p className="font-mono text-[10px] tracking-[0.16em] text-primary">
            ONBOARDING · STEP {step + 1} OF {STEPS.length}
          </p>
          <CardTitle className="font-heading text-2xl text-primary">
            {STEPS[step]}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {step === 0 && (
            <>
              <div>
                <Label>Company name</Label>
                <Input
                  value={form.name}
                  onChange={(e) => update("name", e.target.value)}
                  placeholder="Acme Corp"
                  maxLength={160}
                />
              </div>
              <div>
                <Label>Stage</Label>
                <Input
                  value={form.stage}
                  onChange={(e) => update("stage", e.target.value)}
                  placeholder="seed"
                  maxLength={40}
                />
              </div>
              <div>
                <Label>Mission</Label>
                <Textarea
                  value={form.mission}
                  onChange={(e) => update("mission", e.target.value)}
                  placeholder="What are you building?"
                  rows={3}
                />
              </div>
            </>
          )}
          {step === 1 && (
            <div>
              <Label>Strategic context</Label>
              <Textarea
                value={form.strategic_context}
                onChange={(e) => update("strategic_context", e.target.value)}
                placeholder="Current priorities, constraints, runway..."
                rows={6}
              />
            </div>
          )}
          {step === 2 && (
            <div className="space-y-2 text-sm">
              <p><strong>Name:</strong> {form.name || "—"}</p>
              <p><strong>Stage:</strong> {form.stage || "—"}</p>
              <p><strong>Mission:</strong> {form.mission || "—"}</p>
              <p><strong>Context:</strong> {form.strategic_context || "—"}</p>
            </div>
          )}
          {error && <p className="text-sm text-red-400">{error}</p>}
          <div className="flex justify-between pt-2">
            <Button
              variant="outline"
              disabled={step === 0}
              onClick={() => setStep((s) => s - 1)}
            >
              Back
            </Button>
            {step < STEPS.length - 1 ? (
              <Button
                onClick={() => setStep((s) => s + 1)}
                disabled={step === 0 && form.name.trim().length < 2}
              >
                Next
              </Button>
            ) : (
              <Button
                onClick={submit}
                disabled={busy || form.name.trim().length < 2}
              >
                {busy ? "Saving…" : "Finish"}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
