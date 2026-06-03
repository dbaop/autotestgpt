"""
对话相关路由
"""

from flask import request, jsonify
from models import db, Conversation, Message, Requirement
from datetime import datetime, timezone
import json


def _title_from_message(content: str) -> str:
    first_line = (content or "").strip().splitlines()[0] if (content or "").strip() else ""
    if not first_line:
        return "对话需求"
    return first_line[:60] + ("..." if len(first_line) > 60 else "")


def _bootstrap_requirement_from_chat(conversation: Conversation, content: str) -> Requirement | None:
    if conversation.requirement_id:
        return None

    demand = (content or "").strip()
    if not demand:
        return None

    title = _title_from_message(demand)
    requirement = Requirement(
        title=title,
        description=demand[:100] + ("..." if len(demand) > 100 else ""),
        raw_text=demand,
        structured_data={"source": "chat"},
        execution_progress={"source": "chat", "auto_complete": True},
        status="pending",
    )
    db.session.add(requirement)
    db.session.flush()

    conversation.requirement_id = requirement.id
    conversation.title = f"需求 #{requirement.id} · {title}"
    db.session.commit()
    return requirement


def get_conversations():
    """获取对话列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        query = Conversation.query.order_by(Conversation.updated_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'items': [conv.to_dict() for conv in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        })
    except Exception as e:
        return jsonify({'error': '获取对话列表失败', 'message': str(e)}), 500


def create_conversation():
    """创建新对话"""
    try:
        data = request.get_json() or {}

        conversation = Conversation(
            title=data.get('title', f'对话-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}'),
            requirement_id=data.get('requirement_id'),
            status='active'
        )
        db.session.add(conversation)
        db.session.commit()

        # 添加系统欢迎消息
        welcome = Message(
            conversation_id=conversation.id,
            sender='router',
            content='您好！我是 AutoTestGPT 对话助手。\n\n'
                    '本页用于沟通与需要您确认的问题；完整 Agent 流水、产物与探活状态请查看 **Agent 工作台**。\n\n'
                    '您可以：说明测试需求、补充测试地址/登录方式、回答验证码或权限相关问题。\n'
                    '关联某条需求后，右侧会同步该任务的简要进度与待办。',
            agent_type='router',
        )
        db.session.add(welcome)
        db.session.commit()

        return jsonify({
            'message': '对话创建成功',
            'conversation': conversation.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '创建对话失败', 'message': str(e)}), 500


def get_conversation(conv_id):
    """获取对话详情"""
    try:
        conversation = db.get_or_404(Conversation, conv_id)
        messages = Message.query.filter_by(conversation_id=conv_id).order_by(Message.created_at).all()

        # 打开对话即视为已读：刷新 last_read_at，清零未读
        conversation.last_read_at = datetime.now(timezone.utc)
        db.session.commit()

        from service.chat_summary_service import build_chat_agent_context_for_conversation

        result = conversation.to_dict()
        result['messages'] = [msg.to_dict() for msg in _visible_messages(messages)]
        result['agent_context'] = build_chat_agent_context_for_conversation(conv_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': '获取对话详情失败', 'message': str(e)}), 500


def delete_conversation(conv_id):
    """删除对话"""
    try:
        conversation = db.get_or_404(Conversation, conv_id)
        db.session.delete(conversation)
        db.session.commit()
        return jsonify({'message': '对话删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '删除对话失败', 'message': str(e)}), 500


def mark_conversation_read(conv_id):
    """显式将对话标记为已读（用于前端 SSE 收到新消息后即时清零未读数）。"""
    try:
        conversation = db.get_or_404(Conversation, conv_id)
        conversation.last_read_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({'message': 'marked read', 'conversation_id': conv_id, 'unread_count': conversation.unread_count()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '标记已读失败', 'message': str(e)}), 500


def get_agent_context(conv_id):
    """返回对话关联需求的精简 Agent 上下文（摘要 + 待确认）。"""
    try:
        db.get_or_404(Conversation, conv_id)
        from service.chat_summary_service import build_chat_agent_context_for_conversation

        context = build_chat_agent_context_for_conversation(conv_id)
        if not context:
            return jsonify({
                'requirement_id': None,
                'headline': '未关联需求任务',
                'pending_questions': [],
                'workbench_path': '/workbench',
            })
        return jsonify(context)
    except Exception as e:
        return jsonify({'error': '获取 Agent 上下文失败', 'message': str(e)}), 500


def stream_conversation(conv_id):
    """SSE 端点，实时推送 Agent 事件到前端。"""
    try:
        db.get_or_404(Conversation, conv_id)
        from service.sse_service import create_sse_stream

        return create_sse_stream(conv_id)
    except Exception as e:
        return jsonify({'error': 'SSE 连接失败', 'message': str(e)}), 500


def _visible_messages(messages):
    return [msg for msg in messages if not (msg.extra_data or {}).get('hidden')]


def get_messages(conv_id):
    """获取对话消息"""
    try:
        conversation = db.get_or_404(Conversation, conv_id)
        last_msg_id = request.args.get('last_id', 0, type=int)

        query = Message.query.filter(
            Message.conversation_id == conv_id,
            Message.id > last_msg_id
        ).order_by(Message.created_at)

        messages = _visible_messages(query.all())
        return jsonify({
            'items': [msg.to_dict() for msg in messages],
            'count': len(messages)
        })
    except Exception as e:
        return jsonify({'error': '获取消息失败', 'message': str(e)}), 500


def send_message(conv_id):
    """发送消息并触发 Agent 处理"""
    try:
        data = request.get_json()
        if not data or 'content' not in data:
            return jsonify({'error': '消息内容不能为空'}), 400

        conversation = db.get_or_404(Conversation, conv_id)
        bootstrapped_requirement = _bootstrap_requirement_from_chat(conversation, data['content'])

        # 防重复：检查最近3秒内是否有相同内容的消息
        recent = Message.query.filter_by(
            conversation_id=conv_id,
            sender='user',
            content=data['content']
        ).order_by(Message.created_at.desc()).first()

        if recent:
            from datetime import timedelta
            if datetime.now(timezone.utc) - recent.created_at.replace(tzinfo=timezone.utc) < timedelta(seconds=3):
                messages = Message.query.filter_by(conversation_id=conv_id).order_by(Message.created_at).all()
                return jsonify({
                    'message': '消息已存在',
                    'messages': [msg.to_dict() for msg in messages],
                    'last_id': messages[-1].id if messages else 0
                }), 200

        from agent.chat_agent import process_user_message
        from service.chat_summary_service import (
            build_chat_agent_context_for_conversation,
            maybe_emit_waiting_user_from_chat,
        )
        from config import Config

        if conversation.requirement_id:
            maybe_emit_waiting_user_from_chat(conversation.requirement_id, data['content'])

        result = process_user_message(conv_id, data['content'])

        # Orchestrator mode — push events via SSE, return 202
        if isinstance(result, dict) and result.get("_orchestrator_mode"):
            from service.sse_service import push_sse_event, broadcast_error
            import threading

            def _run_orchestrator():
                from agent.orchestrator import process_user_message_flow
                from flask import copy_current_request_context

                try:
                    for event in process_user_message_flow(conv_id, data['content']):
                        push_sse_event(conv_id, event)
                except Exception as exc:
                    broadcast_error(conv_id, str(exc))

            thread = threading.Thread(target=_run_orchestrator, daemon=True)
            thread.start()

            return jsonify({
                'message': '已接收，Agent 正在处理...',
                'orchestrator_mode': True,
                'started_from_chat': bool(bootstrapped_requirement),
                'requirement_id': conversation.requirement_id,
            }), 202

        # Legacy chat mode
        flow_result = None
        if bootstrapped_requirement:
            from service.flow_service import enqueue_requirement_flow

            flow_result = enqueue_requirement_flow(bootstrapped_requirement)

        messages = _visible_messages(
            Message.query.filter_by(conversation_id=conv_id).order_by(Message.created_at).all()
        )
        return jsonify({
            'message': '消息已发送',
            'messages': [msg.to_dict() for msg in messages],
            'last_id': messages[-1].id if messages else 0,
            'agent_context': build_chat_agent_context_for_conversation(conv_id),
            'started_from_chat': bool(bootstrapped_requirement),
            'requirement_id': conversation.requirement_id,
            'flow': flow_result,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '发送消息失败', 'message': str(e)}), 500
