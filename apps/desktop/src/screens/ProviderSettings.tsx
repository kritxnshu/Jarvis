import { useCallback, useId, useState, type SyntheticEvent } from "react";

import type { HealthCheckView, ProviderView, RouteStepView } from "@jarvis/contracts";

import { useBridge } from "../app/BridgeContext";
import { useLoad } from "../app/useLoad";
import { BackendError } from "../bridge/bridge";
import {
  checkProvider,
  deleteCredential,
  listProviders,
  saveCredential,
  setRoute,
  updateProvider,
} from "../bridge/chat";
import { Button, Empty, ErrorText, Planned, Section } from "../components/ui";

function message(err: unknown): string {
  return err instanceof BackendError ? err.message : "The request failed.";
}

function ProviderCard({ p, onChange }: { p: ProviderView; onChange: () => void }) {
  const bridge = useBridge();
  const [key, setKey] = useState("");
  const [url, setUrl] = useState(p.base_url);
  const [health, setHealth] = useState<HealthCheckView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const keyId = useId();
  const urlId = useId();
  const needsKey = !p.key_optional;
  const fail = (err: unknown) => {
    setError(message(err));
  };

  const save = (e: SyntheticEvent) => {
    e.preventDefault();
    setError(null);
    saveCredential(bridge, p.id, key).then(() => {
      setKey(""); // the key is never shown again, only its masked hint
      onChange();
    }, fail);
  };

  return (
    <article className="rounded-md border border-line-strong bg-surface-raised p-4">
      <div className="flex items-center justify-between gap-4">
        <h3 className="font-medium text-ink">{p.display_name}</h3>
        <span className={`text-xs ${p.configured ? "text-ok" : "text-ink-subtle"}`}>
          {p.configured ? "Configured" : "Not configured"}
        </span>
      </div>
      {p.retention_policy_url && (
        <p className="mt-1 text-xs text-ink-subtle">
          Data use is governed by the provider, not JARVIS:{" "}
          <span className="font-mono select-all">{p.retention_policy_url}</span>
        </p>
      )}
      {(p.kind === "ollama" || p.kind === "openai") && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            updateProvider(bridge, p.id, { base_url: url }).then(onChange, fail);
          }}
        >
          <label htmlFor={urlId} className="sr-only">
            {p.display_name} endpoint
          </label>
          <input
            id={urlId}
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
            }}
            className="flex-1 rounded-md border border-line-strong bg-surface px-3 py-1.5 font-mono text-xs text-ink"
          />
          <button
            type="submit"
            className="rounded-md border border-line-strong px-3 text-sm text-ink"
          >
            Save endpoint
          </button>
        </form>
      )}
      {needsKey && (
        <form className="mt-3 flex items-center gap-2" onSubmit={save}>
          <label htmlFor={keyId} className="sr-only">
            {p.display_name} API key
          </label>
          <input
            id={keyId}
            type="password"
            autoComplete="off"
            value={key}
            placeholder={p.credential_hint ? `Saved key ${p.credential_hint}` : "API key"}
            onChange={(e) => {
              setKey(e.target.value);
            }}
            className="flex-1 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm text-ink"
          />
          <button
            type="submit"
            disabled={key.trim().length < 8}
            className="rounded-md border border-line-strong px-3 py-1.5 text-sm text-ink disabled:opacity-50"
          >
            {p.has_credential ? "Replace key" : "Save to Keychain"}
          </button>
          {p.has_credential && (
            <Button
              tone="danger"
              onClick={() => {
                deleteCredential(bridge, p.id).then(onChange, fail);
              }}
            >
              Remove
            </Button>
          )}
        </form>
      )}
      <div className="mt-3 flex items-center gap-3">
        <Button
          onClick={() => {
            setHealth(null);
            checkProvider(bridge, p.id).then(setHealth, fail);
          }}
        >
          Test connection
        </Button>
        {health && (
          <span role="status" className={`text-xs ${health.ok ? "text-ok" : "text-warn"}`}>
            {health.ok ? "Reachable" : "Not reachable"} — {health.detail}
          </span>
        )}
      </div>
      {error && <ErrorText>{error}</ErrorText>}
    </article>
  );
}

function ChatRoute({
  providers,
  chain,
  onChange,
}: {
  providers: ProviderView[];
  chain: RouteStepView[];
  onChange: () => void;
}) {
  const bridge = useBridge();
  const [steps, setSteps] = useState<RouteStepView[]>(chain);
  const [error, setError] = useState<string | null>(null);
  const edit = (i: number, change: Partial<RouteStepView>) => {
    setSteps((prev) => prev.map((s, n) => (n === i ? { ...s, ...change } : s)));
  };
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-ink-muted">
        Chat uses the first model; if it fails before answering, the next one is tried and the
        switch is recorded in the audit log.
      </p>
      <ol className="flex flex-col gap-2">
        {steps.map((s, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-6 font-mono text-xs text-ink-subtle">{i + 1}.</span>
            <select
              aria-label={`Provider ${String(i + 1)}`}
              value={s.provider_id}
              onChange={(e) => {
                edit(i, { provider_id: e.target.value });
              }}
              className="rounded-md border border-line-strong bg-surface-raised px-2 py-1.5 text-sm text-ink"
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
            <input
              aria-label={`Model ${String(i + 1)}`}
              value={s.model}
              onChange={(e) => {
                edit(i, { model: e.target.value });
              }}
              className="w-56 rounded-md border border-line-strong bg-surface-raised px-2 py-1.5 font-mono text-xs text-ink"
            />
            <Button
              onClick={() => {
                setSteps((prev) => prev.filter((_, n) => n !== i));
              }}
            >
              Remove
            </Button>
          </li>
        ))}
      </ol>
      <div className="flex gap-2">
        <Button
          onClick={() => {
            setSteps((prev) => [...prev, { provider_id: providers[0]?.id ?? "ollama", model: "" }]);
          }}
        >
          Add fallback
        </Button>
        <Button
          tone="primary"
          onClick={() => {
            setError(null);
            setRoute(bridge, "chat", steps).then(onChange, (err: unknown) => {
              setError(message(err));
            });
          }}
        >
          Save route
        </Button>
      </div>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}

export function ProviderSettings({ ready }: { ready: boolean }) {
  const bridge = useBridge();
  const data = useLoad(
    ready,
    useCallback(() => listProviders(bridge), [bridge]),
  );
  if (data.state.kind === "loading") return <Empty>Loading providers…</Empty>;
  if (data.state.kind === "error") return <ErrorText>{data.state.error.message}</ErrorText>;
  const { providers, routes } = data.state.value;
  return (
    <div className="flex flex-col gap-6">
      <Section title="Model providers">
        <p className="mb-3 text-sm text-ink-muted">
          Keys are stored in the macOS Keychain and never shown again. Ollama runs models on this
          Mac for free: install it from ollama.com, then run <code>ollama pull llama3.2</code>.
        </p>
        <div className="flex flex-col gap-3">
          {providers.map((p) => (
            <ProviderCard key={`${p.id}-${p.base_url}`} p={p} onChange={data.reload} />
          ))}
        </div>
      </Section>
      <Section title="Chat model and fallback">
        <ChatRoute
          key={JSON.stringify(routes.chat)}
          providers={providers}
          chain={routes.chat ?? []}
          onChange={data.reload}
        />
      </Section>
      <Planned name="Voice providers (speech-to-text, text-to-speech)" when="v0.3 · M10" />
      <Planned name="Per-provider screen-content opt-in" when="v0.3 · M9" />
    </div>
  );
}
