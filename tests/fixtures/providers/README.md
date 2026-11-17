# Provider contract fixtures

Streaming responses for each adapter, written from each provider's documented wire format
(not recorded from live traffic: no API keys were available — ADR-0012). Every adapter must turn
`*_text` into the text "Hello, Priya." and `*_tool` into one `get_weather({"city": "Paris"})` call.
Opt-in live smoke tests (`JARVIS_LIVE_SMOKE=1`) check the formats against the real services.
