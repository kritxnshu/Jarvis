import type { ButtonHTMLAttributes, ReactNode } from "react";

type Tone = "primary" | "neutral" | "danger";

const TONES: Record<Tone, string> = {
  primary: "bg-accent text-canvas hover:bg-accent-ink",
  neutral: "border border-line-strong text-ink hover:bg-surface-raised",
  danger: "border border-danger/60 text-danger hover:bg-danger/10",
};

export function Button({
  tone = "neutral",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone }) {
  return (
    <button
      type="button"
      {...props}
      className={`motion-base rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${TONES[tone]} ${className}`}
    />
  );
}

export function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const id = `section-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section aria-labelledby={id} className="rounded-lg border border-line bg-surface p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 id={id} className="text-lg font-semibold text-ink">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

const STATE_TONE: Record<string, string> = {
  completed: "text-ok",
  verified: "text-ok",
  failed: "text-danger",
  cancelled: "text-ink-subtle",
  rejected: "text-ink-subtle",
  needs_review: "text-warn",
  uncertain: "text-warn",
  waiting_for_approval: "text-signal",
  running: "text-accent-ink",
};

export function StatePill({ state }: { state: string }) {
  return (
    <span className={`font-mono text-xs ${STATE_TONE[state] ?? "text-ink-muted"}`}>
      {state.replace(/_/g, " ")}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-ink-subtle">{children}</p>;
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="text-sm text-danger">
      {children}
    </p>
  );
}

export function Planned({ name, when }: { name: string; when: string }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-dashed border-line px-4 py-3">
      <span className="text-sm text-ink-muted">{name}</span>
      <span className="font-mono text-xs text-ink-subtle">Not available yet · {when}</span>
    </div>
  );
}
