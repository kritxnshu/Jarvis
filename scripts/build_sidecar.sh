#!/usr/bin/env bash
# Freeze the Python core into a self-contained directory (ADR-0003: PyInstaller --onedir).
# Output: dist-sidecar/jarvis-backend/jarvis-backend (+ its _internal/ directory).
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_NO_PROGRESS=1

rm -rf build/pyinstaller dist-sidecar
uv run --group packaging pyinstaller \
  --noconfirm --clean --onedir \
  --name jarvis-backend \
  --distpath dist-sidecar \
  --workpath build/pyinstaller \
  --specpath build/pyinstaller \
  --paths backend/src \
  --collect-submodules uvicorn \
  --collect-submodules jarvis \
  --add-data "$PWD/backend/src/jarvis/storage/migrations/*.sql:jarvis/storage/migrations" \
  --noupx \
  backend/packaging/jarvis_backend.py
echo "sidecar: $(du -sh dist-sidecar/jarvis-backend | cut -f1) at dist-sidecar/jarvis-backend"
