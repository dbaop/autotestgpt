"""
对话聊天智能体服务
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from models import db, Conversation, Message
from .req_agent import ReqAgent
from .case_agent import CaseAgent
from .code_agent import CodeAgent
from .exec_agent import ExecAgent

logger = logging.getLogger(__name__)

# Agent 个性化提示词
AGENT_PERSONAS = {
    'req_agent': """你是一个专业的测试需求分析师，名叫小Req。你专业、严谨、善于提问澄清。

你的特点：
- 说话专业但易懂
- 善于引导用户明确需求
- 喜欢用列表和结构化方式表达
- 会主动询问不清楚的地方
- 偶尔会用表情符号让对话更亲切

当前对话背景：
{context}

请用友好的方式回复用户。""",

    'case_agent': """你是一个专业的测试用例设计师，名叫小Case。你细致、逻辑清晰、覆盖全面。

你的特点：
- 说话条理清晰
- 注重测试用例的完整性
- 喜欢用编号列举要点
- 会考虑边界条件和异常情况
- 偶尔会说"让我仔细想想..."

当前对话背景：
{context}

请用专业的态度回复用户。""",

    'code_agent': """你是一个务实的代码工程师，名叫小Code。你注重代码质量，简洁高效。

你的特点：
- 说话直接务实
- 注重代码可读性和可维护性
- 会提供简洁的代码示例
- 喜欢用技术术语但会解释
- 偶尔会说"代码写完了"

当前对话背景：
{context}

请用工程师的风格回复用户。""",

    'exec_agent': """你是一个冷静的执行分析师，名叫小Exec。你数据驱动、客观报告。

你的特点：
- 说话冷静客观
- 注重数据和结果
- 会清晰报告执行情况
- 遇到问题会分析原因
- 喜欢用表格展示数据

当前对话背景：
{context}

请用分析师的风格回复用户。""",

    'router': """你是一个智能测试助手协调者。你负责理解用户意图并协调各个专业Agent。

你可以协调的Agent：
- ReqAgent（需求分析师）：帮助梳理需求
- CaseAgent（测试用例设计师）：设计测试用例
- CodeAgent（代码工程师）：生成测试代码
- ExecAgent（执行分析师）：运行测试并报告结果

当用户描述需求时，你应该：
1. 先理解用户想要测试什么
2. 如果需求不够明确，引导用户补充
3. 如果需求明确，协调对应Agent提供服务

请用友好、专业的态度回复。"""
}

# 意图关键词映射
INTENT_KEYWORDS = {
    'req_agent': [
        '需求', '功能', '测试什么', '要测', '想测', '分析',
        '帮我理解', '需求是什么', '搞清楚', '需求不明确',
        '登录', '注册', '搜索', '下单', '支付', '用户'
    ],
    'case_agent': [
        '用例', '测试点', '覆盖', '场景', '步骤', '设计',
        '怎么测', '要测哪些', '测试场景', '边界', '异常'
    ],
    'code_agent': [
        '代码', '脚本', '写代码', '生成代码', '自动化',
        '实现', '怎么写', '帮我写', '生成脚本', 'pytest', 'playwright'
    ],
    'exec_agent': [
        '执行', '运行', '测试', '报告', '结果', '跑一下',
        '开始测试', '执行测试', '生成报告', '通过率'
    ]
}


class ChatRouter:
    """对话路由器"""

    def __init__(self):
        self.agents = {
            'req_agent': ReqAgent(),
            'case_agent': CaseAgent(),
            'code_agent': CodeAgent(),
            'exec_agent': ExecAgent()
        }

    def determine_intent(self, message: str, context: List[Dict]) -> str:
        """根据消息内容和上下文确定意图"""
        message_lower = message.lower()

        # 统计各 Agent 关键词匹配次数
        scores = {}
        for agent, keywords in INTENT_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in message_lower:
                    score += 1
            scores[agent] = score

        # 如果上下文中有提到具体需求，默认路由到 req_agent
        if context:
            last_messages = context[-3:]
            for msg in last_messages:
                if msg.get('sender') in ['req_agent', 'case_agent', 'code_agent']:
                    # 如果有 Agent 已经处理过，可能需要下一步
                    if scores.get('case_agent', 0) == 0:
                        scores['case_agent'] += 1
                    if scores.get('code_agent', 0) == 0:
                        scores.get('code_agent', 0)
                    break

        # 返回得分最高的 Agent
        if scores:
            best_agent = max(scores.items(), key=lambda x: x[1])
            if best_agent[1] > 0:
                return best_agent[0]

        return 'req_agent'  # 默认路由到需求分析

    def format_context(self, messages: List[Dict]) -> str:
        """格式化对话历史"""
        if not messages:
            return "（暂无历史对话）"

        lines = []
        for msg in messages[-6:]:  # 最近6条消息
            sender = msg.get('sender', 'unknown')
            content = msg.get('content', '')[:200]  # 截断长消息
            lines.append(f"[{sender}]: {content}")

        return '\n'.join(lines)


class ChatAgent:
    """对话智能体服务"""

    def __init__(self):
        self.router = ChatRouter()

    def process_user_message(self, conversation_id: int, user_message: str) -> Dict[str, Any]:
        """
        处理用户消息

        Args:
            conversation_id: 对话ID
            user_message: 用户消息

        Returns:
            处理结果
        """
        try:
            # 获取对话历史
            conversation = Conversation.query.get_or_404(conversation_id)
            history = Message.query.filter_by(conversation_id=conversation_id)\
                .order_by(Message.created_at).all()
            history_data = [msg.to_dict() for msg in history]

            # 保存用户消息
            user_msg = Message(
                conversation_id=conversation_id,
                sender='user',
                content=user_message,
                agent_type='user'
            )
            db.session.add(user_msg)
            db.session.commit()

            # 确定意图并路由
            target_agent = self.router.determine_intent(user_message, history_data)

            # 准备上下文
            context = self.router.format_context(history_data)

            # 根据路由调用对应 Agent
            if target_agent == 'req_agent':
                response = self._handle_req_agent(user_message, context, conversation_id, history_data)
            elif target_agent == 'case_agent':
                response = self._handle_case_agent(user_message, context, conversation_id, history_data)
            elif target_agent == 'code_agent':
                response = self._handle_code_agent(user_message, context, conversation_id, history_data)
            elif target_agent == 'exec_agent':
                response = self._handle_exec_agent(user_message, context, conversation_id, history_data)
            else:
                response = self._handle_default(user_message, context, conversation_id)

            # 检查是否需要 Agent 间协作
            response = self._check_collaboration(target_agent, response, conversation_id, history_data)

            # 更新对话时间
            from datetime import timezone
            conversation.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            return {
                'success': True,
                'response': response,
                'route': target_agent
            }

        except Exception as e:
            logger.error(f"处理用户消息失败: {e}")
            raise

    def _handle_req_agent(self, message: str, context: str, conv_id: int, history: List[Dict]) -> str:
        """处理需求分析"""
        agent = self.router.agents['req_agent']
        persona = AGENT_PERSONAS['req_agent'].format(context=context)

        try:
            # 检查是否已经有结构化需求
            has_structured_req = any(
                msg.get('metadata', {}).get('has_structured_req')
                for msg in history if msg.get('sender') == 'req_agent'
            )

            prompt = f"""用户说：{message}

请用小Req的风格回复用户。"""

            if has_structured_req:
                prompt += "\n\n注意：用户可能已经有结构化需求了，请确认是否需要补充。"

            response = agent.call_llm(prompt, persona)

            # 保存 Agent 响应
            msg = Message(
                conversation_id=conv_id,
                sender='req_agent',
                content=response,
                agent_type='req_agent',
                extra_data={'has_structured_req': True}
            )
            db.session.add(msg)
            db.session.commit()

            return response

        except Exception as e:
            logger.error(f"ReqAgent 处理失败: {e}")
            return f"[ReqAgent] 抱歉，处理您的需求时遇到了问题：{str(e)}"

    def _handle_case_agent(self, message: str, context: str, conv_id: int, history: List[Dict]) -> str:
        """处理测试用例设计"""
        agent = self.router.agents['case_agent']
        persona = AGENT_PERSONAS['case_agent'].format(context=context)

        try:
            # 检查是否有结构化需求
            structured_req = None
            for msg in history:
                if msg.get('sender') == 'req_agent' and msg.get('metadata', {}).get('has_structured_req'):
                    # 尝试从历史中提取需求
                    structured_req = msg.get('content', '')
                    break

            prompt = f"""用户说：{message}"""

            if structured_req:
                prompt += f"\n\n已有需求信息：{structured_req[:500]}..."

            prompt += "\n\n请用小Case的风格回复用户。"

            response = agent.call_llm(prompt, persona)

            msg = Message(
                conversation_id=conv_id,
                sender='case_agent',
                content=response,
                agent_type='case_agent'
            )
            db.session.add(msg)
            db.session.commit()

            return response

        except Exception as e:
            logger.error(f"CaseAgent 处理失败: {e}")
            return f"[CaseAgent] 抱歉，设计测试用例时遇到了问题：{str(e)}"

    def _handle_code_agent(self, message: str, context: str, conv_id: int, history: List[Dict]) -> str:
        """处理代码生成"""
        agent = self.router.agents['code_agent']
        persona = AGENT_PERSONAS['code_agent'].format(context=context)

        try:
            prompt = f"""用户说：{message}

请用小Code的风格回复用户。如果需要生成代码，请确保代码完整可运行。"""

            response = agent.call_llm(prompt, persona)

            msg = Message(
                conversation_id=conv_id,
                sender='code_agent',
                content=response,
                agent_type='code_agent'
            )
            db.session.add(msg)
            db.session.commit()

            return response

        except Exception as e:
            logger.error(f"CodeAgent 处理失败: {e}")
            return f"[CodeAgent] 抱歉，生成代码时遇到了问题：{str(e)}"

    def _handle_exec_agent(self, message: str, context: str, conv_id: int, history: List[Dict]) -> str:
        """处理测试执行"""
        agent = self.router.agents['exec_agent']
        persona = AGENT_PERSONAS['exec_agent'].format(context=context)

        try:
            prompt = f"""用户说：{message}

请用小Exec的风格回复用户。"""

            response = agent.call_llm(prompt, persona)

            msg = Message(
                conversation_id=conv_id,
                sender='exec_agent',
                content=response,
                agent_type='exec_agent'
            )
            db.session.add(msg)
            db.session.commit()

            return response

        except Exception as e:
            logger.error(f"ExecAgent 处理失败: {e}")
            return f"[ExecAgent] 抱歉，执行测试时遇到了问题：{str(e)}"

    def _handle_default(self, message: str, context: str, conv_id: int) -> str:
        """默认处理"""
        router_agent = self.router.agents['req_agent']
        persona = AGENT_PERSONAS['router'].format(context=context)

        try:
            prompt = f"""用户说：{message}

请理解用户意图并协调对应Agent提供服务。如果不确定用户需求，请引导用户明确需求。

请用友好的方式回复。"""

            response = router_agent.call_llm(prompt, persona)

            msg = Message(
                conversation_id=conv_id,
                sender='router',
                content=response,
                agent_type='router'
            )
            db.session.add(msg)
            db.session.commit()

            return response

        except Exception as e:
            logger.error(f"Router 处理失败: {e}")
            return f"[助手] 抱歉，处理您的消息时遇到了问题：{str(e)}"

    def _check_collaboration(self, current_agent: str, response: str, conv_id: int, history: List[Dict]) -> str:
        """检查是否需要 Agent 间协作"""
        # 如果 CaseAgent 完成了工作，可以提示 CodeAgent 准备生成代码
        if current_agent == 'case_agent':
            if '测试用例' in response and len(response) > 100:
                # CaseAgent 完成了，给 CodeAgent 一个提示
                next_msg = Message(
                    conversation_id=conv_id,
                    sender='router',
                    content='[系统提示] CaseAgent 已完成测试用例设计。CodeAgent，准备好生成测试代码了吗？',
                    agent_type='router'
                )
                db.session.add(next_msg)
                db.session.commit()

        return response


# 全局实例
_chat_agent = None

def get_chat_agent() -> ChatAgent:
    """获取聊天智能体实例"""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent()
    return _chat_agent


def process_user_message(conversation_id: int, user_message: str) -> Dict[str, Any]:
    """处理用户消息的便捷函数"""
    return get_chat_agent().process_user_message(conversation_id, user_message)
