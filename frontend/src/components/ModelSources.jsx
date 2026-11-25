import { useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import {
  Check,
  CircleAlert,
  Cpu,
  LoaderCircle,
  Pencil,
  Plus,
  ShieldCheck,
  Trash2,
  Wifi,
} from "lucide-react";
import {
  clearAgentLLMRoute,
  createLLMSource,
  deleteLLMSource,
  getLLMSettings,
  setAgentLLMRoutesBulk,
  setAgentLLMRoute,
  testLLMSource,
  updateLLMSource,
} from "../api";
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
import { Separator } from "@/components/ui/separator";

const roles = ["CEO", "CFO", "CTO", "CSO", "BOARD"];
const sourceTypes = {
  lm_studio: {
    label: "LM Studio",
    baseUrl: "http://localhost:1234/v1",
    keyRequired: false,
  },
  ollama: {
    label: "Ollama",
    baseUrl: "http://localhost:11434/v1",
    keyRequired: false,
  },
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    keyRequired: true,
  },
  anthropic: {
    label: "Anthropic Claude",
    baseUrl: "https://api.anthropic.com",
    keyRequired: true,
  },
  google_gemini: {
    label: "Google Gemini",
    baseUrl: "https://generativelanguage.googleapis.com",
    keyRequired: true,
  },
  openrouter: {
    label: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    keyRequired: true,
  },
  groq: {
    label: "Groq",
    baseUrl: "https://api.groq.com/openai/v1",
    keyRequired: true,
  },
  together: {
    label: "Together AI",
    baseUrl: "https://api.together.xyz/v1",
    keyRequired: true,
  },
  fireworks: {
    label: "Fireworks AI",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    keyRequired: true,
  },
  mistral: {
    label: "Mistral AI",
    baseUrl: "https://api.mistral.ai/v1",
    keyRequired: true,
  },
  deepseek: {
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    keyRequired: true,
  },
  xai: {
    label: "xAI",
    baseUrl: "https://api.x.ai/v1",
    keyRequired: true,
  },
  cerebras: {
    label: "Cerebras",
    baseUrl: "https://api.cerebras.ai/v1",
    keyRequired: true,
  },
  custom: {
    label: "Custom OpenAI-compatible API",
    baseUrl: "",
    keyRequired: true,
  },
};
const providerGroups = [
  { label: "Local servers", providers: ["lm_studio", "ollama"] },
  {
    label: "OpenAI-compatible APIs",
    providers: [
      "openai",
      "openrouter",
      "groq",
      "together",
      "fireworks",
      "mistral",
      "deepseek",
      "xai",
      "cerebras",
      "custom",
    ],
  },
  { label: "Native APIs", providers: ["anthropic", "google_gemini"] },
];

const emptyDraft = {
  name: "",
  provider: "lm_studio",
  base_url: sourceTypes.lm_studio.baseUrl,
  api_key: "",
  clear_api_key: false,
};

const selectClass =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50";

function providerLabel(provider) {
  return sourceTypes[provider]?.label || provider;
}

export default function ModelSources() {
  const { getToken } = useAuth();
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false);
  const [editingSource, setEditingSource] = useState(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [testingSourceId, setTestingSourceId] = useState(null);
  const [modelsBySource, setModelsBySource] = useState({});
  const [routes, setRoutes] = useState({});
  const [savingRole, setSavingRole] = useState("");
  const [globalSourceId, setGlobalSourceId] = useState("");
  const [globalModelName, setGlobalModelName] = useState("");
  const [globalScope, setGlobalScope] = useState("executives");
  const [globalSaving, setGlobalSaving] = useState(false);

  const accessToken = async () => {
    const token = await getToken();
    if (!token) throw new Error("Your session has expired. Sign in again.");
    return token;
  };

  const refresh = async () => {
    const token = await accessToken();
    const next = await getLLMSettings(token);
    setSettings(next);
    setRoutes(Object.fromEntries(
      next.routes.map((route) => [
        route.role,
        {
          sourceId: route.source_id ? String(route.source_id) : "",
          modelName: route.model_name || "",
        },
      ]),
    ));
  };

  useEffect(() => {
    refresh()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const openNewSource = () => {
    setEditingSource(null);
    setDraft({ ...emptyDraft });
    setError("");
    setSourceDialogOpen(true);
  };

  const openEditSource = (source) => {
    setEditingSource(source);
    setDraft({
      name: source.name,
      provider: source.provider,
      base_url: source.base_url,
      api_key: "",
      clear_api_key: false,
    });
    setError("");
    setSourceDialogOpen(true);
  };

  const saveSource = async (event) => {
    event.preventDefault();
    setSourceBusy(true);
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      const payload = {
        name: draft.name.trim(),
        base_url: draft.base_url.trim(),
      };
      if (draft.api_key.trim()) payload.api_key = draft.api_key.trim();
      if (!editingSource) payload.provider = draft.provider;
      if (editingSource && draft.clear_api_key) payload.clear_api_key = true;

      if (editingSource) {
        await updateLLMSource(editingSource.id, payload, token);
      } else {
        await createLLMSource(payload, token);
      }
      await refresh();
      setSourceDialogOpen(false);
      setNotice(editingSource ? "Source updated." : "Source added.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSourceBusy(false);
    }
  };

  const testSource = async (source) => {
    setTestingSourceId(source.id);
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      const result = await testLLMSource(source.id, token);
      setModelsBySource((current) => ({ ...current, [source.id]: result.models }));
      setNotice(
        result.models.length
          ? `${source.name} connected · ${result.models.length} model${result.models.length === 1 ? "" : "s"} found.`
          : `${source.name} responded, but did not list selectable models. Check that the provider exposes its supported model catalog.`,
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setTestingSourceId(null);
    }
  };

  const removeSource = async (source) => {
    if (!window.confirm(`Remove "${source.name}"? This cannot be undone.`)) return;
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      await deleteLLMSource(source.id, token);
      await refresh();
      setNotice("Source removed.");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const saveRoute = async (role) => {
    const route = routes[role] || { sourceId: "", modelName: "" };
    setSavingRole(role);
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      if (route.sourceId) {
        await setAgentLLMRoute(
          role,
          { source_id: Number(route.sourceId), model_name: route.modelName.trim() },
          token,
        );
      } else {
        await clearAgentLLMRoute(role, token);
      }
      await refresh();
      setNotice(`${role} route saved.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingRole("");
    }
  };

  const changeRoute = (role, key, value) => {
    setRoutes((current) => ({
      ...current,
      [role]: { ...(current[role] || { sourceId: "", modelName: "" }), [key]: value },
    }));
  };

  const changeGlobalSource = (sourceId) => {
    setGlobalSourceId(sourceId);
    setGlobalModelName("");
    const source = settings?.sources.find((item) => item.id === Number(sourceId));
    if (source && modelsBySource[source.id] === undefined) {
      void testSource(source);
    }
  };

  const changeRouteSource = (role, sourceId) => {
    changeRoute(role, "sourceId", sourceId);
    changeRoute(role, "modelName", "");
    const source = settings?.sources.find((item) => item.id === Number(sourceId));
    if (source && modelsBySource[source.id] === undefined) {
      void testSource(source);
    }
  };

  const applyGlobalRoute = async () => {
    const rolesToApply = globalScope === "all"
      ? roles
      : roles.filter((role) => role !== "BOARD");
    setGlobalSaving(true);
    setError("");
    setNotice("");
    try {
      const token = await accessToken();
      await setAgentLLMRoutesBulk(
        {
          source_id: Number(globalSourceId),
          model_name: globalModelName,
          roles: rolesToApply,
        },
        token,
      );
      await refresh();
      setNotice(
        `Applied ${globalModelName} to ${rolesToApply.length} roles: ${rolesToApply.join(", ")}.`,
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setGlobalSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading model sources…
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div className="space-y-2">
          <Badge variant="outline" className="gap-2 border-primary/25 font-mono text-[9px] tracking-[0.16em] text-primary">
            <Cpu className="size-3" /> INFERENCE CONFIGURATION
          </Badge>
          <h2 className="font-heading text-2xl tracking-wide sm:text-3xl">Model Sources</h2>
          <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
            Bring your own keys (BYOK): API keys are entered by you, stored encrypted, and never baked into the app. Add local inference servers or hosted AI providers, test connectivity, then choose a source and model for each council role.
          </p>
        </div>
        <Button
          onClick={openNewSource}
          disabled={!settings?.encryption_key_ready}
          className="gap-2"
        >
          <Plus className="size-4" /> Add source
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <CircleAlert className="size-4" />
          <AlertTitle>Model source action failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <Check className="size-4" />
          <AlertTitle>Source status</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}
      {!settings?.encryption_key_ready && (
        <Alert variant="destructive">
          <ShieldCheck className="size-4" />
          <AlertTitle>Secure key storage is not configured</AlertTitle>
          <AlertDescription>
            Set a stable <code>LLM_CONFIG_ENCRYPTION_KEY</code> on the backend before saving provider settings. Generate one with Python’s Fernet utility and keep it private across deployments.
          </AlertDescription>
        </Alert>
      )}

      <Card className="border-border/70 bg-card/80">
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="font-heading text-xl">Connected sources</CardTitle>
            <CardDescription className="mt-1">
              Credentials are encrypted by the backend and never sent back to this page.
            </CardDescription>
          </div>
          <Badge variant="outline" className="shrink-0 border-primary/25 text-primary">
            {settings?.sources.length || 0} configured
          </Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          {settings?.sources.length ? settings.sources.map((source) => {
            const assignedRoles = settings.routes
              .filter((route) => route.source_id === source.id)
              .map((route) => route.role);
            const models = modelsBySource[source.id];
            return (
              <div
                key={source.id}
                className="flex flex-col gap-4 rounded-lg border border-border/70 bg-background/60 p-4 lg:flex-row lg:items-center"
              >
                <div className="grid size-10 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
                  <Cpu className="size-4" />
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium">{source.name}</p>
                    <Badge variant="secondary">{providerLabel(source.provider)}</Badge>
                    {source.api_key_configured && (
                      <Badge variant="outline" className="border-emerald-500/30 text-emerald-300">
                        API key saved
                      </Badge>
                    )}
                  </div>
                  <p className="break-all font-mono text-xs text-muted-foreground">{source.base_url}</p>
                  <p className="text-xs text-muted-foreground">
                    {assignedRoles.length
                      ? `Assigned to ${assignedRoles.join(", ")}`
                      : "Not assigned to a role"}
                    {models ? ` · ${models.length} models discovered` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => testSource(source)}
                    disabled={testingSourceId === source.id}
                  >
                    {testingSourceId === source.id
                      ? <LoaderCircle className="mr-2 size-3.5 animate-spin" />
                      : <Wifi className="mr-2 size-3.5" />}
                    Test / list models
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Edit ${source.name}`} onClick={() => openEditSource(source)}>
                    <Pencil className="size-4" />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Delete ${source.name}`} onClick={() => removeSource(source)}>
                    <Trash2 className="size-4 text-destructive" />
                  </Button>
                </div>
              </div>
            );
          }) : (
            <div className="rounded-lg border border-dashed border-border p-8 text-center">
              <Cpu className="mx-auto size-6 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium">No saved sources yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Add a local inference server or hosted provider to route an executive.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/80">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Executive model routing</CardTitle>
          <CardDescription>
            Routes are captured when a meeting attempt starts; changes take effect on the next run or retry.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-4 rounded-lg border border-primary/20 bg-primary/5 p-4">
            <div>
              <p className="font-medium">Global source and model</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Configure one provider once, then apply it to the C-suite or every agent. You can still override individual roles below.
              </p>
            </div>
            <div className="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-end">
              <div className="space-y-2">
                <Label htmlFor="global-source">Source</Label>
                <select
                  id="global-source"
                  className={selectClass}
                  value={globalSourceId}
                  onChange={(event) => changeGlobalSource(event.target.value)}
                >
                  <option value="">Choose a source</option>
                  {settings?.sources.map((source) => (
                    <option key={source.id} value={source.id}>
                      {source.name} · {providerLabel(source.provider)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="global-model">Model</Label>
                <select
                  id="global-model"
                  className={selectClass}
                  value={globalModelName}
                  disabled={!globalSourceId || !(modelsBySource[Number(globalSourceId)] || []).length}
                  onChange={(event) => setGlobalModelName(event.target.value)}
                >
                  <option value="">
                    {globalSourceId
                      ? testingSourceId === Number(globalSourceId)
                        ? "Loading available models…"
                        : "Choose a model"
                      : "Choose a source first"}
                  </option>
                  {(modelsBySource[Number(globalSourceId)] || []).map((model) => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="global-scope">Apply to</Label>
                <select
                  id="global-scope"
                  className={selectClass}
                  value={globalScope}
                  onChange={(event) => setGlobalScope(event.target.value)}
                >
                  <option value="executives">C-suite only · 4 roles</option>
                  <option value="all">All agents · include BOARD</option>
                </select>
              </div>
              <Button
                onClick={applyGlobalRoute}
                disabled={
                  globalSaving
                  || !settings?.encryption_key_ready
                  || !globalSourceId
                  || !globalModelName
                }
              >
                {globalSaving && <LoaderCircle className="mr-2 size-4 animate-spin" />}
                Apply globally
              </Button>
            </div>
          </div>

          {settings?.routes.map((route, index) => {
            const current = routes[route.role] || { sourceId: "", modelName: "" };
            const selectedSourceId = Number(current.sourceId);
            const modelOptions = modelsBySource[selectedSourceId] || [];
            const currentModelMissing = current.modelName && !modelOptions.includes(current.modelName);
            return (
              <div key={route.role}>
                {index > 0 && <Separator className="my-4" />}
                <div className="grid gap-3 lg:grid-cols-[100px_1fr_1fr_auto] lg:items-end">
                  <div>
                    <Label className="text-xs text-muted-foreground">COUNCIL ROLE</Label>
                    <p className="mt-2 font-heading text-lg">{route.role}</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`source-${route.role}`}>Source</Label>
                    <select
                      id={`source-${route.role}`}
                      className={selectClass}
                      value={current.sourceId}
                      onChange={(event) => changeRouteSource(route.role, event.target.value)}
                    >
                      <option value="">Environment fallback · {route.model_name || "unset"}</option>
                      {settings.sources.map((source) => (
                        <option key={source.id} value={source.id}>
                          {source.name} · {providerLabel(source.provider)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`model-${route.role}`}>Model ID</Label>
                    <select
                      id={`model-${route.role}`}
                      className={selectClass}
                      value={current.modelName}
                      disabled={
                        !current.sourceId
                        || testingSourceId === selectedSourceId
                        || (!modelOptions.length && !currentModelMissing)
                      }
                      onChange={(event) => changeRoute(route.role, "modelName", event.target.value)}
                    >
                      <option value="">
                        {current.sourceId
                          ? testingSourceId === selectedSourceId
                            ? "Loading available models…"
                            : "Select a model"
                          : "Select a source first"}
                      </option>
                      {currentModelMissing && (
                        <option value={current.modelName}>{current.modelName} · saved</option>
                      )}
                      {modelOptions.map((model) => <option key={model} value={model}>{model}</option>)}
                    </select>
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => saveRoute(route.role)}
                    disabled={
                      savingRole === route.role
                      || !settings.encryption_key_ready
                      || Boolean(current.sourceId && !current.modelName)
                    }
                  >
                    {savingRole === route.role
                      ? <LoaderCircle className="mr-2 size-3.5 animate-spin" />
                      : <Check className="mr-2 size-3.5" />}
                    Save
                  </Button>
                </div>
                {route.environment_fallback && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Currently using the backend environment configuration.
                  </p>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      <p className="text-xs leading-5 text-muted-foreground">
        LM Studio and Ollama must be reachable from the backend host; <code>localhost</code> means the API machine, not this browser. Most hosted sources use the OpenAI-compatible API, while Anthropic Claude and Google Gemini use their native APIs and model catalogs.
      </p>

      <Dialog open={sourceDialogOpen} onOpenChange={setSourceDialogOpen}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto border-border/80 bg-card">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">
              {editingSource ? "Edit model source" : "Add model source"}
            </DialogTitle>
            <DialogDescription>
              Provider credentials are encrypted server-side. Leave a saved key field blank to keep its current value.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={saveSource} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="source-name">Display name</Label>
              <Input
                id="source-name"
                required
                minLength={2}
                maxLength={100}
                value={draft.name}
                onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                placeholder="My LM Studio"
              />
            </div>
            {!editingSource && (
              <div className="space-y-2">
                <Label htmlFor="source-provider">Provider type</Label>
                <select
                  id="source-provider"
                  className={selectClass}
                  value={draft.provider}
                  onChange={(event) => setDraft((current) => ({
                    ...current,
                    provider: event.target.value,
                    base_url: sourceTypes[event.target.value].baseUrl,
                  }))}
                >
                  {providerGroups.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.providers.map((id) => (
                        <option key={id} value={id}>{sourceTypes[id].label}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>
            )}
            {draft.provider !== "google_gemini" && (
              <div className="space-y-2">
                <Label htmlFor="source-url">API base URL</Label>
                <Input
                  id="source-url"
                  type="url"
                  required={draft.provider === "custom"}
                  value={draft.base_url}
                  onChange={(event) => setDraft((current) => ({ ...current, base_url: event.target.value }))}
                  placeholder="https://api.example.com/v1"
                />
                {["lm_studio", "ollama"].includes(draft.provider) && (
                  <p className="text-xs leading-5 text-muted-foreground">
                    The endpoint must be reachable from the backend machine; <code>localhost</code> refers to the backend host.
                  </p>
                )}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="source-api-key">
                API key {sourceTypes[draft.provider]?.keyRequired ? "(required)" : "(optional for local servers)"}
              </Label>
              <Input
                id="source-api-key"
                type="password"
                autoComplete="new-password"
                required={!editingSource && sourceTypes[draft.provider]?.keyRequired}
                value={draft.api_key}
                onChange={(event) => setDraft((current) => ({ ...current, api_key: event.target.value }))}
                placeholder={editingSource?.api_key_configured ? "Saved key hidden · enter to replace" : "Paste provider API key"}
              />
              {editingSource?.provider === "lm_studio" && editingSource.api_key_configured && (
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={draft.clear_api_key}
                    onChange={(event) => setDraft((current) => ({ ...current, clear_api_key: event.target.checked }))}
                    className="accent-primary"
                  />
                  Clear saved key
                </label>
              )}
            </div>
            <DialogFooter className="gap-2 sm:gap-2">
              <Button type="button" variant="outline" onClick={() => setSourceDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={sourceBusy || !settings?.encryption_key_ready}>
                {sourceBusy && <LoaderCircle className="mr-2 size-4 animate-spin" />}
                {editingSource ? "Save changes" : "Add source"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
