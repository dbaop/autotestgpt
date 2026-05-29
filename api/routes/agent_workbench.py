"""
Agent workbench routes.
"""

from flask import jsonify, request

from service.agent_workbench_service import get_workbench, list_workbench
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
        return jsonify(payload)
    except AppError as err:
        return jsonify(err.to_dict()), err.status_code
