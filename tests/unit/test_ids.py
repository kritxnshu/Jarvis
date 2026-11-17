from __future__ import annotations

import re
import time

from jarvis.ids import new_id, utc_now_iso


def test_ids_are_unique_and_sortable() -> None:
    first = new_id()
    time.sleep(0.002)
    ids = [new_id() for _ in range(1000)]
    assert len(set(ids)) == 1000
    assert all(len(i) == 26 for i in ids)
    assert first < ids[0]


def test_timestamp_format() -> None:
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", utc_now_iso())
