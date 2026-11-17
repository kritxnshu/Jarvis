"""Test-only backend entry point: the real runtime plus the fixture tools.

Launched by tests as `python -m tests.fixtures.backend_entry`. Never packaged.
"""

import sys

from jarvis.runtime.main import main
from jarvis.trust.secrets import MemorySecretStore
from tests.fixtures.tools import build_fixture_registry

# A memory store stands in for the macOS Keychain (unavailable on Linux test machines).
sys.exit(main(build_fixture_registry(), MemorySecretStore()))
