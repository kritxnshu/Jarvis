//! The complete set of commands the webview can invoke (see capabilities/main.json).

use std::time::Duration;

use serde_json::{json, Value};
use tauri::ipc::Channel;
use tauri::State;

use crate::bridge::client::BackendResponse;
use crate::bridge::routes;
use crate::error::BridgeError;
use crate::state::{AppState, StatusView};

const READY_WAIT: Duration = Duration::from_secs(20);

#[tauri::command]
pub fn backend_status(state: State<'_, AppState>) -> StatusView {
    state.view()
}

#[tauri::command]
pub async fn backend_request(
    state: State<'_, AppState>,
    method: String,
    path: String,
    body: Option<Value>,
) -> Result<BackendResponse, BridgeError> {
    let Some(allowed) = routes::check(&method, &path) else {
        return Err(BridgeError::new(
            "route_not_allowed",
            format!("{method} {path} is not an allowed backend route"),
        ));
    };
    let client = state.client(READY_WAIT).await?;
    client.request_json(allowed, &path, body.as_ref()).await
}

/// Relays backend events to the webview until either side goes away. A bridge-generated
/// `bridge.stream_closed` event tells the UI to resubscribe.
#[tauri::command]
pub async fn subscribe_events(
    state: State<'_, AppState>,
    on_event: Channel<Value>,
) -> Result<(), BridgeError> {
    let client = state.client(READY_WAIT).await?;
    tauri::async_runtime::spawn(async move {
        let result = client
            .stream_events(|event| on_event.send(event).is_ok())
            .await;
        let reason = match result {
            Ok(()) => "ended".to_owned(),
            Err(e) => e.code,
        };
        let _ = on_event.send(json!({
            "type": "bridge.stream_closed",
            "payload": { "reason": reason },
        }));
    });
    Ok(())
}
