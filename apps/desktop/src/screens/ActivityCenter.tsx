import { useCallback, useState } from "react";

import type { ApprovalView, TaskDetail } from "@jarvis/contracts";

import { useBridge } from "../app/BridgeContext";
import { useLoad } from "../app/useLoad";
import { BackendError } from "../bridge/bridge";
import {
  confirmHighRisk,
  decideApproval,
  getTask,
  listApprovals,
  listTasks,
  reviewAction,
  type ReviewChoice,
} from "../bridge/trust";
import { ReceiptView } from "../components/ReceiptView";
import { Button, Empty, ErrorText, Planned, Section, StatePill } from "../components/ui";

function useAction(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    fn().then(
      () => {
        setBusy(false);
        onDone();
      },
      (err: unknown) => {
        setBusy(false);
        setError(err instanceof BackendError ? err.message : "The request failed.");
      },
    );
  };
  return { busy, error, run };
}

function ApprovalCard({ approval, onDone }: { approval: ApprovalView; onDone: () => void }) {
  const bridge = useBridge();
  const { busy, error, run } = useAction(onDone);
  const r = approval.request;
  return (
    <article className="rounded-md border border-line-strong bg-surface-raised p-4">
      <h3 className="font-medium text-ink">{r.intent}</h3>
      <dl className="mt-2 grid grid-cols-[9rem_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-ink-subtle">Why</dt>
        <dd className="text-ink-muted">{r.why}</dd>
        <dt className="text-ink-subtle">Service</dt>
        <dd className="text-ink-muted">{r.service}</dd>
        <dt className="text-ink-subtle">Data affected</dt>
        <dd className="text-ink-muted">{r.data_affected}</dd>
        <dt className="text-ink-subtle">Consequences</dt>
        <dd className="text-ink-muted">{r.consequences}</dd>
        <dt className="text-ink-subtle">Expires</dt>
        <dd className="font-mono text-xs text-ink-muted">{approval.expires_at}</dd>
      </dl>
      <details className="mt-2 text-xs text-ink-muted">
        <summary className="cursor-pointer">Exact parameters</summary>
        <pre className="mt-1 overflow-x-auto rounded bg-canvas p-2 font-mono">
          {JSON.stringify(r.parameters, null, 2)}
        </pre>
      </details>
      <div className="mt-3 flex items-center gap-2">
        {approval.highest_risk ? (
          <Button
            tone="primary"
            disabled={busy}
            onClick={() => {
              run(() => confirmHighRisk(bridge, approval.id));
            }}
          >
            Review in macOS dialog…
          </Button>
        ) : (
          <Button
            tone="primary"
            disabled={busy}
            onClick={() => {
              run(() => decideApproval(bridge, approval.id, true));
            }}
          >
            Approve
          </Button>
        )}
        <Button
          tone="danger"
          disabled={busy}
          onClick={() => {
            run(() => decideApproval(bridge, approval.id, false));
          }}
        >
          Reject
        </Button>
        {approval.highest_risk && (
          <span className="text-xs text-ink-subtle">
            High risk: final confirmation happens outside this window.
          </span>
        )}
      </div>
      {error && <ErrorText>{error}</ErrorText>}
    </article>
  );
}

function ReviewCard({ detail, onDone }: { detail: TaskDetail; onDone: () => void }) {
  const bridge = useBridge();
  const { busy, error, run } = useAction(onDone);
  const action = detail.receipt.actions.find(
    (a) => a.state === "uncertain" || a.state === "completed",
  );
  const choose = (choice: ReviewChoice) => {
    if (action) run(() => reviewAction(bridge, detail.task.id, action.action_id, choice));
  };
  return (
    <article className="rounded-md border border-warn/40 bg-surface-raised p-4">
      <ReceiptView receipt={detail.receipt} />
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          disabled={busy || !action}
          onClick={() => {
            choose("happened");
          }}
        >
          It happened
        </Button>
        <Button
          disabled={busy || !action}
          onClick={() => {
            choose("retry");
          }}
        >
          It didn’t happen — retry
        </Button>
        <Button
          tone="danger"
          disabled={busy || !action}
          onClick={() => {
            choose("cancel");
          }}
        >
          Cancel task
        </Button>
      </div>
      <p className="mt-2 text-xs text-ink-subtle">
        “It happened” is recorded as user-attested, not verified. A retry asks for approval again.
      </p>
      {error && <ErrorText>{error}</ErrorText>}
    </article>
  );
}

export function ActivityCenter({ ready }: { ready: boolean }) {
  const bridge = useBridge();
  const approvals = useLoad(
    ready,
    useCallback(() => listApprovals(bridge), [bridge]),
  );
  const reviews = useLoad(
    ready,
    useCallback(async () => {
      const { tasks } = await listTasks(bridge);
      const waiting = tasks.filter((t) => t.state === "needs_review");
      return Promise.all(waiting.map((t) => getTask(bridge, t.id)));
    }, [bridge]),
  );
  const recent = useLoad(
    ready,
    useCallback(() => listTasks(bridge), [bridge]),
  );
  const refresh = () => {
    approvals.reload();
    reviews.reload();
    recent.reload();
  };

  return (
    <div className="flex flex-col gap-6">
      <Section title="Pending approvals" action={<Button onClick={refresh}>Refresh</Button>}>
        {approvals.state.kind === "loading" && <Empty>Loading…</Empty>}
        {approvals.state.kind === "error" && <ErrorText>{approvals.state.error.message}</ErrorText>}
        {approvals.state.kind === "ready" &&
          (approvals.state.value.approvals.length === 0 ? (
            <Empty>Nothing is waiting for your approval.</Empty>
          ) : (
            <div className="flex flex-col gap-3">
              {approvals.state.value.approvals.map((a) => (
                <ApprovalCard key={a.id} approval={a} onDone={refresh} />
              ))}
            </div>
          ))}
      </Section>
      <Section title="Needs review">
        {reviews.state.kind === "loading" && <Empty>Loading…</Empty>}
        {reviews.state.kind === "error" && <ErrorText>{reviews.state.error.message}</ErrorText>}
        {reviews.state.kind === "ready" &&
          (reviews.state.value.length === 0 ? (
            <Empty>No action has an unknown outcome.</Empty>
          ) : (
            <div className="flex flex-col gap-3">
              {reviews.state.value.map((d) => (
                <ReviewCard key={d.task.id} detail={d} onDone={refresh} />
              ))}
            </div>
          ))}
      </Section>
      <Section title="Recent tasks">
        {recent.state.kind === "ready" && recent.state.value.tasks.length === 0 && (
          <Empty>
            No tasks yet. Tasks appear here once JARVIS has tools to run (v0.1 · M3/M5).
          </Empty>
        )}
        {recent.state.kind === "ready" && recent.state.value.tasks.length > 0 && (
          <ul className="divide-y divide-line">
            {recent.state.value.tasks.slice(0, 20).map((t) => (
              <li key={t.id} className="flex items-center justify-between py-2 text-sm">
                <span className="truncate text-ink">{t.objective}</span>
                <StatePill state={t.state} />
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Planned name="Background tasks with progress" when="v0.2 · M7" />
    </div>
  );
}
