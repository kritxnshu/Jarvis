//! JARVIS desktop shell: window, backend sidecar lifecycle, and the webview ↔ backend bridge.

pub mod bridge;
mod commands;
pub mod error;
pub mod native_confirm;
pub mod rundir;
pub mod secret;
pub mod sidecar;
pub mod state;

use std::path::{Path, PathBuf};
use std::time::Duration;

use tauri::{AppHandle, Manager, RunEvent};

use crate::bridge::client::UdsClient;
use crate::secret::LaunchSecret;
use crate::sidecar::SidecarCommand;
use crate::state::{AppState, BackendStatus, UdsClientHandle};

const READY_TIMEOUT: Duration = Duration::from_secs(30);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(15);
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);

fn resolve_sidecar(app: &AppHandle) -> Option<SidecarCommand> {
    if let Some(cmd) = app
        .path()
        .resource_dir()
        .ok()
        .and_then(|dir| SidecarCommand::bundled(&dir))
    {
        return Some(cmd);
    }
    if cfg!(debug_assertions) {
        // src-tauri → desktop → apps → repository root
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
        return SidecarCommand::development(&repo.canonicalize().unwrap_or(repo));
    }
    None
}

async fn start_backend(app: AppHandle) {
    let state = app.state::<AppState>();
    let outcome = async {
        let data_dir: PathBuf = app
            .path()
            .app_data_dir()
            .map_err(|e| format!("no app data directory: {e}"))?;
        std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&data_dir, std::fs::Permissions::from_mode(0o700))
                .map_err(|e| e.to_string())?;
        }
        let cmd = resolve_sidecar(&app).ok_or("backend executable not found in this build")?;
        let run_dir = rundir::create(&data_dir).map_err(|e| e.to_string())?;
        let secret = LaunchSecret::generate().map_err(|e| e.to_string())?;
        let sidecar = sidecar::launch(&cmd, &secret, &run_dir, &data_dir, READY_TIMEOUT)
            .await
            .map_err(|e| e.to_string())?;
        *state.sidecar.lock().await = Some(sidecar);
        Ok::<_, String>(UdsClient::new(run_dir.socket_path, secret, REQUEST_TIMEOUT))
    }
    .await;
    match outcome {
        Ok(client) => state.set(BackendStatus::Ready(UdsClientHandle(client))),
        Err(why) => state.set(BackendStatus::Failed(why)),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .manage(AppState::default())
        .setup(|app| {
            tauri::async_runtime::spawn(start_backend(app.handle().clone()));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::backend_status,
            commands::backend_request,
            commands::subscribe_events,
            commands::confirm_high_risk_approval,
            commands::save_audit_export,
        ])
        .build(tauri::generate_context!())
        .expect("failed to build the JARVIS application");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            let state = handle.state::<AppState>();
            state.set(BackendStatus::Stopped);
            tauri::async_runtime::block_on(async {
                if let Some(sidecar) = state.sidecar.lock().await.take() {
                    let _ = sidecar.shutdown(SHUTDOWN_GRACE).await;
                }
            });
        }
    });
}
