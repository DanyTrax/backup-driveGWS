"""Plan de backup Drive fechado en cadena (TOTAL / INC)."""
from __future__ import annotations

from app.services.drive_incremental_plan import is_full_snapshot_folder_name, plan_next_dated_backup


def test_is_full_marker() -> None:
    assert is_full_snapshot_folder_name("2025-01-01T00-00 (TOTAL)") is True
    assert is_full_snapshot_folder_name("x (SNAPSHOT)") is True
    assert is_full_snapshot_folder_name("2025-01-01T00-00 (INC)") is False


def test_plan_empty_is_full() -> None:
    k, c = plan_next_dated_backup([], keep=30)
    assert k == "full"
    assert c is None


def test_plan_incremental_when_keep_room() -> None:
    ch = [
        {"id": "1", "name": "2025-01-01T01-00 (TOTAL)"},
        {"id": "2", "name": "2025-01-02T01-00 (INC)"},
    ]
    k, c = plan_next_dated_backup(ch, keep=30)
    assert k == "incremental"
    assert c == "2025-01-02T01-00 (INC)"


def test_plan_full_when_prune_would_remove_total_anchor() -> None:
    ch = [{"id": "0", "name": "2025-01-01T01-00 (TOTAL)"}]
    for i in range(2, 31):
        ch.append({"id": str(i), "name": f"2025-01-{i:02d}T01-00 (INC)"})
    k, c = plan_next_dated_backup(ch, keep=30)
    assert k == "full"
    assert c is None


def test_plan_incremental_when_prune_only_inc_folders() -> None:
    ch = [{"id": str(i), "name": f"2025-01-{i:02d}T01-00 (INC)"} for i in range(1, 31)]
    k, c = plan_next_dated_backup(ch, keep=30)
    assert k == "incremental"
    assert c == "2025-01-30T01-00 (INC)"


def test_plan_incremental_when_keep_zero_never_prune_oldest() -> None:
    """keep=0: sin poda simulada, siempre incremental si hay historia."""
    ch = [
        {"id": "1", "name": "2025-01-01T01-00"},
        {"id": "2", "name": "2025-01-02T01-00"},
    ]
    k, c = plan_next_dated_backup(ch, keep=0)
    assert k == "incremental"
    assert c == "2025-01-02T01-00"
