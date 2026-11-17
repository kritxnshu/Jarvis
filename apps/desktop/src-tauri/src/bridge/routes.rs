//! The only backend routes the webview may reach through `backend_request`.
//! Anything not matched here is refused before a byte is sent to the backend.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Method {
    Get,
    Put,
}

impl Method {
    pub fn as_str(self) -> &'static str {
        match self {
            Method::Get => "GET",
            Method::Put => "PUT",
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
    match (method, segments.as_slice()) {
        ("GET", ["", "v1", "health"]) => Some(Method::Get),
        ("GET", ["", "v1", "settings"]) => Some(Method::Get),
        ("PUT", ["", "v1", "settings", key]) if is_setting_key(key) => Some(Method::Put),
        _ => None,
    }
}

/// Only `[a-z0-9_./]`: no query strings, fragments, percent-encoding or traversal.
fn is_plain_path(path: &str) -> bool {
    path.starts_with('/')
        && !path.contains("//")
        && !path.contains("..")
        && path
            .bytes()
            .all(|b| matches!(b, b'a'..=b'z' | b'0'..=b'9' | b'_' | b'.' | b'/'))
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
            ("PUT", "/v1/settings/a..b"),
            ("PUT", "/v1/settings/.a"),
            ("PUT", "/v1/settings/a/b"),
            ("GET", "/v1/approvals"),
            ("get", "/v1/health"),
            ("GET", ""),
        ] {
            assert_eq!(check(m, p), None, "{m} {p} should be refused");
        }
        let long_key = format!("/v1/settings/{}", "a".repeat(MAX_KEY_LEN + 1));
        assert_eq!(check("PUT", &long_key), None);
    }
}
