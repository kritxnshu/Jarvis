import { useCallback, useEffect, useId, useRef, useState, type SyntheticEvent } from "react";

import type { ChatMessageView } from "@jarvis/contracts";

import { useBridge } from "../app/BridgeContext";
import { useEvents } from "../app/EventHub";
import { useLoad } from "../app/useLoad";
import { BackendError } from "../bridge/bridge";
import {
  createConversation,
  listConversations,
  listMessages,
  sendMessage,
  stopMessage,
} from "../bridge/chat";
import type { BridgeEvent } from "../bridge/types";
import { Button, Empty, ErrorText, Planned } from "../components/ui";

const STATUS_NOTE: Record<string, string> = {
  interrupted: "Interrupted",
  failed: "Failed",
  streaming: "Streaming…",
};

function Bubble({ m, live }: { m: ChatMessageView; live: string | undefined }) {
  const mine = m.role === "user";
  return (
    <li className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[42rem] rounded-lg px-4 py-3 text-sm ${
          mine ? "bg-accent/20 text-ink" : "border border-line bg-surface text-ink"
        }`}
      >
        <p className="whitespace-pre-wrap">
          {(m.status === "streaming" ? (live ?? m.content) : m.content) ||
            (m.status === "streaming" ? "…" : "")}
        </p>
        {!mine && (
          <p className="mt-2 flex flex-wrap gap-2 font-mono text-xs text-ink-subtle">
            {m.provider_id && (
              <span>
                {m.provider_id} · {m.model}
              </span>
            )}
            {STATUS_NOTE[m.status] && (
              <span className={m.status === "failed" ? "text-danger" : "text-warn"}>
                {STATUS_NOTE[m.status]}
                {m.error ? ` — ${m.error}` : ""}
              </span>
            )}
          </p>
        )}
      </div>
    </li>
  );
}

function Conversation({ id }: { id: string }) {
  const bridge = useBridge();
  const [messages, setMessages] = useState<ChatMessageView[]>([]);
  // Streamed text per message, kept even if a delta arrives before the message is loaded.
  const [live, setLive] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const inputId = useId();
  const endRef = useRef<HTMLDivElement>(null);

  const reload = useCallback(() => {
    listMessages(bridge, id).then(
      (r) => {
        setMessages(r.messages);
      },
      (err: unknown) => {
        setError(err instanceof BackendError ? err.message : "Could not load messages.");
      },
    );
  }, [bridge, id]);
  useEffect(reload, [reload]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  useEvents(
    useCallback(
      (e: BridgeEvent) => {
        const p = e.payload ?? {};
        if (p.conversation_id !== id) return;
        if (
          e.type === "chat.delta" &&
          typeof p.text === "string" &&
          typeof p.message_id === "string"
        ) {
          const delta = p.text;
          const mid = p.message_id;
          setLive((prev) => ({ ...prev, [mid]: (prev[mid] ?? "") + delta }));
        } else if (e.type === "chat.started" || e.type === "chat.finished") {
          reload();
        }
      },
      [id, reload],
    ),
  );

  const streaming = messages.find((m) => m.status === "streaming");
  const send = (e: SyntheticEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    setError(null);
    sendMessage(bridge, id, value).then(
      () => {
        setText("");
        reload();
      },
      (err: unknown) => {
        setError(err instanceof BackendError ? err.message : "Could not send.");
      },
    );
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ol className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pb-4" aria-label="Messages">
        {messages.length === 0 && (
          <Empty>Ask anything. Replies stream in as they are written.</Empty>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} m={m} live={live[m.id]} />
        ))}
        <div ref={endRef} />
      </ol>
      {error && <ErrorText>{error}</ErrorText>}
      <form onSubmit={send} className="flex items-end gap-2 border-t border-line pt-3">
        <label htmlFor={inputId} className="sr-only">
          Message
        </label>
        <textarea
          id={inputId}
          rows={2}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) send(e);
          }}
          placeholder="Message JARVIS"
          className="min-h-[2.75rem] flex-1 resize-none rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-sm text-ink"
        />
        {streaming ? (
          <Button
            tone="danger"
            onClick={() => {
              void stopMessage(bridge, streaming.id).then(reload);
            }}
          >
            Stop
          </Button>
        ) : (
          <button
            type="submit"
            disabled={!text.trim()}
            className="motion-base rounded-md bg-accent px-4 py-2 text-sm font-medium text-canvas disabled:opacity-50"
          >
            Send
          </button>
        )}
      </form>
    </div>
  );
}

export function CommandCenter({ ready }: { ready: boolean }) {
  const bridge = useBridge();
  const list = useLoad(
    ready,
    useCallback(() => listConversations(bridge), [bridge]),
  );
  const [selected, setSelected] = useState<string | null>(null);
  const conversations = list.state.kind === "ready" ? list.state.value.conversations : [];
  const active = selected ?? conversations[0]?.id ?? null;

  const startNew = () => {
    void createConversation(bridge, "New conversation").then((c) => {
      setSelected(c.id);
      list.reload();
    });
  };

  return (
    <div className="flex h-[calc(100vh-14rem)] min-h-[24rem] gap-6">
      <nav aria-label="Conversations" className="flex w-56 shrink-0 flex-col gap-2">
        <Button tone="primary" onClick={startNew} disabled={!ready}>
          New conversation
        </Button>
        {list.state.kind === "error" && <ErrorText>{list.state.error.message}</ErrorText>}
        <ul className="flex flex-col gap-1 overflow-y-auto">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                aria-current={active === c.id ? "true" : undefined}
                onClick={() => {
                  setSelected(c.id);
                }}
                className={`motion-base w-full truncate rounded-md px-3 py-2 text-left text-sm ${
                  active === c.id ? "bg-surface-raised text-ink" : "text-ink-muted hover:text-ink"
                }`}
              >
                {c.title}
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-auto">
          <Planned name="Voice input" when="v0.3 · M10" />
        </div>
      </nav>
      {active ? (
        <Conversation key={active} id={active} />
      ) : (
        <Empty>Start a conversation. Models are set up in Provider Settings.</Empty>
      )}
    </div>
  );
}
