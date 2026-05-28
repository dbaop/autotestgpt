import json
import tempfile
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"


def _build_test_app(tmp_dir: Path):
    from models import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'phase2_test.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_phase2"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_knowledge_models_exist():
    import models

    assert hasattr(models, "KnowledgeBase")
    assert hasattr(models, "KnowledgeEntry")
    assert hasattr(models.Requirement, "knowledge_base_id")


def test_knowledge_service_search_returns_relevant_entries():
    from models import KnowledgeBase, KnowledgeEntry
    from service.knowledge_service import KnowledgeService

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        kb = KnowledgeBase(name="Core KB", description="core cases")
        db.session.add(kb)
        db.session.flush()

        db.session.add(
            KnowledgeEntry(
                knowledge_base_id=kb.id,
                title="Login verification code",
                content="Cover invalid sms code, expired code, and retry limits.",
                tags=["login", "sms"],
            )
        )
        db.session.add(
            KnowledgeEntry(
                knowledge_base_id=kb.id,
                title="Report export",
                content="Export the report to excel and verify file fields.",
                tags=["report", "export"],
            )
        )
        db.session.commit()

        service = KnowledgeService()
        hits = service.search_entries(
            "Design login sms code test cases with retry validation",
            knowledge_base_ids=[kb.id],
            limit=2,
        )

        assert hits
        assert hits[0]["title"] == "Login verification code"
        if len(hits) > 1:
            assert hits[0]["score"] >= hits[1]["score"]


def test_case_agent_uses_knowledge_context(monkeypatch):
    from agent.case_agent import CaseAgent
    from models import KnowledgeBase, KnowledgeEntry, Requirement

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        kb = KnowledgeBase(name="Login KB", description="login regression")
        db.session.add(kb)
        db.session.flush()

        requirement = Requirement(
            title="Login requirement",
            description="Users can log in with sms verification code.",
            raw_text="Users can log in with sms verification code.",
            status="parsed",
            knowledge_base_id=kb.id,
        )
        db.session.add(requirement)
        db.session.flush()

        db.session.add(
            KnowledgeEntry(
                knowledge_base_id=kb.id,
                title="Verification code exceptions",
                content="Include wrong code, expired code, resend limits, and lock behavior.",
                tags=["login", "sms", "negative"],
            )
        )
        db.session.commit()

        agent = CaseAgent()
        captured = {}

        def _fake_call_llm(prompt, system_prompt=None):
            captured["prompt"] = prompt
            return json.dumps(
                {
                    "test_cases": [
                        {
                            "id": "TC-LOGIN-001",
                            "title": "Verify wrong sms code",
                            "description": "User submits a wrong verification code.",
                            "test_type": "api",
                            "priority": "high",
                            "preconditions": ["User is on login page"],
                            "test_steps": [
                                {
                                    "step": 1,
                                    "action": "Submit a wrong verification code",
                                    "expected": "Login is rejected",
                                }
                            ],
                            "test_data": {"expected_output": "Reject login"},
                            "tags": ["login"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

        monkeypatch.setattr(agent, "call_llm", _fake_call_llm)

        result = agent.process(
            {
                "structured_req": {
                    "title": "Login",
                    "description": "Users can log in with sms verification code.",
                    "business_modules": [{"name": "Login", "priority": "high", "description": "sms login"}],
                },
                "requirement_id": requirement.id,
            }
        )

        assert "Verification code exceptions" in captured["prompt"]
        assert result["metadata"]["knowledge_entry_count"] == 1


def test_knowledge_base_api_can_create_and_search():
    from api import api_blueprint

    app, db = _build_test_app(_local_tmp_dir())
    app.register_blueprint(api_blueprint, url_prefix="/api")
    client = app.test_client()

    create_response = client.post(
        "/api/knowledge-bases",
        json={"name": "Shared KB", "description": "shared reusable testing knowledge"},
    )
    assert create_response.status_code == 201
    knowledge_base = create_response.get_json()["knowledge_base"]

    add_response = client.post(
        f"/api/knowledge-bases/{knowledge_base['id']}/entries",
        json={
            "title": "Captcha fallback",
            "content": "Verify captcha is triggered after repeated login failures.",
            "tags": ["login", "captcha"],
        },
    )
    assert add_response.status_code == 201

    search_response = client.post(
        "/api/knowledge-bases/search",
        json={
            "query": "login failure should trigger captcha",
            "knowledge_base_ids": [knowledge_base["id"]],
            "limit": 3,
        },
    )

    assert search_response.status_code == 200
    payload = search_response.get_json()
    assert payload["items"]
    assert payload["items"][0]["title"] == "Captcha fallback"
