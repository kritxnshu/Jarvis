//! Backend lifecycle state shared by the Tauri commands.

use std::time::Duration;

use serde::Serialize;
use tokio::sync::{watch, Mutex};

use crate::bridge::client::UdsClient;
use crate::error::BridgeError;
use crate::sidecar::Sidecar;

#[derive(Debug, Clone, PartialEq)]
pub enum BackendStatus {
    Starting,
    Ready(UdsClientHandle),
    Failed(String),
    Stopped,
}

/// Wrapper so status comparisons don't need `PartialEq` on the client.
#[derive(Debug, Clone)]
pub struct UdsClientHandle(pub UdsClient);

impl PartialEq for UdsClientHandle {
    fn eq(&self, _other: &Self) -> bool {
        true
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct StatusView {
    pub state: &'static str,
    pub detail: Option<String>,
}

pub struct AppState {
    status: watch::Sender<BackendStatus>,
    pub sidecar: Mutex<Option<Sidecar>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            status: watch::Sender::new(BackendStatus::Starting),
            sidecar: Mutex::new(None),
        }
    }
}

impl AppState {
    pub fn set(&self, status: BackendStatus) {
        self.status.send_replace(status);
    }

    pub fn view(&self) -> StatusView {
        match &*self.status.borrow() {
            BackendStatus::Starting => StatusView {
                state: "starting",
                detail: None,
            },
            BackendStatus::Ready(_) => StatusView {
                state: "ready",
                detail: None,
            },
            BackendStatus::Failed(why) => StatusView {
                state: "failed",
                detail: Some(why.clone()),
            },
            BackendStatus::Stopped => StatusView {
                state: "stopped",
                detail: None,
            },
        }
    }

    /// Waits (bounded) for the backend to become ready and returns its client.
    pub async fn client(&self, wait: Duration) -> Result<UdsClient, BridgeError> {
        let mut rx = self.status.subscribe();
        let outcome = tokio::time::timeout(wait, async {
            loop {
                match &*rx.borrow_and_update() {
                    BackendStatus::Ready(c) => return Ok(c.0.clone()),
                    BackendStatus::Failed(why) => {
                        return Err(BridgeError::new("backend_failed", why.clone()))
                    }
                    BackendStatus::Stopped => {
                        return Err(BridgeError::new("backend_stopped", "backend has stopped"))
                    }
                    BackendStatus::Starting => {}
                }
                if rx.changed().await.is_err() {
                    return Err(BridgeError::new("backend_stopped", "backend state closed"));
                }
            }
        })
        .await;
        outcome.unwrap_or_else(|_| {
            Err(BridgeError::new(
                "backend_not_ready",
                "backend is still starting",
            ))
        })
    }
}
