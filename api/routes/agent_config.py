"""
Agent config & environment config routes.
"""

from __future__ import annotations

from flask import jsonify, request

from models import AgentConfig, Requirement, db
from service.errors import AppError, ValidationError, NotFoundError


# ---------------------------------------------------------------------------
# Agent Config CRUD
# ---------------------------------------------------------------------------

def list_agent_configs():
    project_id = request.args.get("project_id", type=int)
    query = AgentConfig.query
    if project_id:
        query = query.filter(
            (AgentConfig.project_id == project_id) | (AgentConfig.project_id.is_(None))
        )
    configs = query.order_by(AgentConfig.agent_type).all()
    return jsonify({"items": [c.to_dict() for c in configs], "total": len(configs)})


def upsert_agent_config():
    try:
        body = request.get_json() or {}
        agent_type = (body.get("agent_type") or "").strip()
        if not agent_type:
            raise ValidationError("agent_type is required")

        project_id = body.get("project_id")
        existing = AgentConfig.query.filter_by(
            agent_type=agent_type, project_id=project_id
        ).first()

        if existing:
            existing.system_prompt = body.get("system_prompt")
            existing.model_name = body.get("model_name")
            existing.temperature = body.get("temperature", existing.temperature)
            existing.max_tokens = body.get("max_tokens", existing.max_tokens)
            if "is_enabled" in body:
                existing.is_enabled = body["is_enabled"]
            if "extra_config" in body:
                existing.extra_config = body["extra_config"]
            config = existing
        else:
            config = AgentConfig(
                agent_type=agent_type,
                project_id=project_id,
                system_prompt=body.get("system_prompt"),
                model_name=body.get("model_name"),
                temperature=body.get("temperature", 0.1),
                max_tokens=body.get("max_tokens", 4000),
                is_enabled=body.get("is_enabled", True),
                extra_config=body.get("extra_config"),
            )
            db.session.add(config)

        db.session.commit()
        return jsonify({"message": "saved", "config": config.to_dict()})
    except AppError as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "AGENT_CONFIG_FAILED", "message": str(e)}), 500


def update_agent_config(config_id: int):
    try:
        config = db.session.get(AgentConfig, config_id)
        if not config:
            raise NotFoundError(f"AgentConfig {config_id} not found")

        body = request.get_json() or {}
        for key in ("system_prompt", "model_name", "temperature", "max_tokens", "is_enabled", "extra_config"):
            if key in body:
                setattr(config, key, body[key])

        db.session.commit()
        return jsonify({"message": "updated", "config": config.to_dict()})
    except AppError as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "AGENT_CONFIG_UPDATE_FAILED", "message": str(e)}), 500


# ---------------------------------------------------------------------------
# Environment Config
# ---------------------------------------------------------------------------

def save_environment_config():
    """保存测试环境配置到 requirement 的 execution_progress 中。"""
    try:
        body = request.get_json() or {}
        requirement_id = body.get("requirement_id")
        if not requirement_id:
            raise ValidationError("requirement_id is required")

        req = db.session.get(Requirement, requirement_id)
        if not req:
            raise NotFoundError(f"Requirement {requirement_id} not found")

        env = {
            "test_url": body.get("test_url"),
            "login_state": body.get("login_state", "unknown"),
            "credential_ref": body.get("credential_ref"),
            "allow_explore": body.get("allow_explore", True),
            "last_probe_at": body.get("last_probe_at"),
            "probe_status": body.get("probe_status"),
        }

        progress = req.execution_progress or {}
        progress["test_environment"] = env
        req.execution_progress = progress
        db.session.commit()

        return jsonify({"message": "saved", "environment": env})
    except AppError as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "ENV_CONFIG_FAILED", "message": str(e)}), 500


def get_environment_config(requirement_id: int):
    req = db.session.get(Requirement, requirement_id)
    if not req:
        raise NotFoundError(f"Requirement {requirement_id} not found")

    progress = req.execution_progress or {}
    env = progress.get("test_environment") or {}
    return jsonify({"requirement_id": requirement_id, "environment": env})
