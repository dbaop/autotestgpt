import json
from contextlib import contextmanager
from pathlib import Path

import pytest


def test_code_agent_process_returns_script_objects(monkeypatch):
    from agent.code_agent import CodeAgent
    from config import Config

    workspace = Path("./workspace/test_phase1_tdd")
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Config, "WORKSPACE", str(workspace), raising=False)

    agent = CodeAgent()

    fake_response = json.dumps(
        {
            "scripts": [
                {
                    "id": "TC-001",
                    "title": "demo",
                    "language": "python",
                    "code": "def test_demo():\n    assert True\n",
                }
            ]
        },
        ensure_ascii=False,
    )

    monkeypatch.setattr(agent, "call_llm", lambda *args, **kwargs: fake_response)

    result = agent.process(
        {
            "test_cases": {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "title": "demo",
                        "test_type": "api",
                    }
                ]
            }
        }
    )

    assert isinstance(result["scripts"], list)
    assert result["scripts"], "scripts should not be empty"
    assert isinstance(result["scripts"][0], dict)
    assert result["scripts"][0]["id"] == "TC-001"
    assert "code" in result["scripts"][0]


def test_execute_flow_async_should_not_overwrite_structured_requirement(monkeypatch):
    import importlib
    import sys
    import config as config_module

    monkeypatch.setenv("DATABASE_URI", "sqlite:///phase1_test.db")
    importlib.reload(config_module)
    sys.modules.pop("main", None)
    import main

    class DummyFlow:
        def run(self, flow_data):
            return {"status": "success", "statistics": {"tests": 1}}

    class DummyRequirement:
        def __init__(self):
            self.status = "parsed"
            self.structured_data = {"title": "existing structured requirement"}

    req = DummyRequirement()

    class DummySession:
        def get(self, model, requirement_id):
            return req

        def commit(self):
            return None

    @contextmanager
    def _ctx():
        yield

    monkeypatch.setattr(main.db, "session", DummySession(), raising=False)
    monkeypatch.setattr(main.app, "app_context", _ctx)

    main.execute_flow_async(DummyFlow(), {"demand": "x"}, 1)

    assert req.status == "completed"
    assert req.structured_data == {"title": "existing structured requirement"}


def test_config_should_build_mysql_uri_from_db_fields(monkeypatch):
    import importlib
    import config as config_module

    monkeypatch.setenv("DATABASE_URI", "")
    monkeypatch.setenv("DB_HOST", "192.168.162.137")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_PASSWORD", "Dya20231108@")
    monkeypatch.setenv("DB_NAME", "autotestgpt")

    importlib.reload(config_module)

    assert config_module.Config.DATABASE_URI.startswith("mysql+pymysql://")
    assert "192.168.162.137:3306" in config_module.Config.DATABASE_URI
    assert "autotestgpt" in config_module.Config.DATABASE_URI


def test_review_models_exist():
    import models

    assert hasattr(models, "CodeReviewTask")
    assert hasattr(models, "CodeReviewFinding")


def test_review_service_collects_commits_and_writes_task(monkeypatch):
    from service.review_service import run_review_task

    class DummyTask:
        def __init__(self):
            self.id = 11
            self.repo_url = "http://git.100credit.cn/group/repo.git"
            self.branch = "main"
            self.days = 3
            self.status = "pending"
            self.summary = None
            self.error_message = None
            self.started_at = None
            self.finished_at = None

    task = DummyTask()
    added = []

    class DummySession:
        def get(self, model, task_id):
            return task

        def add(self, obj):
            added.append(obj)

        def commit(self):
            return None

        def rollback(self):
            return None

    monkeypatch.setattr("service.review_service.db.session", DummySession())

    def _fake_git(cmd, cwd=None):
        if "log" in cmd:
            return "abc123|alice|2026-05-25|fix login bug"
        if "show" in cmd:
            return "diff --git a/a.py b/a.py\n+print('ok')"
        return ""

    monkeypatch.setattr("service.review_service._run_git", _fake_git)

    result = run_review_task(11)

    assert result["status"] == "completed"
    assert task.status == "completed"
    assert "1 commits" in (task.summary or "")
    assert added, "Expected findings to be added"
