//! The complete set of commands the webview can invoke (see capabilities/main.json).

use std::time::Duration;

use serde_json::{json, Value};
use tauri::ipc::Channel;
use tauri::State;

use crate::bridge::client::BackendResponse;
use crate::bridge::routes::{self, Method};
use crate::error::BridgeError;
use crate::native_confirm;
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
    if !routes::body_is_allowed(body.as_ref()) {
        return Err(BridgeError::new(
            "native_confirmation_forbidden",
            "native confirmations can only come from the native dialog",
        ));
    }
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

/// Runs `f` on the main thread (macOS requires it for native dialogs) and awaits its result.
async fn on_main_thread<T, F>(app: &tauri::AppHandle, f: F) -> Result<T, BridgeError>
where
    T: Send + 'static,
    F: FnOnce() -> T + Send + 'static,
{
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.run_on_main_thread(move || {
        let _ = tx.send(f());
    })
    .map_err(|e| BridgeError::new("dialog_failed", e.to_string()))?;
    rx.await
        .map_err(|_| BridgeError::new("dialog_failed", "dialog closed unexpectedly"))
}

/// Highest-risk approvals: show a native dialog, and only if the user approves there,
/// send the decision with the native confirmation token (ADR-0004).
#[tauri::command]
pub async fn confirm_high_risk_approval(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    approval_id: String,
) -> Result<BackendResponse, BridgeError> {
    if !native_confirm::is_approval_id(&approval_id) {
        return Err(BridgeError::new("bad_request", "not an approval id"));
    }
    let client = state.client(READY_WAIT).await?;
    let path = format!("/v1/approvals/{approval_id}");
    let approval = client.request_json(Method::Get, &path, None).await?;
    if approval.status != 200 {
        return Ok(approval);
    }
    let text = native_confirm::dialog_text(&approval.body)?;
    let digest = approval.body["digest"]
        .as_str()
        .unwrap_or_default()
        .to_owned();
    let approved = on_main_thread(&app, move || {
        rfd::MessageDialog::new()
            .set_level(rfd::MessageLevel::Warning)
            .set_title(&text.title)
            .set_description(&text.body)
            .set_buttons(rfd::MessageButtons::OkCancelCustom(
                "Approve".into(),
                "Cancel".into(),
            ))
            .show()
    })
    .await?;
    let confirmed = matches!(approved, rfd::MessageDialogResult::Ok)
        || matches!(&approved, rfd::MessageDialogResult::Custom(label) if label == "Approve");
    if !confirmed {
        return Err(BridgeError::new(
            "native_dialog_cancelled",
            "not approved in the native dialog; the request is still pending",
        ));
    }
    let token = native_confirm::token(client.secret(), &approval_id, &digest);
    client
        .request_json(
            Method::Post,
            &format!("{path}/decision"),
            Some(&json!({"approve": true, "native_confirmation": token})),
        )
        .await
}

/// Exports the audit log through a native save dialog; the webview never writes files.
#[tauri::command]
pub async fn save_audit_export(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    format: String,
) -> Result<Value, BridgeError> {
    if format != "json" && format != "csv" {
        return Err(BridgeError::new(
            "bad_request",
            "format must be json or csv",
        ));
    }
    let client = state.client(READY_WAIT).await?;
    let export = client
        .request_json(Method::Get, &format!("/v1/audit/export/{format}"), None)
        .await?;
    let Some(content) = export.body["content"].as_str().map(str::to_owned) else {
        return Err(BridgeError::new(
            "backend_malformed",
            "export had no content",
        ));
    };
    let file_name = format!("jarvis-audit.{format}");
    let target = on_main_thread(&app, move || {
        rfd::FileDialog::new().set_file_name(&file_name).save_file()
    })
    .await?;
    let Some(target) = target else {
        return Ok(json!({"saved": null}));
    };
    std::fs::write(&target, content)
        .map_err(|e| BridgeError::new("write_failed", e.to_string()))?;
    Ok(json!({"saved": target.display().to_string()}))
}
