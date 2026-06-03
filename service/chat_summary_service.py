"""
Compact agent context for chat (summary + pending user actions only).
"""

from __future__ import annotations

from typing import Any

from models import Conversation, Message, Requirement, db
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


def _missing_env_items(env: dict[str, Any], review: dict[str, Any]) -> list[str]:
    items: list[str] = []
    if not env.get("test_url"):
        items.append("测试地址")
    if not env.get("login_state") or env.get("login_state") == "unknown":
        items.append("登录态")
    if not env.get("credential_ref"):
        items.append("凭据")
    if not review.get("repo_url") and not review.get("repo_path"):
        items.append("代码仓库")
    if not review.get("branch"):
        items.append("分支")
    return items


def maybe_post_env_setup_question(requirement_id: int, env: dict[str, Any], review: dict[str, Any]) -> bool:
    """若需求缺测试环境/仓库信息，向关联对话写入一条 system 待确认消息并重置已读状态。

    同一需求在最近一次主动消息之后不再重复打扰；通过 AgentEvent 中 waiting_user 事件去重。
    """
    items = _missing_env_items(env, review)
    if not items:
        return False

    requirement = db.session.get(Requirement, requirement_id)
    if not requirement:
        return False

    conversation = Conversation.query.filter_by(requirement_id=requirement_id).order_by(Conversation.id.asc()).first()
    if not conversation:
        return False

    # 去重：最近 5 分钟内已经发过同类问题就跳过
    from datetime import datetime, timezone, timedelta

    recent = Message.query.filter(
        Message.conversation_id == conversation.id,
        Message.sender == "system",
        Message.content.like("⚙ 待补全:%"),
    ).order_by(Message.id.desc()).first()
    if recent and recent.created_at and datetime.now(timezone.utc) - recent.created_at.replace(tzinfo=timezone.utc) < timedelta(minutes=5):
        return False

    items_text = " / ".join(items)
    content = (
        f"⚙ 待补全:{items_text}\n\n"
        f"工作台还没收到这些信息，我没法做页面探活、登录态复用和代码 Review。\n"
        f"请在「Agent 工作台 → 配置测试环境」填写，或直接在本对话回复，例如：\n"
        f"  · 测试地址 https://staging.example.com\n"
        f"  · 登录态 pre_authenticated,凭据 vault://login/account\n"
        f"  · 仓库 http://git.example.com/group/repo.git,分支 main"
    )
    msg = Message(
        conversation_id=conversation.id,
        sender="system",
        agent_type="router",
        content=content,
        extra_data={"source": "env_setup", "missing": items},
    )
    # 让该消息以未读形式出现：把 last_read_at 置回更早的时间点（或 NULL）
    conversation.last_read_at = (conversation.last_read_at and conversation.last_read_at)  # 保留
    # 关键：让这条新消息一定 > last_read_at，从而被算成未读
    db.session.add(msg)
    # 把已读时间强制回退到本条消息之前，确保未读 +1
    conversation.last_read_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.session.commit()

    # 同时记录到工作台事件流，便于"人工介入"区也能看到
    emit_agent_event(
        requirement_id,
        "System",
        "waiting_user",
        f"等待用户补全: {items_text}",
        {"source": "env_setup", "missing": items},
    )
    return True


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
