//! End to end through the real launch path: Rust generates the secret, spawns the Python
//! backend from the repository's virtualenv, performs the stdin handshake, and talks HTTP over
//! the Unix socket. This is the UI → Rust → backend path minus the webview.

use std::path::{Path, PathBuf};
use std::time::Duration;

use jarvis_desktop_lib::bridge::client::UdsClient;
use jarvis_desktop_lib::bridge::routes::Method;
use jarvis_desktop_lib::rundir;
use jarvis_desktop_lib::secret::LaunchSecret;
use jarvis_desktop_lib::sidecar::{self, Sidecar, SidecarCommand};
use serde_json::json;

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .unwrap()
}

async fn start(data_dir: &Path) -> (Sidecar, UdsClient, LaunchSecret, PathBuf) {
    let cmd = SidecarCommand::development(&repo_root())
        .expect("repository .venv missing: run `uv sync` at the repository root");
    let run = rundir::create(data_dir).unwrap();
    let secret = LaunchSecret::generate().unwrap();
    let sidecar = sidecar::launch(&cmd, &secret, &run, data_dir, Duration::from_secs(30))
        .await
        .expect("backend should start");
    let client = UdsClient::new(
        run.socket_path.clone(),
        secret.clone(),
        Duration::from_secs(10),
    );
    (sidecar, client, secret, run.socket_path)
}

#[tokio::test]
async fn health_and_settings_round_trip_and_survive_restart() {
    let tmp = tempfile::tempdir().unwrap();
    let data = tmp.path().join("data");
    std::fs::create_dir_all(&data).unwrap();

    let (sidecar, client, _secret, _sock) = start(&data).await;
    let health = client
        .request_json(Method::Get, "/v1/health", None)
        .await
        .unwrap();
    assert_eq!(health.status, 200);
    assert_eq!(health.body["status"], "ok");

    let put = client
        .request_json(
            Method::Put,
            "/v1/settings/appearance.reduced_motion",
            Some(&json!({"value": "on"})),
        )
        .await
        .unwrap();
    assert_eq!(put.status, 200, "{:?}", put.body);
    let status = sidecar.shutdown(Duration::from_secs(5)).await.unwrap();
    assert!(status.success(), "backend exit status {status:?}");

    let (sidecar, client, _secret, _sock) = start(&data).await;
    let listed = client
        .request_json(Method::Get, "/v1/settings", None)
        .await
        .unwrap();
    let settings = listed.body["settings"].as_array().unwrap();
    let motion = settings
        .iter()
        .find(|s| s["key"] == "appearance.reduced_motion")
        .unwrap();
    assert_eq!(motion["value"], "on");
    sidecar.shutdown(Duration::from_secs(5)).await;
}

#[tokio::test]
async fn wrong_secret_is_rejected() {
    let tmp = tempfile::tempdir().unwrap();
    let (sidecar, _client, _secret, sock) = start(tmp.path()).await;
    let imposter = UdsClient::new(
        sock,
        LaunchSecret::generate().unwrap(),
        Duration::from_secs(5),
    );
    let resp = imposter
        .request_json(Method::Get, "/v1/health", None)
        .await
        .unwrap();
    assert_eq!(resp.status, 401);
    assert_eq!(resp.body["error"]["code"], "unauthorized");
    sidecar.shutdown(Duration::from_secs(5)).await;
}

#[cfg(target_os = "linux")]
#[tokio::test]
async fn secret_is_not_in_backend_argv_or_environment() {
    let tmp = tempfile::tempdir().unwrap();
    let (sidecar, _client, secret, _sock) = start(tmp.path()).await;
    let cmdline = std::fs::read(format!("/proc/{}/cmdline", sidecar.pid)).unwrap();
    let environ = std::fs::read(format!("/proc/{}/environ", sidecar.pid)).unwrap();
    let needle = secret.expose().as_bytes();
    assert!(!cmdline.windows(needle.len()).any(|w| w == needle));
    assert!(!environ.windows(needle.len()).any(|w| w == needle));
    // Only the fixed, trusted PATH plus non-secret variables reach the child.
    let env = String::from_utf8_lossy(&environ);
    assert!(env.contains(&format!("PATH={}", sidecar::SIDECAR_PATH)));
    sidecar.shutdown(Duration::from_secs(5)).await;
}

#[tokio::test]
async fn events_stream_relays_setting_changes() {
    let tmp = tempfile::tempdir().unwrap();
    let (sidecar, client, _secret, _sock) = start(tmp.path()).await;
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
    let streamer = client.clone();
    let task = tokio::spawn(async move {
        streamer
            .stream_events(move |event| tx.send(event).is_ok())
            .await
    });
    let opened = tokio::time::timeout(Duration::from_secs(5), rx.recv())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(opened["type"], "system.stream_opened");
    client
        .request_json(
            Method::Put,
            "/v1/settings/appearance.show_status_bar",
            Some(&json!({"value": false})),
        )
        .await
        .unwrap();
    let changed = tokio::time::timeout(Duration::from_secs(5), rx.recv())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(changed["type"], "settings.changed");
    assert_eq!(changed["payload"]["key"], "appearance.show_status_bar");
    sidecar.shutdown(Duration::from_secs(5)).await;
    let _ = tokio::time::timeout(Duration::from_secs(5), task).await;
}

#[tokio::test]
async fn dropping_stdin_stops_the_backend() {
    let tmp = tempfile::tempdir().unwrap();
    let (sidecar, client, _secret, sock) = start(tmp.path()).await;
    let started = std::time::Instant::now();
    let status = sidecar.shutdown(Duration::from_secs(5)).await.unwrap();
    assert!(
        status.success(),
        "backend should exit cleanly on stdin close"
    );
    assert!(started.elapsed() < Duration::from_secs(5));
    assert!(!sock.exists(), "socket file should be removed on exit");
    assert!(client
        .request_json(Method::Get, "/v1/health", None)
        .await
        .is_err());
}
