# JARVIS

A personal AI operating system for macOS: state an intention, and JARVIS understands it, plans,
uses tools (files, terminal, browser, screen), verifies the result, and reports back with evidence.

    intention → understanding → planning → execution → verification → result

Built on three principles: an honest "not verified" beats a false "done"; the model proposes and
deterministic code decides; everything leaves a record.

## Status

**Nothing is usable yet.** Milestone 0 (assessment and plan) is complete; there is no application
code. See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for exact status and
[ROADMAP.md](ROADMAP.md) for what comes next.

| Release | Contents | State |
|---|---|---|
| v0.1 Trusted core | app, approvals, audit, receipts, recovery, text chat, providers, memory, files | Not started |
| v0.2 Tasks and terminal | controlled terminal, multi-step planning, background tasks | Not started |
| v0.3 Browser, screen and voice | browser automation, desktop observation, voice | Not started |

## Docs

- [docs/BRIEF.md](docs/BRIEF.md) — full requirements and acceptance tests
- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [SECURITY.md](SECURITY.md)
- [DEVELOPMENT.md](DEVELOPMENT.md) — setup and commands
- [docs/api.md](docs/api.md) · [docs/database.md](docs/database.md) · [docs/adr/](docs/adr/)
