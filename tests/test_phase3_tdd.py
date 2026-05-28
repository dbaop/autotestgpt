import tempfile
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"


def _build_test_app(tmp_dir: Path):
    from models import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'phase3_test.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_phase3"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def _seed_phase3_data(db):
    from models import Requirement, TestCase, TestScript, ExecutionRecord, CodeReviewTask, CodeReviewFinding

    requirement = Requirement(
        title="Login with sms code",
        description="Users can log in using mobile number and sms verification code.",
        raw_text="Users can log in using mobile number and sms verification code.",
        status="executed",
        structured_data={
            "title": "Login with sms code",
            "description": "Users can log in using mobile number and sms verification code.",
            "business_modules": [{"name": "Login", "description": "sms login"}],
        },
    )
    db.session.add(requirement)
    db.session.flush()

    case = TestCase(
        requirement_id=requirement.id,
        title="Reject wrong verification code",
        description="User submits the wrong sms verification code.",
        test_type="api",
        priority="high",
        steps=[{"step": 1, "action": "Submit wrong code", "expected": "Reject login"}],
        expected_results=["Reject login"],
    )
    db.session.add(case)
    db.session.flush()

    script = TestScript(
        test_case_id=case.id,
        script_type="python",
        script_content="def test_login():\n    assert False\n",
        file_path="workspace/scripts/test_login.py",
        status="executed",
    )
    db.session.add(script)
    db.session.flush()

    execution = ExecutionRecord(
        test_script_id=script.id,
        status="failed",
        result_data={"assertion": "expected reject message not found"},
        error_message="AssertionError: expected reject message not found",
        execution_time=1.25,
    )
    db.session.add(execution)

    review_task = CodeReviewTask(
        repo_url="http://git.100credit.cn/group/repo.git",
        branch="main",
        days=7,
        status="completed",
        summary="1 finding detected",
    )
    db.session.add(review_task)
    db.session.flush()

    finding = CodeReviewFinding(
        task_id=review_task.id,
        commit_sha="abc123",
        file_path="backend/login_service.py",
        severity="high",
        title="Missing verification code retry limit",
        detail="Retry limit is not enforced in login verification flow.",
    )
    db.session.add(finding)
    db.session.commit()

    return requirement, case, script, execution, review_task, finding


def test_phase3_models_exist():
    import models

    assert hasattr(models, "DefectCandidate")
    assert hasattr(models, "FinalReport")


def test_defect_service_creates_candidates_from_review_and_execution():
    from service.defect_service import defect_service

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        requirement, _, _, _, review_task, _ = _seed_phase3_data(db)
        result = defect_service.analyze_requirement(requirement.id, review_task.id)

        assert result["defect_count"] >= 2
        titles = [item["title"] for item in result["items"]]
        assert any("retry limit" in title.lower() for title in titles)
        assert any("execution failure" in title.lower() for title in titles)


def test_report_service_builds_html_report():
    from service.defect_service import defect_service
    from service.report_service import report_service

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        requirement, _, _, _, review_task, _ = _seed_phase3_data(db)
        defect_service.analyze_requirement(requirement.id, review_task.id)
        report = report_service.generate_requirement_report(requirement.id, review_task.id)

        assert report.report_type == "requirement_analysis"
        assert "Login with sms code" in report.html_content
        assert "Missing verification code retry limit" in report.html_content
        assert "Reject wrong verification code" in report.html_content


def test_reports_api_returns_report_html():
    from api import api_blueprint
    from service.defect_service import defect_service
    from service.report_service import report_service

    app, db = _build_test_app(_local_tmp_dir())
    app.register_blueprint(api_blueprint, url_prefix="/api")

    with app.app_context():
        requirement, _, _, _, review_task, _ = _seed_phase3_data(db)
        defect_service.analyze_requirement(requirement.id, review_task.id)
        report = report_service.generate_requirement_report(requirement.id, review_task.id)
        report_id = report.id

    client = app.test_client()
    detail_response = client.get(f"/api/reports/{report_id}")
    preview_response = client.get(f"/api/reports/{report_id}/preview")

    assert detail_response.status_code == 200
    assert detail_response.get_json()["report"]["report_type"] == "requirement_analysis"
    assert preview_response.status_code == 200
    assert "text/html" in preview_response.headers["Content-Type"]
