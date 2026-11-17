//! The per-launch secret shared with the backend. It never reaches the webview.

use std::fmt;

/// 256-bit random secret, hex encoded. Deliberately not `Serialize` and redacted in `Debug`.
#[derive(Clone, PartialEq, Eq)]
pub struct LaunchSecret(String);

impl LaunchSecret {
    pub fn generate() -> Result<Self, getrandom::Error> {
        let mut bytes = [0u8; 32];
        getrandom::fill(&mut bytes)?;
        Ok(Self(to_hex(&bytes)))
    }

    pub fn expose(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for LaunchSecret {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("LaunchSecret([REDACTED])")
    }
}

pub fn to_hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push(DIGITS[(b >> 4) as usize] as char);
        out.push(DIGITS[(b & 0x0f) as usize] as char);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn secret_is_64_lowercase_hex_and_unique() {
        let a = LaunchSecret::generate().unwrap();
        let b = LaunchSecret::generate().unwrap();
        assert_eq!(a.expose().len(), 64);
        assert!(a
            .expose()
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
        assert_ne!(a, b);
    }

    #[test]
    fn debug_output_is_redacted() {
        let s = LaunchSecret::generate().unwrap();
        let shown = format!("{s:?}");
        assert!(!shown.contains(s.expose()));
        assert!(shown.contains("REDACTED"));
    }
}
