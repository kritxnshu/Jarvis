from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from jarvis.config.settings_service import (
    InvalidSettingValueError,
    SettingsService,
    UnknownSettingError,
)
from jarvis.storage.db import Database
from jarvis.storage.migrator import apply_migrations
from jarvis.storage.settings_repo import SettingsRepository
from tests.conftest import CANARY


@pytest.fixture
def service(tmp_path: Path) -> Iterator[SettingsService]:
    db = Database(tmp_path / "s.sqlite3")
    apply_migrations(db)
    yield SettingsService(SettingsRepository(db))
    db.close()


def test_defaults_listed(service: SettingsService) -> None:
    views = {v.key: v for v in service.list()}
    assert views["appearance.reduced_motion"].value == "system"
    assert all(v.is_default for v in views.values())


def test_set_and_read_back(service: SettingsService) -> None:
    service.set("appearance.reduced_motion", "on")
    views = {v.key: v for v in service.list()}
    assert views["appearance.reduced_motion"].value == "on"
    assert not views["appearance.reduced_motion"].is_default


def test_unknown_key_rejected(service: SettingsService) -> None:
    with pytest.raises(UnknownSettingError):
        service.set("nope", 1)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("appearance.reduced_motion", "sideways"),
        ("appearance.reduced_motion", CANARY),
        ("appearance.show_status_bar", "true"),  # strict: strings are not booleans
        ("appearance.show_status_bar", 1),
    ],
)
def test_invalid_values_rejected_without_echo(
    service: SettingsService, key: str, value: object
) -> None:
    with pytest.raises(InvalidSettingValueError) as info:
        service.set(key, value)
    assert str(value) not in str(info.value)
