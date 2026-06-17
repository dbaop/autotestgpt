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
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'req_parse_context_test.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_req_parse_context"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_build_requirement_parse_context_from_demand():
    from models import Requirement, TestCase
    from service.knowledge_service import KnowledgeService

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
            status="pending",
        )
        db.session.add(current_req)
        db.session.commit()

        service = KnowledgeService()
        context = service.build_requirement_parse_context(
            "Users can log in with sms verification code.",
            exclude_requirement_id=current_req.id,
            limit=3,
        )

        assert "SMS login" in context["prompt_text"]
        assert "Reject wrong sms verification code" in context["prompt_text"]
        assert len(context["historical_requirements"]) >= 1
        assert len(context["historical_test_cases"]) >= 1


def test_req_agent_process_injects_historical_context(monkeypatch):
    from agent.req_agent import ReqAgent
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
            status="pending",
        )
        db.session.add(current_req)
        db.session.commit()

        agent = ReqAgent()
        captured = {}

        def _fake_call_llm(prompt, system_prompt=None):
            captured["prompt"] = prompt
            return json.dumps(
                {
                    "title": "Login",
                    "description": "Users can log in with sms verification code.",
                    "business_modules": [{"name": "Login", "description": "sms login", "priority": "high"}],
                    "test_points": [{"id": "TP-001", "description": "Wrong code rejected", "type": "functional", "priority": "high"}],
                },
                ensure_ascii=False,
            )

        monkeypatch.setattr(agent, "call_llm", _fake_call_llm)

        result = agent.process(
            {
                "demand": "Users can log in with sms verification code.",
                "requirement_id": current_req.id,
            }
        )

        assert "Reject wrong sms verification code" in captured["prompt"]
        assert "SMS login" in captured["prompt"]
        assert result["metadata"]["historical_test_case_count"] >= 1
        assert result["metadata"]["historical_requirement_count"] >= 1


def test_orchestrator_parsing_instruction_includes_historical_context():
    from agent.orchestrator import ConversationOrchestrator
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
            status="pending",
        )
        db.session.add(current_req)
        db.session.commit()

        orchestrator = ConversationOrchestrator()
        instruction = orchestrator._build_system_instruction("parsing", current_req)

        assert "Reject wrong sms verification code" in instruction
        assert "Historical similar requirements" in instruction
