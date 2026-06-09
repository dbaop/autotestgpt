"""
Flow application service.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

from agent.exec_agent import ExecAgent
from flow.test_flow import AutoTestFlow
from models import Conversation, ExecutionRecord, Message, Requirement, TestCase, TestScript, db
from service.errors import NotFoundError, ValidationError


_executor = ThreadPoolExecutor(max_workers=4)
_flow_registry: dict[int, dict[str, Any]] = {}
_registry_lock = threading.Lock()

# Cooperative cancellation: requirement_ids the user requested to stop.
_cancel_requests: set[int] = set()
_cancel_lock = threading.Lock()


def request_cancel(requirement_id: int) -> None:
    """Mark a running flow for cooperative cancellation."""
    with _cancel_lock:
        _cancel_requests.add(requirement_id)


def is_cancelled(requirement_id: int) -> bool:
    """Whether a cancellation was requested for this requirement."""
    with _cancel_lock:
        return requirement_id in _cancel_requests


def clear_cancel(requirement_id: int) -> None:
    """Clear any pending cancellation flag (called when a flow run ends)."""
    with _cancel_lock:
        _cancel_requests.discard(requirement_id)


def _now():
    return datetime.now(timezone.utc)


def _resolve_flask_app():
    from flask import has_app_context, current_app

    if has_app_context():
        return current_app._get_current_object()
    from main import app

    return app


# ---------------------------------------------------------------------------
# Legacy flow execution (used only when CONVERSATION_FLOW_ENABLED=False)
# ---------------------------------------------------------------------------

def _execute_flow_async_impl(flow, flow_data, requirement_id):
    flow_id = str(id(flow))
    try:
        with _registry_lock:
            _flow_registry[requirement_id] = {"flow_id": flow_id, "status": "running"}
        result = flow.run(flow_data)
        requirement = db.session.get(Requirement, requirement_id)
        if requirement:
            requirement.status = "completed" if isinstance(result, dict) and result.get("status") == "success" else "error"
            requirement.execution_progress = result
            db.session.commit()
        with _registry_lock:
            _flow_registry[requirement_id] = {"flow_id": flow_id, "status": result.get("status", "error")}
    except Exception as e:
        db.session.rollback()
        requirement = db.session.get(Requirement, requirement_id)
        if requirement:
            requirement.status = "error"
            db.session.commit()
        with _registry_lock:
            _flow_registry[requirement_id] = {"flow_id": flow_id, "status": "error", "error": str(e)}
    finally:
        remove = getattr(db.session, "remove", None)
        if callable(remove):
            remove()


def execute_flow_async(flow, flow_data, requirement_id):
    """在线程池中执行时必须持有 Flask app context。"""
    flask_app = _resolve_flask_app()
    with flask_app.app_context():
        _execute_flow_async_impl(flow, flow_data, requirement_id)


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------

def _extract_doc_from_url(url: str) -> dict | None:
    """Try to extract document content from *url* via CDP browser probe."""
    try:
        from service.browser_probe_service import get_browser_probe
        probe = get_browser_probe()
        nav = probe.navigate(url)
        if not nav.get("ok"):
            logger.warning("CDP navigate failed for %s: %s", url, nav.get("error", "unknown"))
            return None
        result = probe.extract_content()
        if result.get("ok") and result.get("length", 0) > 50:
            logger.info("CDP extracted %d chars from %s", result["length"], url)
            content = (
                f"【来源】{result.get('url', url)}\n"
                f"【标题】{result.get('title', '')}\n\n"
                f"{result.get('content', '')}"
            )
            return {
                "content": content,
                "url": url,
                "title": result.get("title", ""),
                "extracted_at": _now().isoformat(),
            }
        logger.warning("CDP extracted too little content from %s: %d chars", url, result.get("length", 0))
        return None
    except Exception as exc:
        logger.warning("CDP extraction failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Orchestrator thread helper — always use app context
# ---------------------------------------------------------------------------

def _run_orchestrator_in_thread(fn, conversation_id: int, requirement_id: int):
    """Execute an orchestrator generator in a background thread with app context."""
    from service.sse_service import push_sse_event, broadcast_error

    flask_app = _resolve_flask_app()
    with flask_app.app_context():
        try:
            for event in fn():
                push_sse_event(conversation_id, event)
        except Exception as exc:
            logger.exception("Orchestrator flow failed for requirement %d", requirement_id)
            broadcast_error(conversation_id, str(exc))
            try:
                req = db.session.get(Requirement, requirement_id)
                if req:
                    req.status = "error"
                    req.execution_progress = (req.execution_progress or {}) | {
                        "error": str(exc)[:500],
                        "failed_at": _now().isoformat(),
                    }
                    db.session.commit()
            except Exception:
                pass
        finally:
            clear_cancel(requirement_id)
            remove = getattr(db.session, "remove", None)
            if callable(remove):
                remove()


# ---------------------------------------------------------------------------
# start_flow / resume_flow
# ---------------------------------------------------------------------------

def start_flow(data: dict):
    demand = (data.get("demand") or "").strip()
    doc_url = (data.get("doc_url") or "").strip()

    test_environment = data.get("test_environment") or {}
    structured_seed: dict = {"test_environment": test_environment}
    original_document = None

    # 持久化前端预设的代码 review 配置（orchestrator 模式下的确认 gate 与收尾会读取）
    review_config = data.get("review") or data.get("review_config")
    if review_config:
        structured_seed["review"] = {
            "enabled": True,
            "repo_url": review_config.get("repo_url", ""),
            "repo_path": review_config.get("repo_path", ""),
            "branch": review_config.get("branch", "main"),
            "days": int(review_config.get("days") or 7),
        }

    # 如果提供了文档 URL（钉钉/飞书/语雀等），通过 CDP 自动提取内容
    is_doc_url_mode = bool(doc_url and not demand)
    if is_doc_url_mode:
        # 先创建占位需求立即返回，避免 CDP 提取阻塞 HTTP 响应。
        # 提取在后台线程完成后再更新需求内容并启动 orchestrator。
        demand = f"请打开以下文档链接并提取测试需求:\n{doc_url}"
        original_document = {"url": doc_url, "needs_retry": True}

    if original_document:
        structured_seed["original_document"] = original_document
    if doc_url:
        structured_seed["doc_url"] = doc_url

    if not demand:
        raise ValidationError("Please provide `demand` or `doc_url` field")

    project_id = data.get("project_id", 1)
    requirement = Requirement(
        title=data.get("title") or f"Requirement-{_now().strftime('%Y%m%d-%H%M%S')}",
        description=demand[:100] + "..." if len(demand) > 100 else demand,
        raw_text=demand,
        structured_data=structured_seed,
        status="pending",
        execution_progress={"test_environment": test_environment} if test_environment else None,
        knowledge_base_id=data.get("knowledge_base_id"),
        project_id=project_id,
    )
    db.session.add(requirement)
    db.session.flush()

    conversation = Conversation(
        title=f"需求 #{requirement.id} · {(requirement.title or '')[:40]}",
        requirement_id=requirement.id,
        status="active",
    )
    db.session.add(conversation)
    db.session.commit()

    # Orchestrator mode: kick off the conversation-driven flow
    from config import Config
    if Config.CONVERSATION_FLOW_ENABLED:
        from agent.orchestrator import process_user_message_flow

        if is_doc_url_mode:
            # CDP extraction is slow (navigate + extract), so run it async.
            # First create the requirement and return the response immediately;
            # then extract in background, update the requirement, and start flow.
            def _extract_then_start():
                flask_app = _resolve_flask_app()
                with flask_app.app_context():
                    try:
                        extracted = _extract_doc_from_url(doc_url)
                        req = db.session.get(Requirement, requirement.id)
                        if req and extracted:
                            content = extracted["content"]
                            req.raw_text = content
                            req.description = content[:100] + "..." if len(content) > 100 else content
                            sd = req.structured_data or {}
                            sd["original_document"] = {
                                "url": doc_url,
                                "title": extracted.get("title", ""),
                                "extracted_content": content,
                                "extracted_at": extracted.get("extracted_at"),
                            }
                            req.structured_data = sd
                            db.session.commit()
                            logger.info("Async CDP extraction succeeded for req %d", requirement.id)
                        elif req:
                            db.session.commit()
                            logger.warning("Async CDP extraction failed for req %d (doc_url=%s)", requirement.id, doc_url)
                        # Use the updated demand from DB (or fallback to placeholder)
                        updated_req = db.session.get(Requirement, requirement.id)
                        updated_demand = updated_req.raw_text if updated_req else demand
                        _fn = lambda: process_user_message_flow(conversation.id, updated_demand)
                        _run_orchestrator_in_thread(_fn, conversation.id, requirement.id)
                    except Exception as exc:
                        logger.exception("Async CDP extraction + flow start failed: %s", exc)
                        try:
                            _fn = lambda: process_user_message_flow(conversation.id, demand)
                            _run_orchestrator_in_thread(_fn, conversation.id, requirement.id)
                        except Exception:
                            pass

            _executor.submit(_extract_then_start)
        else:
            _fn = lambda: process_user_message_flow(conversation.id, demand)
            _executor.submit(_run_orchestrator_in_thread, _fn, conversation.id, requirement.id)

        return {
            "message": "Test flow started (orchestrator mode)",
            "requirement_id": requirement.id,
            "conversation_id": conversation.id,
            "status": "processing",
            "orchestrator_mode": True,
        }

    # Legacy pipeline mode
    flow = AutoTestFlow()
    flow_data = {"demand": demand, "requirement_id": requirement.id, "project_id": project_id}
    if test_environment:
        flow_data["test_environment"] = test_environment
    review_config = data.get("review") or data.get("review_config")
    if review_config:
        flow_data["review"] = review_config

    with _registry_lock:
        _flow_registry[requirement.id] = {"flow_id": str(id(flow)), "status": "pending"}
    _executor.submit(execute_flow_async, flow, flow_data, requirement.id)

    return {
        "message": "Test flow started",
        "requirement_id": requirement.id,
        "conversation_id": conversation.id,
        "status": "processing",
        "flow_id": str(id(flow)),
    }


def enqueue_requirement_flow(requirement: Requirement, review_config: dict | None = None) -> dict[str, Any]:
    """Queue the legacy flow for an existing requirement."""
    flow = AutoTestFlow()
    flow_data = {
        "demand": requirement.raw_text,
        "requirement_id": requirement.id,
        "project_id": requirement.project_id or 1,
    }

    progress = requirement.execution_progress or {}
    structured = requirement.structured_data or {}
    test_environment = progress.get("test_environment") or structured.get("test_environment")
    if test_environment:
        flow_data["test_environment"] = test_environment
    if review_config:
        flow_data["review"] = review_config

    flow_id = str(id(flow))
    with _registry_lock:
        _flow_registry[requirement.id] = {"flow_id": flow_id, "status": "pending"}
    _executor.submit(execute_flow_async, flow, flow_data, requirement.id)

    return {
        "message": "Test flow started",
        "requirement_id": requirement.id,
        "status": "processing",
        "flow_id": flow_id,
    }


def get_flow_status(requirement_id: int):
    requirement = db.session.get(Requirement, requirement_id)
    if not requirement:
        raise NotFoundError(f"Requirement {requirement_id} not found")
    with _registry_lock:
        flow_info = _flow_registry.get(requirement_id, {})
    return {
        "requirement_id": requirement_id,
        "db_status": requirement.status,
        "flow_status": flow_info.get("status", "unknown"),
        "execution_progress": requirement.execution_progress,
    }


def resume_flow(requirement_id: int):
    requirement = db.session.get(Requirement, requirement_id)
    if not requirement:
        raise NotFoundError(f"Requirement {requirement_id} not found")

    current_status = requirement.status
    if current_status in ("executed", "completed"):
        return {"message": "Flow already completed", "status": current_status}, 200

    if current_status == "executing":
        with _registry_lock:
            fi = _flow_registry.get(requirement_id, {})
        if fi.get("status") == "running":
            return {"message": "Flow is running", "status": current_status}, 200

    from config import Config

    # Orchestrator mode
    if Config.CONVERSATION_FLOW_ENABLED:
        conversation = Conversation.query.filter_by(
            requirement_id=requirement_id,
        ).order_by(Conversation.id.asc()).first()

        if not conversation:
            # No conversation yet — create one or fall back to legacy
            conversation = Conversation(
                title=f"需求 #{requirement.id} · {(requirement.title or '')[:40]}",
                requirement_id=requirement.id,
                status="active",
            )
            db.session.add(conversation)
            db.session.commit()

        # Reset error status
        if current_status == "error":
            requirement.status = "pending"
            db.session.commit()

        # Build resume message
        env = (requirement.execution_progress or {}).get("test_environment") or \
              (requirement.structured_data or {}).get("test_environment") or {}
        if env.get("test_url"):
            resume_msg = f"测试地址 {env['test_url']} 已配置，请开始探索页面并推进测试流程"
        else:
            resume_msg = "请开始解析需求并推进测试流程"

        user_msg = Message(
            conversation_id=conversation.id,
            sender="user",
            content=resume_msg,
            agent_type="user",
        )
        db.session.add(user_msg)
        db.session.commit()

        from agent.orchestrator import process_user_message_flow

        def _fn():
            return process_user_message_flow(conversation.id, resume_msg)

        _executor.submit(_run_orchestrator_in_thread, _fn, conversation.id, requirement_id)
        return {
            "message": "Flow resumed (orchestrator mode)",
            "requirement_id": requirement_id,
            "conversation_id": conversation.id,
            "status": "processing",
            "orchestrator_mode": True,
        }, 202

    # Legacy mode
    flow = AutoTestFlow()
    flow_data = {"demand": requirement.raw_text, "requirement_id": requirement_id, "project_id": requirement.project_id or 1}

    progress = requirement.execution_progress or {}
    structured = requirement.structured_data or {}
    test_environment = progress.get("test_environment") or structured.get("test_environment")
    if test_environment:
        flow_data["test_environment"] = test_environment

    if current_status == "error":
        existing_cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
        case_ids = [c.id for c in existing_cases]
        script_count = TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).count() if case_ids else 0
        if script_count:
            flow_data["resume_from"] = "code_generated"
            requirement.status = "code_generated"
        elif existing_cases:
            flow_data["resume_from"] = "cases_generated"
            requirement.status = "cases_generated"
        else:
            requirement.status = "pending"
        requirement.execution_progress = {"retrying": True, "previous_status": current_status, "retry_started_at": _now().isoformat()}
        db.session.commit()
    elif current_status == "parsed":
        if TestCase.query.filter_by(requirement_id=requirement_id).first():
            requirement.status = "cases_generated"
            db.session.commit()
        flow_data["resume_from"] = "cases_generated"
    elif current_status in ("cases_generated", "code_generated"):
        flow_data["resume_from"] = current_status

    _executor.submit(execute_flow_async, flow, flow_data, requirement_id)
    return {
        "message": "Flow resumed",
        "requirement_id": requirement_id,
        "previous_status": current_status,
        "status": "processing",
    }, 202


def retry_script(script_id: int):
    import json

    script = db.session.get(TestScript, script_id)
    if not script:
        raise NotFoundError(f"Test script {script_id} not found")

    is_ui = script.script_type == "ui_cdp"
    if is_ui:
        # CDP / UI 脚本走 DSL 引擎，不走 pytest 子进程
        from service.ui_runner_service import run_ui_dsl

        dsl = json.loads(script.script_content or "{}")
        # Resolve test_url from the requirement's structured_data
        requirement = script.test_case.requirement if script.test_case else None
        structured = requirement.structured_data or {} if requirement else {}
        env = structured.get("test_environment") or {} if isinstance(structured, dict) else {}
        base_url = env.get("test_url", "")
        result = run_ui_dsl(dsl, base_url=base_url, screenshot_prefix=f"ui_{script.id}_retry")
    else:
        exec_agent = ExecAgent()
        result = exec_agent.process(
            {
                "script_id": script.id,
                "script_content": script.script_content,
                "file_path": script.file_path,
                "script_type": script.script_type,
            }
        )
    record = ExecutionRecord(
        test_script_id=script.id,
        status=result.get("status", "unknown"),
        result_data=result.get("result", {}),
        error_message=result.get("error"),
        execution_time=result.get("execution_time", 0),
        report_path=result.get("report_path"),
        screenshot_paths=result.get("screenshots", []),
        started_at=_now(),
        finished_at=_now(),
    )
    db.session.add(record)
    script.status = "executed" if result.get("status") == "success" else "error"
    db.session.commit()
    return {
        "message": "Script retry completed",
        "script_id": script.id,
        "status": result.get("status"),
        "execution_time": result.get("execution_time"),
        "error": result.get("error"),
    }
