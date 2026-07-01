from __future__ import annotations

import json
from pathlib import Path

from kata.challenge import queued_pool_status
from kata.live_progress import update_live_status, update_pool_status


def test_live_progress_updates_and_merges_pools(
    monkeypatch,
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "live-status.json"
    monkeypatch.setenv("KATA_LIVE_STATUS_PATH", str(status_path))

    update_live_status({"state": "running", "phase": "primary", "repo_pack": "demo"})
    update_pool_status(
        "primary",
        {
            "state": "running",
            "total_tasks": 2,
            "completed_tasks": 1,
            "task_statuses": [{"task_id": "task-a", "status": "candidate ahead"}],
        },
    )
    update_pool_status(
        "holdout",
        {
            "state": "queued",
            "total_tasks": 1,
            "completed_tasks": 0,
            "task_statuses": [{"task_id": "secret-a", "status": "queued"}],
        },
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["state"] == "running"
    assert payload["phase"] == "holdout"
    assert payload["repo_pack"] == "demo"
    assert payload["pools"]["primary"]["completed_tasks"] == 1
    assert payload["pools"]["holdout"]["total_tasks"] == 1


def test_queued_pool_status_initializes_all_tasks_as_pending() -> None:
    payload = queued_pool_status("holdout", ["secret-a", "secret-b"])

    assert payload["name"] == "holdout"
    assert payload["state"] == "queued"
    assert payload["total_tasks"] == 2
    assert payload["completed_tasks"] == 0
    assert payload["task_statuses"] == [
        {
            "task_id": "secret-a",
            "status": "queued",
            "completed": False,
            "candidate": {"started": False, "finished": False},
            "frontier": {"started": False, "finished": False},
        },
        {
            "task_id": "secret-b",
            "status": "queued",
            "completed": False,
            "candidate": {"started": False, "finished": False},
            "frontier": {"started": False, "finished": False},
        },
    ]
