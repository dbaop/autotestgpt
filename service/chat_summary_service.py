"""
Compact agent context for chat (summary + pending user actions only).
"""

from __future__ import annotations

from typing import Any

from models import Conversation, Requirement, db
from service.agent_event_service import emit_agent_event
from service.agent_workbench_service import build_requirement_workbench
from service.errors import NotFoundError

_STATUS_HEADLINE = {
    "pending": "等待开始需求解析",
    "parsed": "需求已解析，正在设计用例",
    "cases_generated": "用例已生成，正在编写脚本",
    "code_generated": "脚本已生成，准备执行",
    "executing": "正在执行自动化测试",
    "executed": "执行完成，Review/缺陷分析中",
    "completed": "本需求流程已完成",
    "error": "流程异常，请在工作台查看详情",
}

_INTERVENTION_KEYWORDS = ("验证码", "登录态", "登录过期", "不可访问", "权限不足", "需要确认")


def _get_requirement(requirement_id: int) -> Requirement:
    requirement = db.session.get(Requirement, requirement_id)
    if not requirement:
        raise NotFoundError(f"Requirement {requirement_id} not found")
    return requirement


def _headline(workbench: dict[str, Any]) -> str:
    running = [a for a in workbench["agents"] if a["status"] == "running"]
    if running:
        agent = running[0]
        return f"{agent['name']}：{agent['current_action']}"
    status = workbench["overall_progress"]["status"]
    return _STATUS_HEADLINE.get(status, status)


def _pending_questions(workbench: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in workbench["events"]:
        if event.get("event_type") != "waiting_user":
            continue
        items.append(
            {
                "id": event.get("id"),
                "agent": event.get("agent"),
                "message": event.get("message"),
                "event_type": "waiting_user",
            }
        )
    for row in workbench.get("interventions") or []:
        items.append(
            {
                "id": None,
                "agent": "System",
                "message": row.get("message") or row.get("type"),
                "event_type": row.get("type", "intervention"),
            }
        )
    return items


def _pack_context(requirement_id: int, workbench: dict[str, Any]) -> dict[str, Any]:
    artifacts = workbench["artifacts"]
    running = [
        {"id": a["id"], "name": a["name"], "action": a["current_action"]}
        for a in workbench["agents"]
        if a["status"] == "running"
    ]
    return {
        "requirement_id": requirement_id,
        "title": workbench["requirement"]["title"],
        "status": workbench["overall_progress"]["status"],
        "headline": _headline(workbench),
        "running_agents": running,
        "stats": {
            "cases": artifacts["cases"],
            "ui_scripts": artifacts["ui_scripts"],
            "defects": artifacts["defects"],
            "review_findings": artifacts["review_findings"],
        },
        "pending_questions": _pending_questions(workbench),
        "workbench_path": f"/workbench/{requirement_id}",
    }


def build_chat_agent_context(requirement_id: int) -> dict[str, Any]:
    workbench = build_requirement_workbench(_get_requirement(requirement_id))
    return _pack_context(requirement_id, workbench)


def build_chat_agent_context_for_conversation(conversation_id: int) -> dict[str, Any] | None:
    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or not conversation.requirement_id:
        return None
    return build_chat_agent_context(conversation.requirement_id)


def maybe_emit_waiting_user_from_chat(requirement_id: int, user_message: str) -> bool:
    if not any(keyword in user_message for keyword in _INTERVENTION_KEYWORDS):
        return False
    emit_agent_event(
        requirement_id,
        "System",
        "waiting_user",
        f"Waiting for user: {user_message[:200]}",
        {"source": "chat"},
    )
    return True
