//! The only backend routes the webview may reach through `backend_request`.
//! Anything not matched here is refused before a byte is sent to the backend.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Method {
    Get,
    Put,
    Post,
}

impl Method {
    pub fn as_str(self) -> &'static str {
        match self {
            Method::Get => "GET",
            Method::Put => "PUT",
            Method::Post => "POST",
        }
    }
}

const MAX_PATH_LEN: usize = 256;
const MAX_KEY_LEN: usize = 128;

/// Returns the method to use if `(method, path)` is on the allowlist.
pub fn check(method: &str, path: &str) -> Option<Method> {
    if path.len() > MAX_PATH_LEN || !is_plain_path(path) {
        return None;
    }
    let segments: Vec<&str> = path.split('/').collect();
    use Method::{Get, Post, Put};
    let route = match (method, segments.as_slice()) {
        ("GET", ["", "v1", "health"]) => Get,
        ("GET", ["", "v1", "settings"]) => Get,
        ("PUT", ["", "v1", "settings", key]) if is_setting_key(key) => Put,
        ("GET", ["", "v1", "tasks"]) => Get,
        ("GET", ["", "v1", "tasks", id]) if is_id(id) => Get,
        ("POST", ["", "v1", "tasks", id, "review"]) if is_id(id) => Post,
        ("GET", ["", "v1", "approvals"]) => Get,
        ("GET", ["", "v1", "approvals", id]) if is_id(id) => Get,
        // Native confirmations are added only by `confirm_high_risk_approval`; the generic
        // command refuses bodies that carry one (see `body_is_allowed`).
        ("POST", ["", "v1", "approvals", id, "decision"]) if is_id(id) => Post,
        ("POST", ["", "v1", "audit", "search"]) => Post,
        ("GET", ["", "v1", "audit", "verify"]) => Get,
        ("GET", ["", "v1", "grants"]) => Get,
        ("POST", ["", "v1", "grants"]) => Post,
        ("POST", ["", "v1", "grants", id, "revoke"]) if is_id(id) => Post,
        ("GET", ["", "v1", "providers"]) => Get,
        ("PUT", ["", "v1", "providers", p]) if is_name(p) => Put,
        ("PUT", ["", "v1", "providers", p, "credential"]) if is_name(p) => Put,
        ("POST", ["", "v1", "providers", p, "credential", "delete"]) if is_name(p) => Post,
        ("POST", ["", "v1", "providers", p, "check"]) if is_name(p) => Post,
        ("PUT", ["", "v1", "routes", task]) if ROUTE_TASKS.contains(task) => Put,
        ("GET", ["", "v1", "conversations"]) => Get,
        ("POST", ["", "v1", "conversations"]) => Post,
        ("GET", ["", "v1", "conversations", id, "messages"]) if is_id(id) => Get,
        ("POST", ["", "v1", "conversations", id, "messages"]) if is_id(id) => Post,
        ("POST", ["", "v1", "messages", id, "stop"]) if is_id(id) => Post,
        _ => return None,
    };
    Some(route)
}

/// The generic bridge never forwards a native confirmation token.
pub fn body_is_allowed(body: Option<&serde_json::Value>) -> bool {
    match body {
        Some(serde_json::Value::Object(map)) => !map.contains_key("native_confirmation"),
        _ => true,
    }
}

const ROUTE_TASKS: [&str; 5] = [
    "chat",
    "planning",
    "memory_extraction",
    "vision",
    "embeddings",
];

/// Provider ids: short lowercase names such as `ollama`.
fn is_name(segment: &str) -> bool {
    (1..=32).contains(&segment.len())
        && segment
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
}

/// Backend identifiers: 26-character ULIDs (Crockford base32, uppercase).
fn is_id(segment: &str) -> bool {
    segment.len() == 26
        && segment
            .bytes()
            .all(|b| b.is_ascii_digit() || b.is_ascii_uppercase())
}

/// Only `[A-Za-z0-9_./]`: no query strings, fragments, percent-encoding or traversal.
fn is_plain_path(path: &str) -> bool {
    path.starts_with('/')
        && !path.contains("//")
        && !path.contains("..")
        && path
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b'/'))
}

fn is_setting_key(key: &str) -> bool {
    !key.is_empty()
        && key.len() <= MAX_KEY_LEN
        && key.split('.').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|b| matches!(b, b'a'..=b'z' | b'0'..=b'9' | b'_'))
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    const ID: &str = "01JABCDEFGHJKMNPQRSTVWXYZ0";

    #[test]
    fn trust_kernel_routes() {
        assert_eq!(check("GET", "/v1/tasks"), Some(Method::Get));
        assert_eq!(check("GET", &format!("/v1/tasks/{ID}")), Some(Method::Get));
        assert_eq!(
            check("POST", &format!("/v1/tasks/{ID}/review")),
            Some(Method::Post)
        );
        assert_eq!(
            check("POST", &format!("/v1/approvals/{ID}/decision")),
            Some(Method::Post)
        );
        assert_eq!(check("POST", "/v1/audit/search"), Some(Method::Post));
        assert_eq!(check("GET", "/v1/audit/verify"), Some(Method::Get));
        assert_eq!(
            check("POST", &format!("/v1/grants/{ID}/revoke")),
            Some(Method::Post)
        );
        for (m, p) in [
            ("POST", "/v1/tasks".to_owned()), // the UI does not start tool runs (yet)
            ("POST", "/v1/approvals".to_owned()),
            ("GET", "/v1/audit/export/json".to_owned()), // only via save_audit_export
            ("GET", "/v1/tasks/not-an-id".to_owned()),
            ("GET", format!("/v1/tasks/{}", ID.to_lowercase())),
            ("POST", format!("/v1/approvals/{ID}/decision/x")),
        ] {
            assert_eq!(check(m, &p), None, "{m} {p} should be refused");
        }
    }

    #[test]
    fn conversation_and_provider_routes() {
        for (m, p) in [
            ("GET", "/v1/providers".to_owned()),
            ("PUT", "/v1/providers/ollama".to_owned()),
            ("PUT", "/v1/providers/anthropic/credential".to_owned()),
            (
                "POST",
                "/v1/providers/anthropic/credential/delete".to_owned(),
            ),
            ("POST", "/v1/providers/gemini/check".to_owned()),
            ("PUT", "/v1/routes/chat".to_owned()),
            ("GET", "/v1/conversations".to_owned()),
            ("POST", "/v1/conversations".to_owned()),
            ("GET", format!("/v1/conversations/{ID}/messages")),
            ("POST", format!("/v1/conversations/{ID}/messages")),
            ("POST", format!("/v1/messages/{ID}/stop")),
        ] {
            assert!(check(m, &p).is_some(), "{m} {p} should be allowed");
        }
        for (m, p) in [
            ("PUT", "/v1/routes/anything"),
            ("PUT", "/v1/providers/Ollama"),
            ("GET", "/v1/providers/ollama/credential"), // keys are never read back
            ("POST", "/v1/messages/not-an-id/stop"),
        ] {
            assert_eq!(check(m, p), None, "{m} {p} should be refused");
        }
    }

    #[test]
    fn native_confirmation_never_passes_the_generic_bridge() {
        use serde_json::json;
        assert!(body_is_allowed(Some(&json!({"approve": true}))));
        assert!(body_is_allowed(None));
        assert!(!body_is_allowed(Some(
            &json!({"approve": true, "native_confirmation": "x"})
        )));
    }

    #[test]
    fn allowed_routes() {
        assert_eq!(check("GET", "/v1/health"), Some(Method::Get));
        assert_eq!(check("GET", "/v1/settings"), Some(Method::Get));
        assert_eq!(
            check("PUT", "/v1/settings/appearance.reduced_motion"),
            Some(Method::Put)
        );
    }

    #[test]
    fn refused_routes() {
        for (m, p) in [
            ("GET", "/v1/events"), // streaming goes through subscribe_events only
            ("POST", "/v1/settings"),
            ("DELETE", "/v1/settings/appearance.reduced_motion"),
            ("PUT", "/v1/settings"),
            ("GET", "/v1/health?x=1"),
            ("GET", "/v1/health#x"),
            ("GET", "/v1//health"),
            ("GET", "/v1/../v1/health"),
            ("GET", "/v1/%68ealth"),
            ("GET", "v1/health"),
            ("GET", "/V1/HEALTH"),
            ("GET", "/v1/Health"),
            ("PUT", "/v1/settings/a..b"),
            ("PUT", "/v1/settings/.a"),
            ("PUT", "/v1/settings/a/b"),
            ("DELETE", "/v1/approvals"),
            ("get", "/v1/health"),
            ("GET", ""),
        ] {
            assert_eq!(check(m, p), None, "{m} {p} should be refused");
        }
        let long_key = format!("/v1/settings/{}", "a".repeat(MAX_KEY_LEN + 1));
        assert_eq!(check("PUT", &long_key), None);
    }
}
