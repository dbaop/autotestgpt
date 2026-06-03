import sys
import tempfile
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
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'chat_phase5.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    app.register_blueprint(api_blueprint, url_prefix="/api")

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_chat_phase5"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_conversation_agent_context_returns_summary_not_full_events():
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import Conversation, Requirement
        from service.agent_event_service import emit_agent_event

        requirement = Requirement(
            title="登录流程",
            description="会员登录",
            raw_text="会员登录",
            structured_data={"test_environment": {"test_url": "https://t.example"}},
            status="parsed",
        )
        db.session.add(requirement)
        db.session.flush()
        emit_agent_event(
            requirement.id,
            "System",
            "waiting_user",
            "Waiting for user: 验证码怎么处理？",
        )
        conv = Conversation(title="需求对话", requirement_id=requirement.id)
        db.session.add(conv)
        db.session.commit()
        conv_id = conv.id
        requirement_id = requirement.id

    response = app.test_client().get(f"/api/conversations/{conv_id}/agent-context")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["requirement_id"] == requirement_id
    assert payload["headline"]
    assert payload["workbench_path"] == f"/workbench/{requirement_id}"
    assert any("验证码" in q["message"] for q in payload["pending_questions"])
    assert "events" not in payload


def test_send_message_emits_waiting_user_and_returns_agent_context():
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import AgentEvent, Conversation, Requirement

        requirement = Requirement(
            title="探活",
            description="d",
            raw_text="d",
            status="pending",
        )
        db.session.add(requirement)
        db.session.flush()
        conv = Conversation(title="c", requirement_id=requirement.id)
        db.session.add(conv)
        db.session.commit()
        conv_id = conv.id
        requirement_id = requirement.id

    with app.app_context():
        from unittest.mock import patch

        with patch("agent.chat_agent.process_user_message", return_value={"success": True}):
            response = app.test_client().post(
                f"/api/conversations/{conv_id}/messages",
                json={"content": "测试环境验证码怎么处理？"},
            )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["agent_context"]["requirement_id"] == requirement_id
    assert any("验证码" in q["message"] for q in payload["agent_context"]["pending_questions"])

    with app.app_context():
        from models import AgentEvent

        events = AgentEvent.query.filter_by(requirement_id=requirement_id, event_type="waiting_user").all()
        assert len(events) >= 1


def test_unlinked_chat_message_creates_requirement_and_starts_flow():
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import Conversation

        conv = Conversation(title="临时对话")
        db.session.add(conv)
        db.session.commit()
        conv_id = conv.id

    demand = "请测试会员中心登录，自动补齐测试环境后开始执行。"

    from unittest.mock import patch

    with patch("agent.chat_agent.process_user_message", return_value={"success": True}), \
            patch("service.flow_service.enqueue_requirement_flow", return_value={"flow_id": "flow-1", "status": "processing"}, create=True) as enqueue:
        response = app.test_client().post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": demand},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["started_from_chat"] is True
    assert payload["requirement_id"]
    assert payload["agent_context"]["requirement_id"] == payload["requirement_id"]
    enqueue.assert_called_once()

    with app.app_context():
        from models import Conversation, Requirement

        updated_conv = db.session.get(Conversation, conv_id)
        requirement = db.session.get(Requirement, updated_conv.requirement_id)
        assert requirement is not None
        assert requirement.raw_text == demand
        assert requirement.status == "pending"
        assert updated_conv.title.startswith(f"需求 #{requirement.id}")
