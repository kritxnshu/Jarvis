//! Launching and stopping the Python backend.
//!
//! The secret goes over stdin, never argv or the environment. Stdin stays open for the
//! sidecar's lifetime: when this process dies the pipe closes and the backend exits.

use std::path::{Path, PathBuf};
use std::process::{ExitStatus, Stdio};
use std::time::Duration;

use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};

use crate::error::BridgeError;
use crate::rundir::RunDir;
use crate::secret::LaunchSecret;

/// Trusted system directories only; nothing user-writable.
pub const SIDECAR_PATH: &str = "/usr/bin:/bin:/usr/sbin:/sbin";

#[derive(Debug, Clone)]
pub struct SidecarCommand {
    pub program: PathBuf,
    pub args: Vec<String>,
    /// Non-secret variables only (e.g. PYTHONPATH in development).
    pub env: Vec<(String, String)>,
}

impl SidecarCommand {
    /// Production: the frozen backend bundled at `<resources>/sidecar/jarvis-backend/`.
    pub fn bundled(resource_dir: &Path) -> Option<Self> {
        let program = resource_dir
            .join("sidecar")
            .join("jarvis-backend")
            .join("jarvis-backend");
        program.is_file().then(|| Self {
            program,
            args: vec![],
            env: vec![],
        })
    }

    /// Development: the repository's virtualenv Python running `-m jarvis`.
    pub fn development(repo_root: &Path) -> Option<Self> {
        let program = repo_root.join(".venv").join("bin").join("python");
        program.exists().then(|| Self {
            program,
            args: vec!["-m".into(), "jarvis".into()],
            env: vec![(
                "PYTHONPATH".into(),
                repo_root.join("backend").join("src").display().to_string(),
            )],
        })
    }
}

#[derive(Debug)]
pub struct Sidecar {
    child: Child,
    stdin: Option<ChildStdin>,
    pub pid: u32,
}

pub async fn launch(
    cmd: &SidecarCommand,
    secret: &LaunchSecret,
    run_dir: &RunDir,
    data_dir: &Path,
    ready_timeout: Duration,
) -> Result<Sidecar, BridgeError> {
    let mut command = Command::new(&cmd.program);
    command
        .args(&cmd.args)
        .env_clear()
        .env("PATH", SIDECAR_PATH)
        .env("LANG", "en_US.UTF-8")
        .envs(cmd.env.iter().map(|(k, v)| (k.as_str(), v.as_str())))
        .current_dir(data_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .kill_on_drop(true);
    let mut child = command
        .spawn()
        .map_err(|e| BridgeError::new("sidecar_spawn_failed", e.to_string()))?;
    let pid = child.id().unwrap_or_default();

    let handshake = serde_json::json!({
        "secret": secret.expose(),
        "socket_path": run_dir.socket_path,
        "data_dir": data_dir,
    });
    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| BridgeError::new("sidecar_spawn_failed", "no stdin pipe"))?;
    let mut line = serde_json::to_vec(&handshake)
        .map_err(|e| BridgeError::new("sidecar_spawn_failed", e.to_string()))?;
    line.push(b'\n');
    stdin
        .write_all(&line)
        .await
        .map_err(|e| BridgeError::new("sidecar_handshake_failed", e.to_string()))?;
    stdin
        .flush()
        .await
        .map_err(|e| BridgeError::new("sidecar_handshake_failed", e.to_string()))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| BridgeError::new("sidecar_spawn_failed", "no stdout pipe"))?;
    let mut reader = BufReader::new(stdout);
    let mut ready_line = String::new();
    let read = tokio::time::timeout(ready_timeout, reader.read_line(&mut ready_line)).await;
    let ready = match read {
        Ok(Ok(n)) if n > 0 => serde_json::from_str::<serde_json::Value>(&ready_line)
            .ok()
            .and_then(|v| v.get("ready").and_then(serde_json::Value::as_bool))
            .unwrap_or(false),
        _ => false,
    };
    if !ready {
        let _ = child.start_kill();
        let status = child.wait().await.ok();
        return Err(BridgeError::new(
            "sidecar_not_ready",
            format!("backend did not report ready (exit status: {status:?})"),
        ));
    }
    // The backend writes nothing more to stdout; drain it anyway so it can never block.
    tokio::spawn(async move {
        let mut sink = String::new();
        while matches!(reader.read_line(&mut sink).await, Ok(n) if n > 0) {
            sink.clear();
        }
    });
    Ok(Sidecar {
        child,
        stdin: Some(stdin),
        pid,
    })
}

impl Sidecar {
    /// Close stdin (the backend's shutdown signal), wait up to `grace`, then kill.
    pub async fn shutdown(mut self, grace: Duration) -> Option<ExitStatus> {
        drop(self.stdin.take());
        match tokio::time::timeout(grace, self.child.wait()).await {
            Ok(Ok(status)) => Some(status),
            _ => {
                let _ = self.child.start_kill();
                self.child.wait().await.ok()
            }
        }
    }
}
