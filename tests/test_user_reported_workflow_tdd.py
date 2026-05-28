import tempfile
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"


def _build_test_app(tmp_dir: Path):
    from models import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'user_reported_workflow.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_user_reported"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_full_workflow_auto_runs_code_review_and_report(monkeypatch):
    from flow.test_flow import AutoTestFlow
    from models import CodeReviewFinding, CodeReviewTask, FinalReport, Requirement, db

    app, _db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        requirement = Requirement(
            title="Login requirement",
            description="Users can sign in with sms code.",
            raw_text="Users can sign in with sms code.",
            status="pending",
        )
        db.session.add(requirement)
        db.session.commit()
        requirement_id = requirement.id

        flow = AutoTestFlow()
        monkeypatch.setattr(
            flow,
            "parse_requirement",
            lambda demand, req_id: {
                "title": "Login requirement",
                "description": demand,
                "business_modules": [{"name": "Login", "priority": "high", "description": "sms login"}],
            },
        )
        monkeypatch.setattr(flow, "design_test_cases", lambda structured_req, req_id: {"test_cases": []})
        monkeypatch.setattr(flow, "generate_code", lambda test_cases, req_id: {"scripts": []})
        monkeypatch.setattr(flow, "execute_tests", lambda req_id: {"executions": []})

        def _fake_run_review_task(task_id):
            task = db.session.get(CodeReviewTask, task_id)
            task.status = "completed"
            task.summary = "review finished"
            db.session.add(
                CodeReviewFinding(
                    task_id=task_id,
                    commit_sha="abc123",
                    file_path="backend/login.py",
                    severity="high",
                    title="Missing retry limit",
                    detail="Retry limit is not enforced.",
                )
            )
            db.session.commit()
            return {"status": "completed", "task_id": task_id, "findings": 1}

        monkeypatch.setattr("flow.test_flow.run_review_task", _fake_run_review_task, raising=False)

        result = flow.run(
            {
                "demand": "Users can sign in with sms code.",
                "requirement_id": requirement_id,
                "project_id": 1,
                "review": {
                    "repo_url": "http://git.100credit.cn/group/demo-repo.git",
                    "branch": "feature/login",
                    "days": 3,
                },
            }
        )

        task = CodeReviewTask.query.filter_by(repo_url="http://git.100credit.cn/group/demo-repo.git").one()
        report = FinalReport.query.filter_by(requirement_id=requirement_id, review_task_id=task.id).one()

        assert result["status"] == "success"
        assert "code_review" in result["steps_completed"]
        assert "defect_analysis" in result["steps_completed"]
        assert "report_generation" in result["steps_completed"]
        assert result["review"]["task_id"] == task.id
        assert result["report"]["id"] == report.id
        assert result["statistics"]["review_findings"] == 1


def test_case_agent_prompts_require_chinese_test_cases():
    from agent.case_agent import CaseAgent

    agent = CaseAgent()
    prompt = agent.build_prompt(
        {
            "title": "会员登录",
            "description": "用户可以使用短信验证码登录。",
            "test_points": [{"id": "TP-1", "type": "api", "priority": "high", "description": "错误验证码"}],
        }
    )

    assert "必须使用中文" in agent.system_prompt
    assert "测试用例" in agent.system_prompt
    assert "必须使用中文" in prompt


def test_resume_error_requirement_retries_generated_scripts(monkeypatch):
    import importlib
    import sys

    import config as config_module

    retry_db_path = _local_tmp_dir() / "retry_error_flow.db"
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{retry_db_path.as_posix()}")
    importlib.reload(config_module)
    sys.modules.pop("main", None)
    import main

    captured = {}

    class DummyExecutor:
        def submit(self, target, *args):
            captured["target"] = target
            captured["args"] = args
            captured["started"] = True
            return None

    monkeypatch.setattr("service.flow_service._executor", DummyExecutor())
    monkeypatch.setattr("service.flow_service.AutoTestFlow", lambda: object())

    with main.app.app_context():
        from models import Requirement, TestCase, TestScript, db

        requirement = Requirement(
            title="Failed login requirement",
            description="Login flow execution failed.",
            raw_text="Login flow execution failed.",
            status="error",
            structured_data={"title": "Failed login requirement"},
            execution_progress={"status": "failed", "failed_step": "execute_tests"},
        )
        db.session.add(requirement)
        db.session.flush()

        case = TestCase(
            requirement_id=requirement.id,
            title="登录成功进入会员中心",
            description="重新执行已有脚本",
            test_type="ui",
            priority="high",
            steps=[{"step": 1, "action": "登录", "expected": "进入首页"}],
        )
        db.session.add(case)
        db.session.flush()

        db.session.add(
            TestScript(
                test_case_id=case.id,
                script_type="playwright",
                script_content="def test_login():\n    assert True\n",
                file_path="workspace/scripts/test_login.py",
                status="error",
            )
        )
        db.session.commit()
        requirement_id = requirement.id

    response = main.app.test_client().post(f"/api/flow/resume/{requirement_id}")

    assert response.status_code == 202
    assert captured["started"] is True
    flow_data = captured["args"][1]
    assert flow_data["requirement_id"] == requirement_id
    assert flow_data["resume_from"] == "code_generated"

    with main.app.app_context():
        from models import Requirement, db

        retried_requirement = db.session.get(Requirement, requirement_id)
        assert retried_requirement.status == "code_generated"


def test_execute_flow_async_marks_failed_result_as_error(monkeypatch):
    import importlib
    import sys
    from contextlib import contextmanager

    import config as config_module

    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{(_local_tmp_dir() / 'failed_async.db').as_posix()}")
    importlib.reload(config_module)
    sys.modules.pop("main", None)
    import main
    from service import flow_service

    class DummyFlow:
        def run(self, flow_data):
            return {"status": "failed", "failed_step": "execute_tests", "error": "script failed"}

    class DummyRequirement:
        def __init__(self):
            self.status = "executing"
            self.structured_data = {"title": "existing"}
            self.execution_progress = None

    req = DummyRequirement()

    class DummySession:
        def get(self, model, requirement_id):
            return req

        def commit(self):
            return None

    @contextmanager
    def _ctx():
        yield

    monkeypatch.setattr(flow_service.db, "session", DummySession(), raising=False)
    monkeypatch.setattr(main.app, "app_context", _ctx)

    main.execute_flow_async(DummyFlow(), {"demand": "x"}, 1)

    assert req.status == "error"
    assert req.execution_progress["status"] == "failed"
