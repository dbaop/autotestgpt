import tempfile
import sys
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_test_app(tmp_dir: Path):
    from api import api_blueprint
    from models import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'agent_workbench.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    app.register_blueprint(api_blueprint, url_prefix="/api")

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_agent_workbench"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def _seed_workbench_data(db):
    from models import (
        CodeReviewFinding,
        CodeReviewTask,
        DefectCandidate,
        ExecutionRecord,
        FinalReport,
        Requirement,
        TestCase,
        TestScript,
    )

    requirement = Requirement(
        title="会员中心登录",
        description="短信验证码登录会员中心。",
        raw_text="短信验证码登录会员中心。",
        structured_data={"title": "会员中心登录", "test_environment": {"test_url": "https://test.example.com"}},
        status="completed",
        execution_progress={
            "status": "success",
            "review": {"task_id": 1},
            "defects": {"defect_count": 1},
            "test_environment": {"test_url": "https://test.example.com", "login_state": "pre_authenticated"},
        },
    )
    db.session.add(requirement)
    db.session.flush()

    ui_case = TestCase(
        requirement_id=requirement.id,
        title="登录后进入会员中心",
        description="浏览器登录后进入首页。",
        test_type="ui",
        priority="high",
        steps=[{"step": 1, "action": "打开测试地址", "expected": "进入首页"}],
    )
    api_case = TestCase(
        requirement_id=requirement.id,
        title="登录接口返回 token",
        description="接口返回 token。",
        test_type="api",
        priority="medium",
        steps=[{"step": 1, "action": "调用接口", "expected": "返回 token"}],
    )
    db.session.add(ui_case)
    db.session.add(api_case)
    db.session.flush()

    ui_script = TestScript(
        test_case_id=ui_case.id,
        script_type="playwright",
        script_content="def test_ui_login(page):\n    assert True\n",
        file_path="workspace/ui_tests/test_login.py",
        status="executed",
    )
    api_script = TestScript(
        test_case_id=api_case.id,
        script_type="python",
        script_content="def test_api_login():\n    assert True\n",
        status="executed",
    )
    db.session.add(ui_script)
    db.session.add(api_script)
    db.session.flush()

    execution = ExecutionRecord(
        test_script_id=ui_script.id,
        status="failed",
        result_data={"passed": False},
        error_message="Timeout waiting for member center home",
        execution_time=12.5,
    )
    db.session.add(execution)

    review_task = CodeReviewTask(
        repo_url="http://git.example.com/app.git",
        branch="feature/login",
        days=3,
        status="completed",
        summary="review finished",
    )
    db.session.add(review_task)
    db.session.flush()
    requirement.execution_progress["review"]["task_id"] = review_task.id

    db.session.add(
        CodeReviewFinding(
            task_id=review_task.id,
            file_path="src/login.ts",
            severity="high",
            title="验证码重试未限制",
            detail="连续输错验证码未触发限制。",
        )
    )
    db.session.add(
        DefectCandidate(
            requirement_id=requirement.id,
            review_task_id=review_task.id,
            test_case_id=ui_case.id,
            execution_record_id=execution.id,
            source_type="execution",
            severity="high",
            title="Execution failure: 登录后进入会员中心",
            summary="Timeout waiting for member center home",
        )
    )
    db.session.add(
        FinalReport(
            requirement_id=requirement.id,
            review_task_id=review_task.id,
            title="会员中心登录报告",
            html_content="<h1>report</h1>",
        )
    )
    db.session.commit()
    return requirement


def test_agent_workbench_api_summarizes_agents_and_artifacts():
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        requirement = _seed_workbench_data(db)
        requirement_id = requirement.id

    response = app.test_client().get("/api/agent-workbench")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["summary"]["total_requirements"] == 1
    item = payload["items"][0]
    assert item["requirement"]["id"] == requirement_id
    assert item["environment"]["test_url"] == "https://test.example.com"
    assert item["artifacts"]["ui_scripts"] == 1
    assert item["artifacts"]["review_findings"] == 1
    assert item["artifacts"]["defects"] == 1

    agents = {agent["id"]: agent for agent in item["agents"]}
    assert agents["browser_agent"]["status"] == "done"
    assert "agent-browser" in agents["browser_agent"]["current_action"]
    assert agents["code_review_agent"]["status"] == "done"
    assert agents["bug_agent"]["status"] == "done"
    assert any(event["agent"] == "BrowserAgent" for event in item["events"])
    assert any(event["agent"] == "BugAgent" for event in item["events"])


def test_agent_workbench_marks_current_agent_as_running():
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import Requirement

        requirement = Requirement(
            title="待设计用例",
            description="需求已解析，BrowserAgent 正在探索页面DOM。",
            raw_text="需求已解析，等待页面探索。",
            structured_data={"title": "待设计用例"},
            status="parsed",
        )
        db.session.add(requirement)
        db.session.commit()

    response = app.test_client().get("/api/agent-workbench")

    assert response.status_code == 200
    agents = {agent["id"]: agent for agent in response.get_json()["items"][0]["agents"]}
    assert agents["req_agent"]["status"] == "done"
    # parsed → browser_agent 先探索页面，case_agent 等 probed 后才启动
    assert agents["browser_agent"]["status"] == "running", f"browser_agent should be running, got {agents['browser_agent']['status']}"
    assert agents["case_agent"]["status"] == "queued"
    assert agents["code_agent"]["status"] == "queued"
