-- M3: model providers, per-task routing, conversations.

CREATE TABLE providers (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,                 -- anthropic | openai | gemini | ollama
    display_name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    key_optional INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    has_credential INTEGER NOT NULL DEFAULT 0,  -- the key itself lives only in the Keychain
    credential_hint TEXT,                       -- masked, e.g. ••••abcd
    retention_policy_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Ordered fallback chain per task kind: [{"provider_id": "...", "model": "..."}, ...]
CREATE TABLE model_routes (
    task TEXT PRIMARY KEY,              -- chat | planning | memory_extraction | vision | embeddings
    chain_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                 -- user | assistant
    content TEXT NOT NULL,
    status TEXT NOT NULL,               -- complete | streaming | interrupted | failed
    provider_id TEXT,
    model TEXT,
    error TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX messages_conversation ON messages(conversation_id, created_at);
