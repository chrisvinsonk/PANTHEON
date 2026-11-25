import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import { Building2, ChevronDown, LoaderCircle, Plus } from "lucide-react";
import {
  createCompanyProfile,
  getCompanies,
} from "../api";
import {
  getActiveCompanyId,
  setActiveCompanyId,
  switchActiveCompany,
} from "../company";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function CompanySwitcher({ onManage }) {
  const { getToken } = useAuth();
  const [companies, setCompanies] = useState([]);
  const [activeId, setActiveId] = useState(getActiveCompanyId());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ name: "", mission: "", stage: "" });

  const load = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    const list = await getCompanies(token);
    setCompanies(list);
    const stored = getActiveCompanyId();
    const match = list.find((company) => company.id === stored);
    if (match) {
      setActiveId(match.id);
    } else if (list.length) {
      const fallback = list[0].id;
      setActiveCompanyId(fallback);
      setActiveId(fallback);
      if (stored && stored !== fallback) {
        // The stored company no longer exists; reload so every view refetches
        // against the fallback instead of failing on a stale header.
        window.location.reload();
      }
    }
  };

  useEffect(() => {
    load()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const activeCompany = useMemo(
    () => companies.find((company) => company.id === activeId) || companies[0] || null,
    [companies, activeId],
  );

  const changeCompany = (event) => {
    const nextId = Number(event.target.value);
    if (!nextId || nextId === activeId) return;
    switchActiveCompany(nextId);
  };

  const create = async () => {
    if (!draft.name.trim()) return;
    setCreating(true);
    setError("");
    try {
      const token = await getToken();
      if (!token) throw new Error("Your session has expired. Sign in again.");
      const company = await createCompanyProfile(
        {
          name: draft.name.trim(),
          mission: draft.mission.trim(),
          stage: draft.stage.trim(),
        },
        token,
      );
      switchActiveCompany(company.id);
    } catch (requestError) {
      setError(requestError.message);
      setCreating(false);
    }
  };

  if (loading) {
    return (
      <span className="flex items-center gap-2 text-xs text-muted-foreground">
        <LoaderCircle className="size-3.5 animate-spin" /> Companies…
      </span>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <div className="relative flex items-center">
        <Building2 className="pointer-events-none absolute left-2.5 size-3.5 text-primary" />
        <select
          aria-label="Active company"
          value={activeCompany?.id ?? ""}
          onChange={changeCompany}
          className="h-9 max-w-[42vw] appearance-none rounded-md border border-primary/30 bg-primary/5 py-1 pl-8 pr-8 text-xs font-medium text-foreground outline-none transition-colors hover:border-primary/50 focus:border-primary/60 sm:max-w-[220px]"
        >
          {companies.map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 size-3.5 text-muted-foreground" />
      </div>
      <Button
        variant="outline"
        size="icon"
        className="size-9 border-primary/30 text-primary"
        title="New company"
        onClick={() => {
          setDraft({ name: "", mission: "", stage: "" });
          setCreateOpen(true);
        }}
      >
        <Plus className="size-4" />
      </Button>
      {onManage && (
        <Button
          variant="ghost"
          size="sm"
          className="hidden text-xs text-muted-foreground sm:inline-flex"
          onClick={onManage}
        >
          Profile
        </Button>
      )}
      {error && !createOpen && (
        <span className="max-w-[160px] truncate text-[10px] text-destructive" title={error}>
          {error}
        </span>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-lg border-border/80 bg-card">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">New company profile</DialogTitle>
            <DialogDescription>
              Each company keeps its own context, conclaves, evidence, decisions, feedback and operational drafts.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="new-company-name">Company name</Label>
              <Input
                id="new-company-name"
                value={draft.name}
                maxLength={160}
                placeholder="e.g. Northstar Labs"
                onChange={(event) =>
                  setDraft((current) => ({ ...current, name: event.target.value }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="new-company-mission">Mission</Label>
              <Textarea
                id="new-company-mission"
                rows={2}
                maxLength={4000}
                value={draft.mission}
                placeholder="What is this company here to do?"
                onChange={(event) =>
                  setDraft((current) => ({ ...current, mission: event.target.value }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="new-company-stage">Stage</Label>
              <Input
                id="new-company-stage"
                value={draft.stage}
                maxLength={40}
                placeholder="e.g. pre-seed, seed, growth"
                onChange={(event) =>
                  setDraft((current) => ({ ...current, stage: event.target.value }))
                }
              />
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={create}
              disabled={creating || !draft.name.trim()}
              className="gap-2"
            >
              {creating ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
              Create and switch
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
