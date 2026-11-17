"""PyInstaller entry point for the frozen backend sidecar."""

import sys

from jarvis.runtime.main import main

sys.exit(main())
