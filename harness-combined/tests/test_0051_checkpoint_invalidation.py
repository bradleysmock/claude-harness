"""Ticket 0051 — Checkpoint invalidation on spec edits and post-rebase re-gating.

Unit tests for the fingerprinting checkpoint tool in server.py, plus
content-verification tests for the build-ticket Step 3 and deliver-ticket Step 7
flow-doc changes.
"""
from __future__ import annotations

import json
from pathlib import Path

import server

BUILD_FLOW = Path(__file__).parent.parent / "context" / "flows" / "build-ticket.md"
DELIVER_FLOW = Path(__file__).parent.parent / "context" / "flows" / "deliver-ticket.md"


def _mk_project(tmp_path: Path, task_id: str, spec_ids: list[str]) -> Path:
    """Create a minimal .harness tree with spec files and a task file."""
    harness = tmp_path / ".harness"
    specs = harness / "specs"
    tasks = harness / "tasks"
    specs.mkdir(parents=True)
    tasks.mkdir(parents=True)
    for sid in spec_ids:
        (specs / f"{sid}.py").write_text(f"# spec {sid}\nspec = object()\n")
    (tasks / f"{task_id}.py").write_text(f"# task {task_id}\ntask = object()\n")
    return tmp_path


def _read(tmp_path: Path, task_id: str) -> dict:
    return json.loads(server.checkpoint("read", task_id, str(tmp_path)))


# --- FR-1 / FR-2: write/read round-trip stores hashes and keeps unchanged specs ---


def test_write_stores_hashes_for_specs_and_task(tmp_path):
    task_id = "t-round"
    specs = ["t-round-a", "t-round-b"]
    _mk_project(tmp_path, task_id, specs)

    server.checkpoint("write", task_id, str(tmp_path), completed=specs)

    raw = json.loads((tmp_path / ".harness" / "checkpoints" / f"{task_id}.json").read_text())
    assert raw["completed"] == specs
    assert set(raw["hashes"]) == set(specs)
    assert all(isinstance(h, str) and len(h) == 64 for h in raw["hashes"].values())
    assert isinstance(raw["task_hash"], str) and len(raw["task_hash"]) == 64
    # Backward-compatible: original fields remain.
    assert raw["task_id"] == task_id
    assert "updated" in raw


def test_roundtrip_all_valid_when_nothing_changes(tmp_path):
    task_id = "t-valid"
    specs = ["t-valid-a", "t-valid-b"]
    _mk_project(tmp_path, task_id, specs)
    server.checkpoint("write", task_id, str(tmp_path), completed=specs)

    result = _read(tmp_path, task_id)
    assert result["completed"] == specs
    assert result["invalidated"] == []


# --- FR-2: edited spec is excluded and reported; sibling retained ---


def test_edited_spec_invalidated_sibling_kept(tmp_path):
    task_id = "t-edit"
    specs = ["t-edit-a", "t-edit-b"]
    _mk_project(tmp_path, task_id, specs)
    server.checkpoint("write", task_id, str(tmp_path), completed=specs)

    # Edit only spec a.
    (tmp_path / ".harness" / "specs" / "t-edit-a.py").write_text("# spec t-edit-a EDITED\n")

    result = _read(tmp_path, task_id)
    assert result["completed"] == ["t-edit-b"]
    assert result["invalidated"] == ["t-edit-a"]


def test_task_file_edit_invalidates_all(tmp_path):
    task_id = "t-task"
    specs = ["t-task-a", "t-task-b"]
    _mk_project(tmp_path, task_id, specs)
    server.checkpoint("write", task_id, str(tmp_path), completed=specs)

    (tmp_path / ".harness" / "tasks" / f"{task_id}.py").write_text("# task CHANGED\n")

    result = _read(tmp_path, task_id)
    assert result["completed"] == []
    assert sorted(result["invalidated"]) == sorted(specs)


def test_deleted_spec_file_invalidates_entry(tmp_path):
    task_id = "t-del"
    specs = ["t-del-a", "t-del-b"]
    _mk_project(tmp_path, task_id, specs)
    server.checkpoint("write", task_id, str(tmp_path), completed=specs)

    (tmp_path / ".harness" / "specs" / "t-del-a.py").unlink()

    result = _read(tmp_path, task_id)
    assert result["completed"] == ["t-del-b"]
    assert result["invalidated"] == ["t-del-a"]


# --- FR-5: legacy checkpoint (no hashes) is fully invalidated ---


def test_legacy_checkpoint_fully_invalidated(tmp_path):
    task_id = "t-legacy"
    specs = ["t-legacy-a", "t-legacy-b"]
    _mk_project(tmp_path, task_id, specs)
    # Simulate an older checkpoint written before hashes existed.
    ckpt_dir = tmp_path / ".harness" / "checkpoints"
    ckpt_dir.mkdir(parents=True)
    (ckpt_dir / f"{task_id}.json").write_text(
        json.dumps({"task_id": task_id, "completed": specs, "updated": "2020-01-01T00:00:00"})
    )

    result = _read(tmp_path, task_id)
    assert result["completed"] == []
    assert result["invalidated"] == specs


# --- Read with no checkpoint file ---


def test_read_no_checkpoint_file(tmp_path):
    _mk_project(tmp_path, "t-none", ["t-none-a"])
    result = _read(tmp_path, "t-none")
    assert result["completed"] == []
    assert result["invalidated"] == []


def test_single_spec_no_task_file_stays_valid(tmp_path):
    """Common non-DAG path: individual specs with no task file. task_hash is None on
    both write and read, which must not invalidate an unchanged spec."""
    task_id = "0051-solo"
    harness = tmp_path / ".harness"
    (harness / "specs").mkdir(parents=True)
    (harness / "specs" / f"{task_id}.py").write_text("# solo spec\nspec = object()\n")
    # No tasks/ dir at all — no task file.
    server.checkpoint("write", task_id, str(tmp_path), completed=[task_id])

    raw = json.loads((harness / "checkpoints" / f"{task_id}.json").read_text())
    assert raw["task_hash"] is None

    result = _read(tmp_path, task_id)
    assert result["completed"] == [task_id]
    assert result["invalidated"] == []


# --- FR-3: build-ticket Step 3 announcement ---


def test_build_flow_step3_announces_invalidated():
    content = BUILD_FLOW.read_text()
    start = content.find("## Step 3")
    end = content.find("## Step 4", start)
    step3 = content[start:end if end >= 0 else len(content)]
    assert "invalidated" in step3
    assert "spec edited since last pass" in step3
    assert "will re-run" in step3


# --- FR-4: deliver-ticket Step 7 re-gate + conditional downgrade ---


def test_deliver_flow_step7_regates_and_conditionally_downgrades():
    content = DELIVER_FLOW.read_text()
    start = content.find("## Step 7")
    end = content.find("## Step 8", start)
    step7 = content[start:end if end >= 0 else len(content)]
    assert "gate_run_on_dir" in step7
    assert "re-gated clean after rebase" in step7
    # Downgrade is conditioned on gate failure, not unconditional.
    assert "Gate fails" in step7 or "gate failure" in step7
    assert "downgrade" in step7.lower()
