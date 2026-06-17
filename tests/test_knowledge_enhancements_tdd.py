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
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'knowledge_enhancements_test.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_knowledge_enhancements"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_search_all_sources_merges_kb_and_historical():
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
        db.session.commit()

        service = KnowledgeService()
        payload = service.search_all_sources(
            "login sms verification code",
            knowledge_base_ids=[kb.id],
            limit=5,
        )

        source_types = {item["source_type"] for item in payload["items"]}
        assert "knowledge_entry" in source_types
        assert "historical_requirement" in source_types
        assert "historical_test_case" in source_types


def test_tool_search_knowledge_base_includes_historical_results():
    from agent.tools import tool_search_knowledge_base
    from models import Requirement, TestCase

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
                steps=[{"step": 1, "action": "Submit wrong code", "expected": "Login rejected"}],
                expected_results=["Login rejected"],
            )
        )
        db.session.commit()

        results = tool_search_knowledge_base("login sms verification code", limit=5)
        source_types = {item["source_type"] for item in results}
        assert "historical_test_case" in source_types
        assert "historical_requirement" in source_types


def test_index_requirement_writes_requirement_and_cases_to_kb():
    from models import KnowledgeBase, KnowledgeEntry, Requirement, TestCase
    from service.knowledge_service import KnowledgeService, AUTO_HISTORY_KB_NAME

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        bound_kb = KnowledgeBase(name="Project KB", description="project")
        db.session.add(bound_kb)
        db.session.flush()

        requirement = Requirement(
            title="SMS login",
            description="Users log in with sms verification code.",
            raw_text="sms login",
            status="completed",
            knowledge_base_id=bound_kb.id,
            structured_data={"title": "SMS login", "description": "Users log in with sms verification code."},
        )
        db.session.add(requirement)
        db.session.flush()

        db.session.add(
            TestCase(
                requirement_id=requirement.id,
                title="Reject wrong sms verification code",
                description="Submit an invalid sms code during login.",
                test_type="api",
                priority="high",
                methodology="error_guessing",
                steps=[{"step": 1, "action": "Submit wrong code", "expected": "Login rejected"}],
                expected_results=["Login rejected"],
            )
        )
        db.session.commit()

        service = KnowledgeService()
        result = service.index_requirement(requirement.id)

        assert result["entry_count"] >= 2
        assert KnowledgeBase.query.filter_by(name=AUTO_HISTORY_KB_NAME).first() is not None

        bound_refs = {
            entry.source_ref
            for entry in KnowledgeEntry.query.filter_by(knowledge_base_id=bound_kb.id).all()
        }
        assert f"requirement:{requirement.id}" in bound_refs
        assert any(ref.startswith(f"requirement:{requirement.id}:case:") for ref in bound_refs)

        service.index_requirement(requirement.id)
        assert KnowledgeEntry.query.filter_by(knowledge_base_id=bound_kb.id).count() == result["entry_count"]


def test_search_entries_uses_vector_similarity_when_enabled(monkeypatch):
    from models import KnowledgeBase, KnowledgeEntry
    from service.knowledge_service import KnowledgeService

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        kb = KnowledgeBase(name="Vector KB", description="vector")
        db.session.add(kb)
        db.session.flush()

        db.session.add(
            KnowledgeEntry(
                knowledge_base_id=kb.id,
                title="Login sms code",
                content="Wrong code, expired code, resend limits.",
                tags=["login"],
                embedding=[1.0, 0.0, 0.0],
            )
        )
        db.session.add(
            KnowledgeEntry(
                knowledge_base_id=kb.id,
                title="Report export",
                content="Export monthly sales report to excel.",
                tags=["report"],
                embedding=[0.0, 1.0, 0.0],
            )
        )
        db.session.commit()

        service = KnowledgeService()

        def _fake_embed(text: str):
            if "login" in text.lower() or "sms" in text.lower():
                return [0.95, 0.05, 0.0]
            return [0.0, 1.0, 0.0]

        monkeypatch.setattr("service.embedding_service.embedding_service.embed_text", _fake_embed)
        monkeypatch.setattr("service.embedding_service.embedding_service.is_enabled", lambda: True)

        hits = service.search_entries(
            "login sms verification code",
            knowledge_base_ids=[kb.id],
            limit=2,
        )

        assert hits
        assert hits[0]["title"] == "Login sms code"
        assert hits[0].get("score_method") in ("vector", "hybrid")
