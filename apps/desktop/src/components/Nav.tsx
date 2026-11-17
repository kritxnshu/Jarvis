import { SCREENS, type ScreenId } from "../screens/registry";

export function Nav({
  current,
  onSelect,
}: {
  current: ScreenId;
  onSelect: (id: ScreenId) => void;
}) {
  const primary = SCREENS.filter((s) => s.id !== "preferences");
  const renderItem = (id: ScreenId, title: string) => (
    <li key={id}>
      <button
        type="button"
        aria-current={current === id ? "page" : undefined}
        onClick={() => {
          onSelect(id);
        }}
        className={`motion-base w-full rounded-md px-3 py-2 text-left text-sm ${
          current === id
            ? "bg-surface-raised text-ink"
            : "text-ink-muted hover:bg-surface-raised/60 hover:text-ink"
        }`}
      >
        {title}
      </button>
    </li>
  );
  return (
    <nav
      aria-label="Screens"
      className="flex w-56 shrink-0 flex-col border-r border-line bg-surface px-3 py-4"
    >
      <div className="mb-6 px-3">
        <span className="text-sm font-semibold tracking-[0.2em] text-ink">JARVIS</span>
      </div>
      <ul className="flex flex-col gap-1">{primary.map((s) => renderItem(s.id, s.title))}</ul>
      <ul className="mt-auto flex flex-col gap-1 border-t border-line pt-3">
        {renderItem("preferences", "Preferences")}
      </ul>
    </nav>
  );
}
