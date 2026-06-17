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
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'historical_context_test.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_historical_context"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_search_historical_requirements_returns_similar_past_requirements():
    from models import Requirement
    from service.knowledge_service import KnowledgeService

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        old_req = Requirement(
            title="SMS login",
            description="Users log in with mobile sms verification code.",
            raw_text="sms login",
            status="cases_generated",
            structured_data={
                "title": "SMS login",
                "description": "Users log in with mobile sms verification code.",
                "business_modules": [{"name": "Login", "description": "sms login module"}],
            },
        )
        unrelated = Requirement(
            title="Report export",
            description="Export monthly sales report to excel.",
            raw_text="report export",
            status="cases_generated",
        )
        db.session.add_all([old_req, unrelated])
        db.session.commit()

        service = KnowledgeService()
        hits = service.search_historical_requirements(
            {
                "title": "Login",
                "description": "Users can log in with sms verification code.",
                "business_modules": [{"name": "Login", "description": "sms login"}],
            },
            limit=3,
        )

        assert hits
        assert hits[0]["title"] == "SMS login"
        assert hits[0]["source_type"] == "historical_requirement"
        assert all(item["title"] != "Report export" for item in hits[:1])


def test_search_historical_test_cases_returns_related_cases():
    from models import Requirement, TestCase
    from service.knowledge_service import KnowledgeService

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        req = Requirement(
            title="SMS login",
            description="Users log in with sms verification code.",
            raw_text="sms login",
            status="cases_generated",
        )
        db.session.add(req)
        db.session.flush()

        db.session.add(
            TestCase(
                requirement_id=req.id,
                title="Reject wrong sms verification code",
                description="Submit an invalid sms code during login.",
                test_type="api",
                priority="high",
                methodology="error_guessing",
                steps=[{"step": 1, "action": "Submit wrong code", "expected": "Login rejected"}],
                expected_results=["Login rejected"],
            )
        )
        db.session.add(
            TestCase(
                requirement_id=req.id,
                title="Export report columns",
                description="Verify excel export columns.",
                test_type="api",
                priority="medium",
                steps=[{"step": 1, "action": "Export report", "expected": "Excel downloaded"}],
                expected_results=["Excel downloaded"],
            )
        )
        db.session.commit()

        service = KnowledgeService()
        hits = service.search_historical_test_cases(
            {
                "title": "Login",
                "description": "Users can log in with sms verification code.",
            },
            limit=3,
        )

        assert hits
        assert hits[0]["title"] == "Reject wrong sms verification code"
        assert hits[0]["source_type"] == "historical_test_case"
        assert hits[0]["requirement_id"] == req.id


def test_build_case_context_merges_kb_and_historical_sources():
    from models import KnowledgeBase, KnowledgeEntry, Requirement, TestCase
    from service.knowledge_service import KnowledgeService

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        kb = KnowledgeBase(name="Login KB", description="login knowledge")
        db.session.add(kb)
        db.session.flush()

        db.session.add(
            KnowledgeEntry(
                knowledge_base_id=kb.id,
                title="Verification code exceptions",
                content="Include wrong code, expired code, and resend limits.",
                tags=["login", "sms"],
            )
        )

        old_req = Requirement(
            title="SMS login",
            description="Users log in with sms verification code.",
            raw_text="sms login",
            status="cases_generated",
            structured_data={"title": "SMS login", "description": "Users log in with sms verification code."},
        )
        db.session.add(old_req)
        db.session.flush()

        db.session.add(
            TestCase(
                requirement_id=old_req.id,
                title="Reject wrong sms verification code",
                description="Submit an invalid sms code during login.",
                test_type="api",
                priority="high",
                steps=[{"step": 1, "action": "Submit wrong code", "expected": "Login rejected"}],
                expected_results=["Login rejected"],
            )
        )

        current_req = Requirement(
            title="Login requirement",
            description="Users can log in with sms verification code.",
            raw_text="Users can log in with sms verification code.",
            status="parsed",
            knowledge_base_id=kb.id,
        )
        db.session.add(current_req)
        db.session.commit()

        service = KnowledgeService()
        context = service.build_case_context(
            {
                "title": "Login",
                "description": "Users can log in with sms verification code.",
                "business_modules": [{"name": "Login", "description": "sms login"}],
            },
            knowledge_base_ids=[kb.id],
            exclude_requirement_id=current_req.id,
            limit=2,
        )

        assert len(context["knowledge_entries"]) >= 1
        assert len(context["historical_requirements"]) >= 1
        assert len(context["historical_test_cases"]) >= 1
        assert "Verification code exceptions" in context["prompt_text"]
        assert "SMS login" in context["prompt_text"]
        assert "Reject wrong sms verification code" in context["prompt_text"]
        assert "Historical similar requirements" in context["prompt_text"]
        assert "Historical similar test cases" in context["prompt_text"]


def test_build_case_context_excludes_current_requirement():
    from models import Requirement
    from service.knowledge_service import KnowledgeService

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        current_req = Requirement(
            title="SMS login",
            description="Users log in with sms verification code.",
            raw_text="sms login",
            status="parsed",
            structured_data={"title": "SMS login", "description": "Users log in with sms verification code."},
        )
        db.session.add(current_req)
        db.session.commit()

        service = KnowledgeService()
        hits = service.search_historical_requirements(
            {"title": "SMS login", "description": "Users log in with sms verification code."},
            exclude_requirement_id=current_req.id,
            limit=3,
        )

        assert hits == []


def test_case_agent_injects_historical_context_into_prompt(monkeypatch):
    from agent.case_agent import CaseAgent
    from models import Requirement, TestCase

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        old_req = Requirement(
            title="SMS login",
            description="Users log in with sms verification code.",
            raw_text="sms login",
            status="cases_generated",
        )
        db.session.add(old_req)
        db.session.flush()

        db.session.add(
            TestCase(
                requirement_id=old_req.id,
                title="Reject wrong sms verification code",
                description="Submit an invalid sms code during login.",
                test_type="api",
                priority="high",
                steps=[{"step": 1, "action": "Submit wrong code", "expected": "Login rejected"}],
                expected_results=["Login rejected"],
            )
        )

        current_req = Requirement(
            title="Login requirement",
            description="Users can log in with sms verification code.",
            raw_text="Users can log in with sms verification code.",
            status="parsed",
        )
        db.session.add(current_req)
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
                "requirement_id": current_req.id,
            }
        )

        assert "Reject wrong sms verification code" in captured["prompt"]
        assert "SMS login" in captured["prompt"]
        assert result["metadata"]["historical_test_case_count"] >= 1
        assert result["metadata"]["historical_requirement_count"] >= 1
