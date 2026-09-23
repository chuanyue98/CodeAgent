"""委派运行记录路由的测试。"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.services import delegation_runs
from core.web.routers import delegations as delegations_router
from tests._helpers import assert_camel

RUN_ID = "claude-20260923-141420-b4f2f2"


@pytest.fixture
def runs(tmp_path, monkeypatch):
    root = tmp_path / "runs"
    monkeypatch.setattr(delegation_runs, "runs_root", lambda: root)
    return root


def _write_run(root, run_id, *, status, pid=None, result=None, output=""):
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "task.json").write_text(
        json.dumps(
            {
                "engine": "claude",
                "mode": "review",
                "instruction": "review 一下",
                "workspace": "/repo",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps(
            {
                "status": status,
                "pid": pid,
                "created_at": 100.0,
                "started_at": 100.0,
                "ended_at": 112.5 if status != "running" else None,
            }
        ),
        encoding="utf-8",
    )
    if result is not None:
        (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (run_dir / "output.log").write_text(output, encoding="utf-8")
    return run_dir


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(delegations_router.router)
    return TestClient(app)


def test_list_is_camel_case_and_leaves_results_out(runs):
    _write_run(
        runs,
        RUN_ID,
        status="completed",
        result={"success": True, "files_changed": ["a.py"]},
    )

    body = _client().get("/api/delegations").json()

    assert_camel(body)
    [run] = body["runs"]
    assert run["runId"] == RUN_ID
    assert run["status"] == "completed"
    assert run["elapsedSeconds"] == 12.5
    assert "result" not in run


def test_list_filters_by_workspace(runs):
    _write_run(runs, RUN_ID, status="completed")

    body = _client().get("/api/delegations", params={"workspace": "/other"}).json()

    assert body == {"runs": []}


def test_detail_carries_the_result_and_the_output_tail(runs):
    _write_run(
        runs,
        RUN_ID,
        status="completed",
        result={"success": True, "files_changed": ["a.py"], "diff": "+x"},
        output="开头\n" + "x" * 10_000 + "\n结尾",
    )

    body = _client().get(f"/api/delegations/{RUN_ID}").json()

    assert_camel(body)
    assert body["result"]["filesChanged"] == ["a.py"]
    assert body["outputTail"].endswith("结尾")
    assert "开头" not in body["outputTail"]


def test_unknown_and_malformed_ids_are_404(runs):
    client = _client()
    assert (
        client.get("/api/delegations/claude-20260101-000000-000000").status_code == 404
    )
    assert client.get("/api/delegations/not-a-run-id").status_code == 404


def test_stopping_a_finished_run_is_a_conflict(runs):
    _write_run(runs, RUN_ID, status="completed")

    response = _client().post(f"/api/delegations/{RUN_ID}/stop")

    assert response.status_code == 409


@pytest.mark.skipif(sys.platform == "win32", reason="用进程组结束 worker")
def test_stop_ends_a_running_worker(runs):
    worker = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    try:
        _write_run(runs, RUN_ID, status="running", pid=worker.pid)

        response = _client().post(f"/api/delegations/{RUN_ID}/stop")

        assert response.status_code == 200
        assert worker.wait(timeout=10) is not None
        body = _client().get(f"/api/delegations/{RUN_ID}").json()
        assert body["status"] == "stopped"
    finally:
        if worker.poll() is None:
            worker.kill()


def test_newest_run_comes_first_whatever_the_engine(runs):
    """run id 以引擎名开头，按名字排序会让 opencode 永远压在 claude 前面。"""
    _write_run(runs, "opencode-20260923-100000-aaaaaa", status="completed")
    _write_run(runs, "claude-20260923-120000-bbbbbb", status="completed")

    body = _client().get("/api/delegations").json()

    assert [run["runId"] for run in body["runs"]] == [
        "claude-20260923-120000-bbbbbb",
        "opencode-20260923-100000-aaaaaa",
    ]
