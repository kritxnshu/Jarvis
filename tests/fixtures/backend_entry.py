"""Test-only backend entry point: the real runtime plus the fixture tools.

Launched by tests as `python -m tests.fixtures.backend_entry`. Never packaged.
"""

import sys

from jarvis.runtime.main import main
from tests.fixtures.tools import build_fixture_registry

sys.exit(main(build_fixture_registry()))
