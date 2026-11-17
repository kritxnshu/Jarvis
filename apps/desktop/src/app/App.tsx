import { useCallback, useEffect, useRef, useState } from "react";

import { NotAvailable } from "../components/NotAvailable";
import { Nav } from "../components/Nav";
import { StatusBar } from "../components/StatusBar";
import { ActivityCenter } from "../screens/ActivityCenter";
import { CommandCenter } from "../screens/CommandCenter";
import { ProviderSettings } from "../screens/ProviderSettings";
import { Preferences } from "../screens/Preferences";
import { SecurityCenter } from "../screens/SecurityCenter";
import { TaskHistory } from "../screens/TaskHistory";
import { screenById, type ScreenId } from "../screens/registry";
import type { BridgeEvent } from "../bridge/types";
import { EventHub, EventHubProvider } from "./EventHub";
import {
  settingValue,
  useBackendEvents,
  useBackendStatus,
  useHealth,
  useSettings,
} from "./useBackend";

/** Screens with working content; the rest show their "Not available yet" plan. */
const BUILT_SCREENS: ReadonlySet<ScreenId> = new Set([
  "command",
  "providers",
  "preferences",
  "activity",
  "security",
  "history",
]);

export function App() {
  const [screenId, setScreenId] = useState<ScreenId>("command");
  const status = useBackendStatus();
  const ready = status.state === "ready";
  const health = useHealth(ready);
  const { settings, save, applyRemoteChange } = useSettings(ready);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const [hub] = useState(() => new EventHub());
  const onEvent = useCallback(
    (event: BridgeEvent) => {
      hub.emit(event);
      if (event.type === "settings.changed" && typeof event.payload?.key === "string") {
        applyRemoteChange(event.payload.key, event.payload.value);
      }
    },
    [applyRemoteChange, hub],
  );
  useBackendEvents(ready, onEvent);

  const reducedMotion = settingValue(settings, "appearance.reduced_motion", "system");
  useEffect(() => {
    document.documentElement.dataset.reducedMotion = reducedMotion;
  }, [reducedMotion]);

  const select = (id: ScreenId) => {
    setScreenId(id);
    // Move focus to the new screen's heading for keyboard and screen-reader users.
    requestAnimationFrame(() => headingRef.current?.focus());
  };

  const screen = screenById(screenId);
  const showStatusBar = settingValue<boolean>(settings, "appearance.show_status_bar", true);

  return (
    <EventHubProvider hub={hub}>
      <div className="flex h-screen flex-col bg-canvas text-ink">
        <div className="flex min-h-0 flex-1">
          <Nav current={screenId} onSelect={select} />
          <main
            className="min-w-0 flex-1 overflow-y-auto px-10 py-8"
            aria-labelledby="screen-title"
          >
            <h1
              id="screen-title"
              ref={headingRef}
              tabIndex={-1}
              className="text-2xl font-semibold tracking-tight text-ink"
            >
              {screen.title}
            </h1>
            <p className="mt-2 max-w-prose text-sm text-ink-muted">{screen.summary}</p>
            <div className="mt-8">
              {screenId === "preferences" && <Preferences settings={settings} save={save} />}
              {screenId === "command" && <CommandCenter ready={ready} />}
              {screenId === "providers" && <ProviderSettings ready={ready} />}
              {screenId === "activity" && <ActivityCenter ready={ready} />}
              {screenId === "security" && <SecurityCenter ready={ready} />}
              {screenId === "history" && <TaskHistory ready={ready} />}
              {!BUILT_SCREENS.has(screenId) && <NotAvailable parts={screen.planned} />}
            </div>
          </main>
        </div>
        {showStatusBar && <StatusBar status={status} health={health} />}
      </div>
    </EventHubProvider>
  );
}
