//! Native confirmation for highest-risk approvals (BRIEF §4.11, ADR-0004).
//!
//! The webview can ask for a confirmation, but only this module can produce the token the
//! backend requires: it needs the launch secret, which never reaches the webview, and it is
//! computed only after the user clicks Approve in a native macOS dialog.

use hmac::{Hmac, Mac};
use serde_json::Value;
use sha2::Sha256;

use crate::error::BridgeError;
use crate::secret::{to_hex, LaunchSecret};

const LABEL: &[u8] = b"jarvis-native-confirm";

/// HMAC-SHA256(secret, label || 0 || approval_id || 0 || digest), hex. Mirrors
/// `jarvis.trust.approvals.native_confirmation_token`.
pub fn token(secret: &LaunchSecret, approval_id: &str, digest: &str) -> String {
    let mut mac = Hmac::<Sha256>::new_from_slice(secret.expose().as_bytes())
        .expect("HMAC accepts keys of any length");
    mac.update(LABEL);
    mac.update(b"\0");
    mac.update(approval_id.as_bytes());
    mac.update(b"\0");
    mac.update(digest.as_bytes());
    to_hex(&mac.finalize().into_bytes())
}

/// ULIDs as issued by the backend: 26 chars of Crockford base32.
pub fn is_approval_id(id: &str) -> bool {
    id.len() == 26
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || b.is_ascii_uppercase())
}

/// What the native dialog shows, taken from the backend's approval record.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DialogText {
    pub title: String,
    pub body: String,
}

pub fn dialog_text(approval: &Value) -> Result<DialogText, BridgeError> {
    let request = &approval["request"];
    let field = |name: &str| {
        request[name]
            .as_str()
            .unwrap_or("(not provided)")
            .to_owned()
    };
    if approval["highest_risk"] != Value::Bool(true) {
        return Err(BridgeError::new(
            "not_highest_risk",
            "this approval does not need native confirmation",
        ));
    }
    if approval["status"] != Value::String("pending".into()) {
        return Err(BridgeError::new(
            "approval_not_pending",
            "this approval is no longer pending",
        ));
    }
    let category = approval["category"]
        .as_str()
        .unwrap_or("consequential action");
    Ok(DialogText {
        title: format!("JARVIS wants to: {}", field("intent")),
        body: format!(
            "Category: {category}\nService: {}\nWhy: {}\nData affected: {}\nConsequences: {}\n\n\
             Approve only if you expect this. Nothing happens unless you choose Approve.",
            field("service"),
            field("why"),
            field("data_affected"),
            field("consequences"),
        ),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn fixed_secret() -> LaunchSecret {
        LaunchSecret::from_hex_for_tests(&"ab".repeat(32))
    }

    #[test]
    fn token_matches_the_python_backend() {
        // Vector from jarvis.trust.approvals.native_confirmation_token("ab"*32, id, "d"*64).
        assert_eq!(
            token(
                &fixed_secret(),
                "01JABCDEFGHJKMNPQRSTVWXYZ0",
                &"d".repeat(64)
            ),
            "74b1650e437714cd9187c58094703edda66ef51370c4b2e7386a4129d03cdc66"
        );
    }

    #[test]
    fn token_changes_with_id_digest_and_secret() {
        let base = token(&fixed_secret(), "A", "d");
        assert_ne!(base, token(&fixed_secret(), "B", "d"));
        assert_ne!(base, token(&fixed_secret(), "A", "e"));
        assert_ne!(base, token(&LaunchSecret::generate().unwrap(), "A", "d"));
    }

    #[test]
    fn approval_ids_are_validated() {
        assert!(is_approval_id("01JABCDEFGHJKMNPQRSTVWXYZ0"));
        assert!(!is_approval_id("01jabcdefghjkmnpqrstvwxyz0"));
        assert!(!is_approval_id("../../v1/settings/xxxxxxxxx"));
        assert!(!is_approval_id(""));
    }

    #[test]
    fn dialog_shows_what_why_service_data_and_consequences() {
        let approval = json!({
            "highest_risk": true, "status": "pending", "category": "send_message",
            "request": {"intent": "Send a message to Priya", "why": "You asked",
                        "service": "Messages", "data_affected": "One message",
                        "consequences": "Priya receives it"}
        });
        let text = dialog_text(&approval).unwrap();
        assert_eq!(text.title, "JARVIS wants to: Send a message to Priya");
        for part in [
            "send_message",
            "Messages",
            "You asked",
            "One message",
            "Priya receives it",
        ] {
            assert!(text.body.contains(part), "{part}");
        }
    }

    #[test]
    fn dialog_refuses_non_high_risk_or_decided_approvals() {
        let low = json!({"highest_risk": false, "status": "pending", "request": {}});
        assert_eq!(dialog_text(&low).unwrap_err().code, "not_highest_risk");
        let used = json!({"highest_risk": true, "status": "used", "request": {}});
        assert_eq!(dialog_text(&used).unwrap_err().code, "approval_not_pending");
    }
}
