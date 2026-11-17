# ADR-0006: Provider adapters without vendor SDKs

**Status:** Accepted (2026-11-17)

## Context
Brief §4.3: app code depends only on an internal interface; adapters for OpenAI-compatible,
Anthropic, Gemini, Ollama; contract tests against recorded fixtures incl. 429/5xx/timeout/malformed.

## Decision
- Internal types in `jarvis.providers.types`: `Message`, `ToolSpec`, `ToolCall`, `StreamDelta`,
  `Usage`, `ProviderError` (kinds: rate_limited, server, timeout, malformed, auth, unavailable).
- Each adapter speaks its REST/SSE API directly with `httpx` (async, explicit timeouts). No
  vendor SDKs: fewer dependencies, uniform error mapping, and fixtures are plain HTTP recordings
  replayed through `httpx.MockTransport`.
- Registry + router: per-task routes (chat, planning, memory_extraction, vision, embeddings) with
  ordered fallback; every fallback is audited.

## Consequences
- We maintain wire-format code for four APIs; contract tests catch drift. Live smoke tests are
  opt-in (`JARVIS_LIVE_SMOKE=1`) and need real keys.
