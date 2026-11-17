import { useCallback, useState } from "react";

import { useBridge } from "../app/BridgeContext";
import { useLoad } from "../app/useLoad";
import { getTask, listTasks } from "../bridge/trust";
import { ReceiptView } from "../components/ReceiptView";
import { Empty, ErrorText, Planned, Section, StatePill } from "../components/ui";

function ReceiptPanel({ taskId }: { taskId: string }) {
  const bridge = useBridge();
  const detail = useLoad(
    true,
    useCallback(() => getTask(bridge, taskId), [bridge, taskId]),
  );
  if (detail.state.kind === "loading") return <Empty>Loading receipt…</Empty>;
  if (detail.state.kind === "error") return <ErrorText>{detail.state.error.message}</ErrorText>;
  return <ReceiptView receipt={detail.state.value.receipt} />;
}

export function TaskHistory({ ready }: { ready: boolean }) {
  const bridge = useBridge();
  const tasks = useLoad(
    ready,
    useCallback(() => listTasks(bridge), [bridge]),
  );
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-6">
      <Section title="Receipts">
        {tasks.state.kind === "loading" && <Empty>Loading…</Empty>}
        {tasks.state.kind === "error" && <ErrorText>{tasks.state.error.message}</ErrorText>}
        {tasks.state.kind === "ready" && tasks.state.value.tasks.length === 0 && (
          <Empty>No tasks have run yet.</Empty>
        )}
        {tasks.state.kind === "ready" && tasks.state.value.tasks.length > 0 && (
          <div className="grid grid-cols-[minmax(16rem,1fr)_2fr] gap-6">
            <ul className="divide-y divide-line" aria-label="Tasks">
              {tasks.state.value.tasks.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    aria-pressed={selected === t.id}
                    onClick={() => {
                      setSelected(t.id);
                    }}
                    className="motion-base flex w-full items-center justify-between gap-3 py-2 text-left text-sm hover:bg-surface-raised"
                  >
                    <span className="truncate text-ink">{t.objective}</span>
                    <StatePill state={t.state} />
                  </button>
                </li>
              ))}
            </ul>
            <div>
              {selected ? (
                <ReceiptPanel taskId={selected} />
              ) : (
                <Empty>Select a task to see its receipt.</Empty>
              )}
            </div>
          </div>
        )}
      </Section>
      <Planned name="Multi-step task timelines" when="v0.2 · M7" />
    </div>
  );
}
