import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"


def _build_test_app(tmp_dir: Path):
    from models import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'ui_heal_test.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_ui_heal"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def test_element_to_selector_prefers_stable_attributes():
    from service.ui_heal_service import element_to_selector

    assert element_to_selector({"tag": "input", "id": "username"}) == "#username"
    assert element_to_selector({"tag": "button", "data_testid": "login-btn"}) == "[data-testid='login-btn']"
    assert element_to_selector({"tag": "input", "name": "phone"}) == "input[name='phone']"


def test_apply_fixes_to_dsl_replaces_selectors_in_when_and_then():
    from service.ui_heal_service import apply_fixes_to_dsl

    dsl = {
        "given": {"action": "navigate", "url": "/login"},
        "when": [{"action": "fill", "selector": "#wrong-phone", "value": "13800138000"}],
        "then": [{"type": "element_visible", "selector": "#wrong-phone"}],
    }
    fixed = apply_fixes_to_dsl(
        dsl,
        [{"old_selector": "#wrong-phone", "new_selector": "#phone", "reason": "matched placeholder"}],
    )

    assert fixed["when"][0]["selector"] == "#phone"
    assert fixed["then"][0]["selector"] == "#phone"


def test_suggest_selector_fixes_matches_input_by_placeholder():
    from service.ui_heal_service import suggest_selector_fixes

    dsl = {
        "when": [{"action": "fill", "selector": "#wrong-phone", "value": "13800138000"}],
        "then": [],
    }
    result = {
        "result": {
            "steps": [{"action": "fill", "selector": "#wrong-phone", "ok": False, "error": "not found"}],
            "assertions": [],
        }
    }
    snapshot = {
        "ok": True,
        "elements": [
            {
                "tag": "input",
                "id": "phone",
                "placeholder": "请输入手机号",
                "type": "tel",
                "visible": True,
            }
        ],
    }

    fixes = suggest_selector_fixes(dsl, result, snapshot)
    assert fixes
    assert fixes[0]["new_selector"] == "#phone"


def test_run_ui_dsl_with_self_heal_retries_after_fix():
    from service.ui_heal_service import run_ui_dsl_with_self_heal

    dsl = {
        "given": {"action": "navigate", "url": "/login"},
        "when": [{"action": "click", "selector": "#wrong-login", "value": ""}],
        "then": [{"type": "element_visible", "selector": "body"}],
    }
    failed = {
        "status": "failed",
        "execution_time": 1.0,
        "error": "selector not found",
        "report_path": None,
        "screenshots": [],
        "result": {
            "steps": [{"action": "click", "selector": "#wrong-login", "ok": False, "error": "not found"}],
            "assertions": [],
            "passed": False,
        },
    }
    healed = {
        "status": "success",
        "execution_time": 0.8,
        "error": None,
        "report_path": None,
        "screenshots": ["after.png"],
        "result": {"steps": [], "assertions": [], "passed": True},
    }
    snapshot = {
        "ok": True,
        "elements": [{"tag": "button", "id": "login-btn", "text": "登录", "visible": True}],
    }

    with patch("service.ui_heal_service.run_ui_dsl", side_effect=[failed, healed]) as run_mock, patch(
        "service.ui_heal_service.get_browser_probe"
    ) as probe_mock:
        probe = MagicMock()
        probe.is_connected = True
        probe.snapshot.return_value = snapshot
        probe_mock.return_value = probe

        result = run_ui_dsl_with_self_heal(dsl, base_url="https://example.com", screenshot_prefix="ui_1")

    assert run_mock.call_count == 2
    assert result["status"] == "success"
    assert result["heal_attempted"] is True
    assert result["healed"] is True
    assert result["heal_fixes"][0]["new_selector"] == "#login-btn"
    assert result["fixed_dsl"]["when"][0]["selector"] == "#login-btn"


def test_recovery_steps_run_before_step_failure():
    from service.ui_runner_service import _run_when_step

    probe = MagicMock()
    probe.fill.side_effect = [
        {"ok": False, "error": "not found"},
        {"ok": True},
    ]

    step = {
        "action": "fill",
        "selector": "#wrong-phone",
        "value": "13800138000",
        "recovery_steps": [{"action": "fill", "selector": "#phone", "value": "13800138000"}],
    }
    result = _run_when_step(probe, step)

    assert result["ok"] is True
    assert result.get("via") == "recovery_steps"
    assert probe.fill.call_count == 2


def test_requirement_detail_includes_heal_metadata():
    from models import Requirement, TestCase, TestScript, ExecutionRecord
    from service.requirement_service import get_requirement_detail

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        req = Requirement(title="Login", description="login", raw_text="login", status="executed")
        db.session.add(req)
        db.session.flush()
        case = TestCase(requirement_id=req.id, title="Login case", test_type="ui")
        db.session.add(case)
        db.session.flush()
        script = TestScript(
            test_case_id=case.id,
            script_type="ui_cdp",
            script_content="{}",
            file_path="ui_case_1.json",
        )
        db.session.add(script)
        db.session.flush()
        db.session.add(
            ExecutionRecord(
                test_script_id=script.id,
                status="success",
                result_data={
                    "passed": True,
                    "heal_attempted": True,
                    "healed": True,
                    "heal_fixes": [{"old_selector": "#wrong-login", "new_selector": "#login-btn"}],
                },
                execution_time=0.8,
            )
        )
        db.session.commit()

        payload = get_requirement_detail(req.id)
        assert payload["executions"][0]["healed"] is True
        assert payload["executions"][0]["heal_fixes"][0]["new_selector"] == "#login-btn"


def test_frontend_requirement_detail_shows_self_heal_panel():
    source = Path("autotestgptFront/src/pages/RequirementDetail.tsx").read_text(encoding="utf-8")
    assert "heal_attempted" in source
    assert "自愈成功" in source
    assert "heal_fixes" in source


def test_build_heal_sse_event_formats_messages():
    from service.ui_heal_service import build_heal_sse_event

    attempting = build_heal_sse_event(12, "attempting")
    assert attempting["type"] == "heal_event"
    assert attempting["script_id"] == 12
    assert "snapshot" in attempting["message"]

    success = build_heal_sse_event(
        12,
        "success",
        healed=True,
        heal_fixes=[{"old_selector": "#wrong-login", "new_selector": "#login-btn"}],
    )
    assert success["healed"] is True
    assert "#wrong-login" in success["message"]


def test_orchestrator_emits_heal_events_on_ui_failure(monkeypatch):
    from agent.orchestrator import ConversationOrchestrator
    from models import Conversation, Requirement, TestCase, TestScript

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        req = Requirement(
            title="Login",
            description="login",
            raw_text="login",
            status="code_generated",
            structured_data={"test_environment": {"test_url": "https://example.com"}},
        )
        db.session.add(req)
        db.session.flush()
        conv = Conversation(title="Login conv", requirement_id=req.id)
        db.session.add(conv)
        db.session.flush()
        case = TestCase(requirement_id=req.id, title="Login case", test_type="ui")
        db.session.add(case)
        db.session.flush()
        script = TestScript(
            test_case_id=case.id,
            script_type="ui_cdp",
            script_content=json.dumps(
                {
                    "given": {"action": "navigate", "url": "/login"},
                    "when": [{"action": "click", "selector": "#wrong-login"}],
                    "then": [{"type": "element_visible", "selector": "body"}],
                }
            ),
            file_path="ui_case_1.json",
        )
        db.session.add(script)
        db.session.commit()

        failed = {
            "status": "failed",
            "execution_time": 1.0,
            "error": "selector not found",
            "report_path": None,
            "screenshots": [],
            "result": {
                "steps": [{"action": "click", "selector": "#wrong-login", "ok": False}],
                "assertions": [],
                "passed": False,
            },
        }
        healed = {
            "status": "success",
            "execution_time": 0.8,
            "error": None,
            "report_path": None,
            "screenshots": [],
            "result": {"steps": [], "assertions": [], "passed": True},
            "heal_attempted": True,
            "healed": True,
            "heal_fixes": [{"old_selector": "#wrong-login", "new_selector": "#login-btn"}],
            "fixed_dsl": {"when": [{"action": "click", "selector": "#login-btn"}]},
        }

        monkeypatch.setattr("service.ui_runner_service.run_ui_dsl", lambda *args, **kwargs: failed)
        monkeypatch.setattr(
            "service.ui_heal_service.attempt_ui_dsl_heal",
            lambda *args, **kwargs: {
                "result": healed,
                "heal_attempted": True,
                "healed": True,
                "heal_fixes": healed["heal_fixes"],
                "fixed_dsl": healed["fixed_dsl"],
                "heal_error": None,
            },
        )

        orchestrator = ConversationOrchestrator()
        events = list(orchestrator._run_execution(conv.id, req))
        heal_events = [event for event in events if event.get("type") == "heal_event"]

        assert len(heal_events) >= 2
        assert heal_events[0]["phase"] == "attempting"
        assert heal_events[-1]["phase"] == "success"


def test_frontend_chat_shows_self_heal_events():
    source = Path("autotestgptFront/src/pages/Chat.tsx").read_text(encoding="utf-8")
    assert "heal_event" in source
    assert "healEvents" in source
    assert "自愈中" in source


def test_flow_service_retry_persists_healed_dsl():
    from models import Requirement, TestCase, TestScript
    from service.flow_service import retry_script

    app, db = _build_test_app(_local_tmp_dir())

    with app.app_context():
        req = Requirement(
            title="Login",
            description="login",
            raw_text="login",
            status="executed",
            structured_data={"test_environment": {"test_url": "https://example.com"}},
        )
        db.session.add(req)
        db.session.flush()
        case = TestCase(requirement_id=req.id, title="Login case", test_type="ui")
        db.session.add(case)
        db.session.flush()
        script = TestScript(
            test_case_id=case.id,
            script_type="ui_cdp",
            script_content=json.dumps(
                {
                    "given": {"action": "navigate", "url": "/login"},
                    "when": [{"action": "click", "selector": "#wrong-login"}],
                    "then": [{"type": "element_visible", "selector": "body"}],
                }
            ),
            file_path="ui_case_1.json",
        )
        db.session.add(script)
        db.session.commit()

        healed_payload = {
            "status": "success",
            "execution_time": 0.5,
            "error": None,
            "report_path": None,
            "screenshots": [],
            "result": {"steps": [], "assertions": [], "passed": True},
            "heal_attempted": True,
            "healed": True,
            "heal_fixes": [{"old_selector": "#wrong-login", "new_selector": "#login-btn"}],
            "fixed_dsl": {
                "given": {"action": "navigate", "url": "/login"},
                "when": [{"action": "click", "selector": "#login-btn"}],
                "then": [{"type": "element_visible", "selector": "body"}],
            },
        }

        with patch("service.ui_heal_service.run_ui_dsl_with_self_heal", return_value=healed_payload):
            response = retry_script(script.id)

        db.session.refresh(script)
        saved = json.loads(script.script_content)
        assert response["status"] == "success"
        assert saved["when"][0]["selector"] == "#login-btn"
