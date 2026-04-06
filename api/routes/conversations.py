"""
对话相关路由
"""

from flask import request, jsonify
from models import db, Conversation, Message
from datetime import datetime, timezone
import json


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
            content='您好！我是 AutoTestGPT 智能测试助手。我有四个专业的 Agent 成员：\n\n'
                    '- **ReqAgent**：需求分析师，帮您梳理和理解测试需求\n'
                    '- **CaseAgent**：测试用例设计师，为您设计全面的测试用例\n'
                    '- **CodeAgent**：代码工程师，生成可执行的自动化测试脚本\n'
                    '- **ExecAgent**：执行分析师，运行测试并生成详细报告\n\n'
                    '请告诉我您想要测试什么？我会协调各 Agent 为您服务。',
            agent_type='router'
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

        result = conversation.to_dict()
        result['messages'] = [msg.to_dict() for msg in messages]
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


def get_messages(conv_id):
    """获取对话消息"""
    try:
        conversation = db.get_or_404(Conversation, conv_id)
        last_msg_id = request.args.get('last_id', 0, type=int)

        query = Message.query.filter(
            Message.conversation_id == conv_id,
            Message.id > last_msg_id
        ).order_by(Message.created_at)

        messages = query.all()
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

        # 调用 Agent 处理（Agent 内部会保存用户消息）
        from agent.chat_agent import process_user_message
        result = process_user_message(conv_id, data['content'])

        # 返回更新后的消息列表
        messages = Message.query.filter_by(conversation_id=conv_id).order_by(Message.created_at).all()
        return jsonify({
            'message': '消息已发送',
            'messages': [msg.to_dict() for msg in messages],
            'last_id': messages[-1].id if messages else 0
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '发送消息失败', 'message': str(e)}), 500
