# JARVIS

A personal AI operating system for macOS: state an intention, and JARVIS understands it, plans,
uses tools (files, terminal, browser, screen), verifies the result, and reports back with evidence.

    intention → understanding → planning → execution → verification → result

Built on three principles: an honest "not verified" beats a false "done"; the model proposes and
deterministic code decides; everything leaves a record.

## Status

**Working now:** streaming text chat with Stop (free local models via Ollama by default; Gemini,
Anthropic or OpenAI-compatible with your own key, stored in the macOS Keychain), approvals with a
native confirmation for the riskiest actions, crash-safe execution with receipts, and a
tamper-evident audit log. Memory and file management come next.

The app is unsigned (no Apple Developer ID yet). After unzipping it, run once:
`xattr -dr com.apple.quarantine JARVIS.app`. See
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for exact status and evidence.

Try it from source: `uv sync --all-groups && pnpm install && pnpm --filter @jarvis/desktop dev`.

| Release | Contents | State |
|---|---|---|
| v0.1 Trusted core | app, approvals, audit, receipts, recovery, text chat, providers, memory, files | In progress (M1–M3 of M1–M5 done) |
| v0.2 Tasks and terminal | controlled terminal, multi-step planning, background tasks | Not started |
| v0.3 Browser, screen and voice | browser automation, desktop observation, voice | Not started |

## Docs

- [docs/BRIEF.md](docs/BRIEF.md) — full requirements and acceptance tests
- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [SECURITY.md](SECURITY.md)
- [DEVELOPMENT.md](DEVELOPMENT.md) — setup and commands
- [docs/api.md](docs/api.md) · [docs/database.md](docs/database.md) · [docs/adr/](docs/adr/)
