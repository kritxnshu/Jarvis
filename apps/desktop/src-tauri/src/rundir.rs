//! Per-launch private directory that holds the backend socket.

use std::fs::{self, DirBuilder};
use std::io;
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
use std::path::{Path, PathBuf};

use crate::secret::to_hex;

/// macOS `sun_path` is 104 bytes including the terminating NUL.
pub const MAX_SOCKET_PATH: usize = 103;
pub const SOCKET_NAME: &str = "b.sock";

#[derive(Debug)]
pub struct RunDir {
    pub dir: PathBuf,
    pub socket_path: PathBuf,
}

/// Creates `<data_dir>/run/<8 hex chars>/` with mode 0700 and removes stale launch dirs.
pub fn create(data_dir: &Path) -> io::Result<RunDir> {
    let run_root = data_dir.join("run");
    DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(&run_root)?;
    fs::set_permissions(&run_root, fs::Permissions::from_mode(0o700))?;
    remove_stale(&run_root);

    let mut id = [0u8; 4];
    getrandom::fill(&mut id).map_err(|e| io::Error::other(e.to_string()))?;
    let dir = run_root.join(to_hex(&id));
    DirBuilder::new().mode(0o700).create(&dir)?;
    // The process umask may have stripped bits we asked for; set the exact mode.
    fs::set_permissions(&dir, fs::Permissions::from_mode(0o700))?;

    let socket_path = dir.join(SOCKET_NAME);
    let len = socket_path.as_os_str().len();
    if len > MAX_SOCKET_PATH {
        let _ = fs::remove_dir(&dir);
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("socket path is {len} bytes; the limit is {MAX_SOCKET_PATH}"),
        ));
    }
    Ok(RunDir { dir, socket_path })
}

/// Best effort: earlier launches that crashed may have left directories behind.
fn remove_stale(run_root: &Path) {
    if let Ok(entries) = fs::read_dir(run_root) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() && !path.is_symlink() {
                let _ = fs::remove_dir_all(&path);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::MetadataExt;

    #[test]
    fn creates_private_dirs() {
        let tmp = tempfile::tempdir().unwrap();
        let rd = create(tmp.path()).unwrap();
        assert_eq!(fs::metadata(&rd.dir).unwrap().mode() & 0o777, 0o700);
        assert_eq!(
            fs::metadata(tmp.path().join("run")).unwrap().mode() & 0o777,
            0o700
        );
        assert_eq!(rd.socket_path.parent().unwrap(), rd.dir);
    }

    #[test]
    fn removes_stale_launch_dirs() {
        let tmp = tempfile::tempdir().unwrap();
        let first = create(tmp.path()).unwrap();
        let second = create(tmp.path()).unwrap();
        assert!(!first.dir.exists());
        assert!(second.dir.exists());
    }

    #[test]
    fn rejects_overlong_socket_paths() {
        let tmp = tempfile::tempdir().unwrap();
        let deep = tmp.path().join("x".repeat(110));
        fs::create_dir_all(&deep).unwrap();
        let err = create(&deep).unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::InvalidInput);
    }
}
