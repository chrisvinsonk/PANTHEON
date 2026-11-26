import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import { Building2, LoaderCircle, Plus, Trash2 } from "lucide-react";
import {
  createCompanyProfile,
  deleteCompanyProfile,
  getCompanies,
  updateCompanyProfile,
} from "../api";
import {
  clearActiveCompanyId,
  getActiveCompanyId,
  isBlankCompany,
  setActiveCompanyId,
  syncActiveCompanyId,
} from "../company";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function Companies() {
  const { getToken } = useAuth();
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState({ name: "", mission: "", stage: "" });
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    const list = await getCompanies(token);
    setCompanies(list);
    syncActiveCompanyId(list.filter((company) => !isBlankCompany(company)));
    return list;
  }, [getToken]);

  useEffect(() => {
    load()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [load]);

  const create = async () => {
    if (draft.name.trim().length < 2) return;
    setCreating(true);
    setError("");
    setNotice("");
    try {
      const token = await getToken();
      const company = await createCompanyProfile(
        {
          name: draft.name.trim(),
          mission: draft.mission.trim(),
          stage: draft.stage.trim(),
          onboarded: true,
        },
        token,
      );
      setActiveCompanyId(company.id);
      setDraft({ name: "", mission: "", stage: "" });
      await load();
      setNotice(`Created “${company.name}”. It is now the active company.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCreating(false);
    }
  };

  const rename = async (company) => {
    const name = window.prompt("Company name", company.name);
    if (!name || name.trim().length < 2 || name.trim() === company.name) return;
    setBusyId(company.id);
    setError("");
    setNotice("");
    try {
      const token = await getToken();
      await updateCompanyProfile(company.id, { name: name.trim(), onboarded: true }, token);
      await load();
      setNotice("Company renamed and activated.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (company) => {
    if (companies.length <= 1) {
      setError("Keep at least one company. Create another before deleting this one.");
      return;
    }
    if (!window.confirm(`Delete “${company.name || "Unnamed company"}”? This cannot be undone.`)) {
      return;
    }
    setBusyId(company.id);
    setError("");
    setNotice("");
    try {
      const token = await getToken();
      const wasActive = getActiveCompanyId() === company.id;
      await deleteCompanyProfile(company.id, true, token);
      if (wasActive) clearActiveCompanyId();
      await load();
      setNotice(`Deleted “${company.name || "Unnamed company"}”.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-6">
      <div>
        <h2 className="font-heading text-2xl tracking-wide text-primary sm:text-3xl">
          Manage Companies
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Create, rename and delete your companies. At least one company must remain —
          create another before deleting the last one.
        </p>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      {notice && <p className="text-sm text-primary">{notice}</p>}

      <Card className="border-border/60 bg-card/60">
        <CardHeader>
          <CardTitle className="text-sm">Create company</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label>Name</Label>
            <Input
              value={draft.name}
              maxLength={160}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="e.g. Northstar Labs"
            />
          </div>
          <div>
            <Label>Mission</Label>
            <Textarea
              value={draft.mission}
              maxLength={4000}
              onChange={(e) => setDraft({ ...draft, mission: e.target.value })}
              placeholder="What is this company here to do?"
            />
          </div>
          <div>
            <Label>Stage</Label>
            <Input
              value={draft.stage}
              maxLength={40}
              onChange={(e) => setDraft({ ...draft, stage: e.target.value })}
              placeholder="e.g. seed"
            />
          </div>
          <Button onClick={create} disabled={creating || draft.name.trim().length < 2}>
            {creating ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
            Create
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-3">
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" /> Loading…
          </p>
        ) : companies.length === 0 ? (
          <p className="text-sm text-muted-foreground">No companies yet. Create one above.</p>
        ) : (
          companies.map((company) => {
            const blank = isBlankCompany(company);
            const active = getActiveCompanyId() === company.id;
            return (
              <Card key={company.id} className="border-border/60 bg-card/60">
                <CardContent className="flex items-center justify-between gap-3 p-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <Building2 className="size-4 shrink-0 text-primary" />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-foreground">
                        {company.name || "Unnamed company"}
                        {active && <span className="ml-2 text-[10px] font-normal text-primary">ACTIVE</span>}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {blank
                          ? "Needs setup — use Rename to give it a name"
                          : `${company.stage || "—"} · ${company.mission || "No mission"}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyId === company.id}
                      onClick={() => rename(company)}
                    >
                      {blank ? "Set up" : "Rename"}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={companies.length <= 1 || busyId === company.id}
                      title={
                        companies.length <= 1
                          ? "Keep at least one company"
                          : "Delete company"
                      }
                      onClick={() => remove(company)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </section>
  );
}
