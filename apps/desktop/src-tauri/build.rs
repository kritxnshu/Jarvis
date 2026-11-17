fn main() {
    // Declaring the app's commands makes Tauri require an explicit capability grant for
    // each one: the webview can call nothing that capabilities/main.json does not list.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "backend_status",
            "backend_request",
            "subscribe_events",
            "confirm_high_risk_approval",
            "save_audit_export",
        ]),
    ))
    .expect("failed to run tauri-build");
}
