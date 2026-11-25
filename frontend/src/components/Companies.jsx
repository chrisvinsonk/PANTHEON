import { useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import { Building2, Plus, Trash2 } from "lucide-react";
import { getCompanies, createCompanyProfile, deleteCompanyProfile, updateCompanyProfile } from "../api";
import { Button } from "@/components/ui/button";
import { clearActiveCompanyId } from "../company";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function Companies() {
  const { getToken } = useAuth();
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState({ name: "", mission: "", stage: "" });
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const token = await getToken();
      setCompanies(await getCompanies(token));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!draft.name.trim()) return;
    setCreating(true);
    setError("");
    try {
      const token = await getToken();
      await createCompanyProfile({ name: draft.name.trim(), mission: draft.mission.trim(), stage: draft.stage.trim() }, token);
      setDraft({ name: "", mission: "", stage: "" });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const remove = async (id) => {
    if (companies.length <= 1) {
      window.alert("Keep at least one company. Create another before deleting this one.");
      return;
    }
    if (!window.confirm("Delete this company?")) return;
    try {
      const token = await getToken();
      await deleteCompanyProfile(id, true, token);
      clearActiveCompanyId();
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const rename = async (company) => {
    const name = window.prompt("New name", company.name);
    if (!name || name === company.name) return;
    try {
      const token = await getToken();
      await updateCompanyProfile(company.id, { name }, token);
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <section className="space-y-6">
      <h2 className="font-heading text-2xl tracking-wide text-primary sm:text-3xl">Manage Companies</h2>
      {error && <p className="text-sm text-red-400">{error}</p>}
      <Card className="border-border/60 bg-card/60">
        <CardHeader><CardTitle className="text-sm">Create company</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div><Label>Name</Label><Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></div>
          <div><Label>Mission</Label><Textarea value={draft.mission} onChange={(e) => setDraft({ ...draft, mission: e.target.value })} /></div>
          <div><Label>Stage</Label><Input value={draft.stage} onChange={(e) => setDraft({ ...draft, stage: e.target.value })} /></div>
          <Button onClick={create} disabled={creating || !draft.name.trim()}>{creating ? "Creating…" : "Create"}</Button>
        </CardContent>
      </Card>
      <div className="grid gap-3">
        {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : companies.map((c) => (
          <Card key={c.id} className="border-border/60 bg-card/60">
            <CardContent className="flex items-center justify-between p-4">
              <div className="flex items-center gap-3">
                <Building2 className="size-4 text-primary" />
                <div>
                  <p className="text-sm font-semibold text-foreground">{c.name}</p>
                  <p className="text-xs text-muted-foreground">{c.stage || "—"} · {c.mission || "No mission"}</p>
                </div>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => rename(c)}>Rename</Button>
                <Button size="sm" variant="destructive" onClick={() => remove(c.id)}><Trash2 className="size-3.5" /></Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
