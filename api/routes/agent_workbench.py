"""
Agent workbench routes.
"""

from flask import jsonify, request

from service.agent_workbench_service import get_workbench, list_workbench
from service.chat_summary_service import maybe_post_env_setup_question
from service.errors import AppError


def list_agent_workbench():
    try:
        return jsonify(list_workbench())
    except AppError as err:
        return jsonify(err.to_dict()), err.status_code


def get_agent_workbench(requirement_id: int):
    try:
        since_id = request.args.get("since_id", type=int)
        payload = get_workbench(requirement_id)
        if since_id:
            payload["events"] = [e for e in payload["events"] if e["id"] > since_id]
        # 主动把"待补全"问询推到关联对话，触发未读消息提醒
        try:
            maybe_post_env_setup_question(requirement_id, payload.get("environment") or {}, payload.get("review") or {})
        except Exception:
            pass  # 不阻塞主流程
        return jsonify(payload)
    except AppError as err:
        return jsonify(err.to_dict()), err.status_code
