# ADR-0012: Free-first defaults (no paid services required)

**Status:** Accepted (2026-11-17)

## Context
The founder has no budget for paid APIs or an Apple Developer ID right now and asked for the
cheapest workable path. The brief still requires adapters for OpenAI-compatible APIs, Anthropic,
Gemini and Ollama, and an honest "not configured" state for anything without credentials.

## Decision
- **Default model provider: Ollama** (local, free, no account). Default routes for chat, planning
  and memory extraction point at the local Ollama endpoint `http://127.0.0.1:11434`. Until Ollama is
  installed and a model is pulled, the provider shows "Not configured / unreachable" — never a fake
  reply.
- **Optional free cloud provider: Gemini** (Google AI Studio free tier). Its configuration links to
  Google's data-use terms; JARVIS does not claim anything about retention.
- **Anthropic and OpenAI-compatible adapters** are built and contract-tested with fixtures, and
  stay "Not configured" until a key is saved to the Keychain. The OpenAI-compatible adapter also
  serves other OpenAI-style endpoints (including local servers such as LM Studio).
- **Signing:** no Apple Developer ID. Builds are unsigned (ad-hoc signed by the toolchain); the
  README documents `xattr -dr com.apple.quarantine JARVIS.app`. Keychain items created by unsigned
  builds may prompt again after an update (ADR-0008).
- **CI:** the repository is public, so GitHub Actions (including macOS runners) costs nothing. The
  macOS job runs on pull requests and manual dispatch.
- **Voice (v0.3):** macOS built-in speech synthesis plus a local Whisper-class model as the free path.

## Consequences
- Contract-test fixtures are written from the providers' documented wire formats, not recorded
  from live traffic (no keys). This is stated in the tests and the status file; opt-in live smoke
  tests run only when a key or Ollama is present.
- Local models are slower and weaker than paid ones; quality depends on the founder's Mac (RAM).
