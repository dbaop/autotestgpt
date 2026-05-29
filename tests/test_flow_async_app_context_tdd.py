import sys
import tempfile
import threading
import time
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_flow_app_ctx"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_execute_flow_async_emits_events_inside_background_thread():
    import main
    from flow.test_flow import AutoTestFlow
    from models import AgentEvent, Requirement, db
    from service.flow_service import execute_flow_async

    tmp = _local_tmp_dir()
    main.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp / 'flow_ctx.db'}"

    with main.app.app_context():
        db.drop_all()
        db.create_all()
        requirement = Requirement(
            title="ctx",
            description="d",
            raw_text="d",
            status="pending",
        )
        db.session.add(requirement)
        db.session.commit()
        requirement_id = requirement.id

    class StubFlow:
        def run(self, flow_data):
            from service.agent_event_service import emit_agent_event

            emit_agent_event(requirement_id, "ReqAgent", "started", "thread ctx ok")
            return {"status": "success", "requirement_id": requirement_id}

    done = threading.Event()
    errors: list[str] = []

    def worker():
        try:
            execute_flow_async(StubFlow(), {"requirement_id": requirement_id}, requirement_id)
        except Exception as exc:
            errors.append(str(exc))
        finally:
            done.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert done.wait(10), "flow thread did not finish"
    assert not errors, errors

    with main.app.app_context():
        events = AgentEvent.query.filter_by(requirement_id=requirement_id).all()
        assert any(event.message == "thread ctx ok" for event in events)
        requirement = db.session.get(Requirement, requirement_id)
        assert requirement.status == "completed"
