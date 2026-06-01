import io
import tempfile
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"


def _build_test_app(tmp_dir: Path):
    from models import db
    from api import api_blueprint

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'phase5_test.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    app.register_blueprint(api_blueprint, url_prefix="/api")

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_phase5"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_requirement_file_upload_creates_requirement():
    app, _db = _build_test_app(_local_tmp_dir())
    client = app.test_client()

    response = client.post(
        "/api/requirements/import",
        data={
            "title": "Imported login requirement",
            "file": (io.BytesIO("Login should support sms verification".encode("utf-8")), "login.txt"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["requirement"]["title"] == "Imported login requirement"
    assert "sms verification" in payload["requirement"]["description"]


def test_review_service_uses_repo_url_workspace(monkeypatch):
    from service.review_service import run_review_task

    class DummyTask:
        def __init__(self):
            self.id = 21
            self.repo_url = "http://git.100credit.cn/group/demo-repo.git"
            self.repo_path = None
            self.repo_type = "remote"
            self.branch = "main"
            self.days = 5
            self.status = "pending"
            self.summary = None
            self.error_message = None
            self.started_at = None
            self.finished_at = None

    task = DummyTask()
    added = []
    seen_cwds = []

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
    monkeypatch.setattr("service.review_service._resolve_repo_path", lambda t: "workspace/repos/demo-repo")

    def _fake_git(cmd, cwd=None):
        seen_cwds.append(cwd)
        if "log" in cmd:
            return "abc123|alice|2026-05-25|fix login bug"
        if "show" in cmd:
            return "diff --git a/a.py b/a.py\n+print('ok')"
        return ""

    monkeypatch.setattr("service.review_service._run_git", _fake_git)

    result = run_review_task(21)

    assert result["status"] == "completed"
    assert seen_cwds
    assert all(cwd == "workspace/repos/demo-repo" for cwd in seen_cwds)
    assert added
