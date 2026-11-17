// The seven product screens (BRIEF §9) plus Preferences. Each lists what it will hold and
// the milestone that brings it, so "Not available yet" states are specific and honest.

export type ScreenId =
  | "command"
  | "activity"
  | "memory"
  | "skills"
  | "providers"
  | "security"
  | "history"
  | "preferences";

export interface PlannedPart {
  name: string;
  release: "v0.1" | "v0.2" | "v0.3";
  milestone: string;
}

export interface ScreenDef {
  id: ScreenId;
  title: string;
  summary: string;
  planned: PlannedPart[];
}

export const SCREENS: readonly ScreenDef[] = [
  {
    id: "command",
    title: "Command Center",
    summary: "State an intention, follow the conversation and the current task, stop it anytime.",
    planned: [
      { name: "Streaming text conversation with stop control", release: "v0.1", milestone: "M3" },
      { name: "Voice input and barge-in", release: "v0.3", milestone: "M10" },
    ],
  },
  {
    id: "activity",
    title: "Activity Center",
    summary: "Running and background tasks, pending approvals, and items that need your review.",
    planned: [{ name: "Background tasks with progress", release: "v0.2", milestone: "M7" }],
  },
  {
    id: "memory",
    title: "Memory Center",
    summary: "What JARVIS remembers, where it came from, and the proposals waiting for you.",
    planned: [
      { name: "History and memories with provenance", release: "v0.1", milestone: "M4" },
      { name: "Proposal review queue", release: "v0.1", milestone: "M4" },
    ],
  },
  {
    id: "skills",
    title: "Skills Center",
    summary:
      "What JARVIS can do on this Mac, the permissions each skill needs, and when it arrives.",
    planned: [
      { name: "Files", release: "v0.1", milestone: "M5" },
      { name: "Terminal", release: "v0.2", milestone: "M6" },
      { name: "Browser", release: "v0.3", milestone: "M8" },
      { name: "Desktop observation", release: "v0.3", milestone: "M9" },
    ],
  },
  {
    id: "providers",
    title: "Provider Settings",
    summary: "Model and voice providers, credentials in the Keychain, health and routing.",
    planned: [
      { name: "Model providers, keys and routing", release: "v0.1", milestone: "M3" },
      { name: "Voice providers", release: "v0.3", milestone: "M10" },
      { name: "Per-provider screen-content opt-in", release: "v0.3", milestone: "M9" },
    ],
  },
  {
    id: "security",
    title: "Security Center",
    summary: "Directory access, approvals, terminal policy, OS permissions and the audit log.",
    planned: [
      { name: "Terminal policy and allowlist", release: "v0.2", milestone: "M6" },
      { name: "Screen and microphone permissions", release: "v0.3", milestone: "M9" },
    ],
  },
  {
    id: "history",
    title: "Task History",
    summary: "Every task's timeline and execution receipt, with the evidence behind its status.",
    planned: [{ name: "Multi-step task timelines", release: "v0.2", milestone: "M7" }],
  },
  {
    id: "preferences",
    title: "Preferences",
    summary: "Appearance settings, stored by the JARVIS core.",
    planned: [],
  },
];

export function screenById(id: ScreenId): ScreenDef {
  const found = SCREENS.find((s) => s.id === id);
  if (!found) throw new Error(`unknown screen ${id}`);
  return found;
}
