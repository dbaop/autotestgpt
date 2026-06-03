"""
Requirement routes.
"""

from datetime import datetime, timezone

from flask import jsonify, request

from models import Conversation, Message, Requirement, db
from service.document_import_service import parse_uploaded_file
from service.errors import AppError, ValidationError
from service.requirement_service import (
    create_requirement as create_requirement_entity,
    delete_requirement as delete_requirement_entity,
    get_requirement_detail,
    list_requirements,
    update_requirement as update_requirement_entity,
)


def _create_requirement_conversation(requirement: Requirement) -> Conversation:
    """为需求自动创建一条对话，并写入欢迎消息。"""
    conversation = Conversation(
        title=f"需求 #{requirement.id} · {(requirement.title or '')[:40]}",
        requirement_id=requirement.id,
        status="active",
    )
    db.session.add(conversation)
    db.session.flush()

    welcome = Message(
        conversation_id=conversation.id,
        sender="router",
        agent_type="router",
        content=(
            "您好！我是 AutoTestGPT 对话助手。\n\n"
            "本页用于沟通与需要您确认的问题；完整 Agent 流水、产物与探活状态请查看 **Agent 工作台**。\n\n"
            "您可以：说明测试需求、补充测试地址/登录方式、回答验证码或权限相关问题。\n"
            "关联此条需求后，右侧会同步该任务的简要进度与待办。"
        ),
    )
    db.session.add(welcome)
    db.session.commit()
    return conversation


def get_requirements():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        status = request.args.get("status")
        pagination = list_requirements(page=page, per_page=per_page, status=status)

        return jsonify(
            {
                "items": [req.to_dict() for req in pagination.items],
                "total": pagination.total,
                "page": page,
                "per_page": per_page,
                "pages": pagination.pages,
            }
        )
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": "Failed to load requirements", "message": str(e)}), 500


def get_requirement(req_id):
    try:
        return jsonify(get_requirement_detail(req_id))
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": "Failed to load requirement", "message": str(e)}), 500


def create_requirement():
    try:
        requirement = create_requirement_entity(request.get_json() or {})
        conversation = _create_requirement_conversation(requirement)
        return jsonify(
            {
                "message": "Requirement created",
                "requirement": requirement.to_dict(),
                "conversation_id": conversation.id,
            }
        ), 201
    except AppError as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to create requirement", "message": str(e)}), 500


def import_requirement():
    try:
        upload = request.files.get("file")
        title = (request.form.get("title") or "").strip() or "Imported Requirement"
        project_id = request.form.get("project_id", type=int)
        knowledge_base_id = request.form.get("knowledge_base_id", type=int)

        if not upload or not upload.filename:
            raise ValidationError("Please upload a requirement file")

        raw_bytes = upload.read()
        content = parse_uploaded_file(upload.filename, raw_bytes)
        if not content:
            raise ValidationError("Uploaded file does not contain readable content")

        requirement = Requirement(
            title=title,
            description=content[:500],
            raw_text=content,
            status="pending",
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
        )
        db.session.add(requirement)
        db.session.flush()

        # 自动创建关联对话，确保前端"对话协作"里能看到新需求
        conversation = _create_requirement_conversation(requirement)

        return jsonify(
            {
                "message": "Requirement imported",
                "requirement": requirement.to_dict(),
                "conversation_id": conversation.id,
            }
        ), 201
    except AppError as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to import requirement", "message": str(e)}), 500


def update_requirement(req_id):
    try:
        requirement = update_requirement_entity(req_id, request.get_json() or {})
        return jsonify({"message": "Requirement updated", "requirement": requirement.to_dict()})
    except AppError as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to update requirement", "message": str(e)}), 500


def delete_requirement(req_id):
    try:
        delete_requirement_entity(req_id)
        return jsonify({"message": "Requirement deleted"})
    except AppError as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to delete requirement", "message": str(e)}), 500
