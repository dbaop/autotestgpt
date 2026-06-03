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
from models import Conversation, ExecutionRecord, Requirement, TestCase, TestScript, db
from service.errors import NotFoundError, ValidationError


_executor = ThreadPoolExecutor(max_workers=4)
_flow_registry: dict[int, dict[str, Any]] = {}
_registry_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc)


def _set_requirement_status(requirement_id: int, status: str, execution_progress: dict | None = None):
    requirement = db.session.get(Requirement, requirement_id)
    if not requirement:
        raise NotFoundError(f"Requirement {requirement_id} not found")
    requirement.status = status
    if execution_progress is not None:
        requirement.execution_progress = execution_progress
    db.session.commit()
    return requirement


def _resolve_flask_app():
    from flask import has_app_context, current_app

    if has_app_context():
        return current_app._get_current_object()
    from main import app

    return app


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


def _extract_doc_from_url(url: str) -> str | None:
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
            return (
                f"【来源】{result.get('url', url)}\n"
                f"【标题】{result.get('title', '')}\n\n"
                f"{result.get('content', '')}"
            )
        logger.warning("CDP extracted too little content from %s: %d chars", url, result.get("length", 0))
        return None
    except Exception as exc:
        logger.warning("CDP extraction failed for %s: %s", url, exc)
        return None


def start_flow(data: dict):
    demand = (data.get("demand") or "").strip()
    doc_url = (data.get("doc_url") or "").strip()

    # 如果提供了文档 URL（钉钉/飞书/语雀等），通过 CDP 自动提取内容
    if doc_url and not demand:
        extracted = _extract_doc_from_url(doc_url)
        if extracted:
            demand = extracted
        else:
            # CDP 提取失败时，把 URL 当作需求描述，让 agent 自己去打开
            demand = f"请打开以下文档链接并提取测试需求:\n{doc_url}"

    if not demand:
        raise ValidationError("Please provide `demand` or `doc_url` field")

    project_id = data.get("project_id", 1)
    # 保存原始文档 URL 供后续参考
    original_doc_url = doc_url or None
    test_environment = data.get("test_environment") or {}
    structured_seed = {"test_environment": test_environment}
    if original_doc_url:
        structured_seed["doc_url"] = original_doc_url
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
    test_environment = data.get("test_environment") or {}
    structured_seed = {"test_environment": test_environment} if test_environment else None
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
        import json as _json
        from service.sse_service import push_sse_event, broadcast_error

        def _run_orchestrator_flow():
            from agent.orchestrator import process_user_message_flow
            try:
                for event in process_user_message_flow(conversation.id, demand):
                    push_sse_event(conversation.id, event)
            except Exception as exc:
                broadcast_error(conversation.id, str(exc))

        _executor.submit(_run_orchestrator_flow)

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

    flow = AutoTestFlow()
    flow_data = {"demand": requirement.raw_text, "requirement_id": requirement_id, "project_id": requirement.project_id or 1}

    # 带上已保存的测试环境配置，确保 resume 后 agent 能拿到 URL/登录态/凭据
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
    script = db.session.get(TestScript, script_id)
    if not script:
        raise NotFoundError(f"Test script {script_id} not found")

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
