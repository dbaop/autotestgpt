import tempfile
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"


def _build_test_app(tmp_dir: Path):
    from models import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'phase4_autofix.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_phase4_autofix"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def _seed_autofix_data(db):
    from models import Requirement, DefectCandidate

    requirement = Requirement(
        title="Login with sms code",
        description="Users can log in with mobile number and verification code.",
        raw_text="Users can log in with mobile number and verification code.",
        status="executed",
    )
    db.session.add(requirement)
    db.session.flush()

    review_defect = DefectCandidate(
        requirement_id=requirement.id,
        source_type="code_review",
        severity="high",
        title="Code review risk: Missing verification code retry limit",
        summary="Retry limit is not enforced in login verification flow.",
        evidence={
            "file_path": "backend/login_service.py",
            "commit_sha": "abc123",
        },
    )
    execution_defect = DefectCandidate(
        requirement_id=requirement.id,
        source_type="execution",
        severity="high",
        title="Execution failure: UI login opens center home",
        summary="Timeout waiting for home page selector",
        evidence={
            "script_id": 11,
            "execution_record_id": 22,
        },
    )
    db.session.add(review_defect)
    db.session.add(execution_defect)
    db.session.commit()

    return requirement, review_defect, execution_defect


def test_phase4_models_exist():
    import models

    assert hasattr(models, "FixSuggestion")


def test_autofix_service_generates_structured_suggestions():
    from service.autofix_service import autofix_service

    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        requirement, _, _ = _seed_autofix_data(db)
        result = autofix_service.generate_suggestions(requirement.id)

        assert result["suggestion_count"] == 2
        first = result["items"][0]
        assert "title" in first
        assert "suggested_action" in first
        assert "patch_preview" in first
        assert "backend/login_service.py" in "".join(first.get("target_files", [])) or result["items"][1]["target_files"]


def test_autofix_api_returns_suggestions():
    from api import api_blueprint

    app, db = _build_test_app(_local_tmp_dir())
    app.register_blueprint(api_blueprint, url_prefix="/api")

    with app.app_context():
        requirement, _, _ = _seed_autofix_data(db)
        requirement_id = requirement.id

    client = app.test_client()
    response = client.post("/api/autofix/suggestions", json={"requirement_id": requirement_id})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["suggestion_count"] == 2
    assert payload["items"][0]["mode"] == "suggestion_only"
