import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { updateCompany } from "../api";

const STEPS = ["Company", "Strategy", "Review"];

export default function Onboarding({ getToken, onComplete }) {
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
      await updateCompany({ ...form, onboarded: true }, token);
      onComplete?.();
    } catch (e) {
      setError(e.message || "Failed to save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 py-16">
      <Card className="w-full max-w-xl border-border/60 bg-card/80">
        <CardHeader>
          <p className="font-mono text-[10px] tracking-[0.16em] text-primary">ONBOARDING · STEP {step + 1} OF {STEPS.length}</p>
          <CardTitle className="font-heading text-2xl text-primary">{STEPS[step]}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {step === 0 && (
            <>
              <div>
                <Label>Company name</Label>
                <Input value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="Acme Corp" />
              </div>
              <div>
                <Label>Stage</Label>
                <Input value={form.stage} onChange={(e) => update("stage", e.target.value)} placeholder="seed" />
              </div>
              <div>
                <Label>Mission</Label>
                <Textarea value={form.mission} onChange={(e) => update("mission", e.target.value)} placeholder="What are you building?" />
              </div>
            </>
          )}
          {step === 1 && (
            <div>
              <Label>Strategic context</Label>
              <Textarea value={form.strategic_context} onChange={(e) => update("strategic_context", e.target.value)} placeholder="Current priorities, constraints, runway..." rows={6} />
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
            <Button variant="outline" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>Back</Button>
            {step < STEPS.length - 1 ? (
              <Button onClick={() => setStep((s) => s + 1)} disabled={step === 0 && !form.name.trim()}>Next</Button>
            ) : (
              <Button onClick={submit} disabled={busy || !form.name.trim()}>{busy ? "Saving…" : "Finish"}</Button>
            )}
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
