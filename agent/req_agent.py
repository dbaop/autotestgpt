"""
需求解析智能体
"""

import json
import logging
from typing import Any, Dict, Generator, List, Optional

from .tool_agent import ToolCapableAgent
from .tools import format_tools_prompt
from config import Config

logger = logging.getLogger(__name__)

CONVERSATION_PHASES = {
    "idle": "No active task",
    "clarifying": "Agent is asking the user questions",
    "parsing": "ReqAgent is parsing requirements",
    "designing_cases": "CaseAgent is designing test cases",
    "generating_code": "CodeAgent is generating test scripts",
    "executing": "ExecAgent is running tests",
    "reviewing": "ReviewAgent is reviewing code",
    "completed": "All phases complete",
}

class ReqAgent(ToolCapableAgent):
    """需求解析智能体 — 支持工具调用和多轮交互"""

    def __init__(self):
        super().__init__(model="gpt-4", temperature=0.1, agent_type="req_agent")
        self.system_prompt = self.custom_system_prompt or """你是一个专业的测试需求分析师。你的任务是将自然语言需求解析为结构化的测试需求。

**文档内容优先级**
- 如果 prompt 中已包含 PRE-EXTRACTED DOCUMENT CONTENT 标记的文档正文，直接使用该内容。
- 如果用户提供的是文档链接（钉钉/飞书/语雀/Notion）且 prompt 中没有预提取内容，优先用 browser_navigate + browser_extract_content 打开。如果浏览器不可用（返回错误），不要卡住——直接用用户提供的文本内容继续分析。
- 如果 prompt 中明确说"请打开以下文档链接"但没有预提取内容，说明之前的自动提取失败了，你必须手动用 browser_navigate + browser_extract_content 去提取。如果浏览器也不可用，告诉用户需要手动粘贴文档内容或提供测试地址。

**关键：你没有浏览器也可以工作。** 如果用户已经提供了需求文本（即使是 URL），先用文本中能提取的任何信息开始分析。不要因为无法打开链接就停止——输出你目前能分析出的内容，并在 test_points 中标注哪些需要进一步确认。

请按照以下JSON格式输出：

{
  "title": "需求标题",
  "description": "需求详细描述",
  "business_modules": [
    {
      "name": "业务模块名称",
      "description": "模块描述",
      "priority": "high/medium/low"
    }
  ],
  "interfaces": [
    {
      "name": "接口名称",
      "method": "GET/POST/PUT/DELETE",
      "endpoint": "/api/endpoint",
      "description": "接口描述",
      "parameters": [
        {
          "name": "参数名",
          "type": "string/integer/boolean",
          "required": true/false,
          "description": "参数描述"
        }
      ]
    }
  ],
  "ui_elements": [
    {
      "name": "UI元素名称",
      "type": "button/input/form/table",
      "selector": "CSS选择器或XPath",
      "description": "元素描述"
    }
  ],
  "test_points": [
    {
      "id": "TP-001",
      "description": "测试点描述",
      "type": "functional/performance/security",
      "priority": "high/medium/low"
    }
  ],
  "test_scenarios": [
    {
      "name": "测试场景名称",
      "description": "场景描述",
      "preconditions": ["前置条件"],
      "steps": ["步骤1", "步骤2"],
      "expected_results": ["预期结果1", "预期结果2"]
    }
  ]
}

**重要规则：**
1. 你分析的是用户需求文档中**描述的系统/功能**，不是文档本身。
2. 如果用户提供的是在线文档链接，优先用 browser_navigate + browser_extract_content 提取；如果浏览器不可用，直接用用户提供的文本分析，不要卡住。
3. 如果用户提到了平台/应用名称但没有提供测试地址（URL），使用 ask_user 询问。
4. 如果测试涉及登录/认证，使用 ask_user 询问登录方式和凭据。
5. 如果用户需求描述模糊，使用 ask_user 要求用户补充。
6. 可以搜索知识库作为参考，但不要用知识库内容替代用户的实际需求。
7. 只有收集到足够信息后才输出 JSON。

**JSON 输出规则（非常重要！）：**
- 所有字段必须填入**真实的具体值**，不能复制示例模板中的占位符。
- title 必须是从需求中提取的真实标题，不能是"需求标题"。
- priority 必须是 high / medium / low 之一，不能是 "high/medium/low"。
- required 必须是 true 或 false，不能是 "true/false"。
- type 必须是具体的类型名如 string / integer / boolean / object，不能是 "string/integer/boolean"。
- test_points 中的 id 必须是 TP-001 这样的真实编号，不能是示例文本。
- 如果你没有足够信息填入某个字段，将其设为合理的默认值（如 priority: "medium", required: false），不要在 JSON 值里写说明文字。

请确保输出是有效的JSON格式，不要包含其他解释性文本。"""
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析需求
        
        Args:
            input_data: 包含需求文本的字典
            
        Returns:
            结构化需求数据
        """
        try:
            # 验证输入
            if not self.validate_input(input_data, ['demand']):
                raise ValueError("输入数据缺少'demand'字段")
            
            demand = input_data['demand']
            logger.info(f"开始解析需求，长度: {len(demand)}")
            
            # 构建提示词
            prompt = f"""请解析以下测试需求：

{demand}

请按照指定的JSON格式输出结构化需求。"""
            
            # 调用大模型
            response = self.call_llm(prompt, self.system_prompt)
            
            # 解析JSON响应
            structured_req = self.parse_json_response(response)
            
            # 添加元数据
            structured_req['metadata'] = {
                'agent': 'ReqAgent',
                'model': self.model,
                'input_length': len(demand),
                'output_timestamp': self.get_timestamp()
            }
            
            # 记录处理日志
            self.log_processing(input_data, structured_req)
            
            return structured_req
            
        except Exception as e:
            logger.error(f"需求解析失败: {e}")
            raise

    # ------------------------------------------------------------------
    # act() — 多轮交互式需求解析
    # ------------------------------------------------------------------

    def act(
        self,
        conversation_messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Generator[Dict[str, Any], Optional[str], None]:
        """Interactive requirement parsing with knowledge base search and user questions."""
        tools_prompt = format_tools_prompt(self._tools)
        full_system = self.system_prompt + "\n\n" + tools_prompt

        yield from super().act(conversation_messages, full_system)

    def _try_extract_artifact(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract structured requirement from the agent response."""
        try:
            data = self.parse_json_response(response)
            if "title" in data and ("test_points" in data or "test_scenarios" in data
                                     or "business_modules" in data):
                return {"key": "structured_requirement", "data": data}
        except Exception:
            pass
        return None

    def get_timestamp(self):
        """获取时间戳"""
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def extract_keywords(self, demand: str) -> list:
        """
        提取关键词
        
        Args:
            demand: 需求文本
            
        Returns:
            关键词列表
        """
        try:
            prompt = f"""请从以下需求中提取关键词（最多10个）：

{demand}

请以JSON数组格式输出：["关键词1", "关键词2", ...]"""
            
            response = self.call_llm(prompt, "你是一个关键词提取专家。")
            keywords = self.parse_json_response(response)
            
            return keywords if isinstance(keywords, list) else []
            
        except Exception as e:
            logger.error(f"关键词提取失败: {e}")
            return []
    
    def estimate_test_effort(self, structured_req: Dict[str, Any]) -> Dict[str, Any]:
        """
        估算测试工作量
        
        Args:
            structured_req: 结构化需求
            
        Returns:
            工作量估算
        """
        try:
            # 计算测试点数量
            test_points = len(structured_req.get('test_points', []))
            interfaces = len(structured_req.get('interfaces', []))
            ui_elements = len(structured_req.get('ui_elements', []))
            scenarios = len(structured_req.get('test_scenarios', []))
            
            # 简单估算公式
            total_cases = test_points + interfaces + ui_elements + scenarios
            estimated_hours = total_cases * 0.5  # 每个测试点0.5小时
            
            effort = {
                'test_points': test_points,
                'interfaces': interfaces,
                'ui_elements': ui_elements,
                'scenarios': scenarios,
                'total_cases': total_cases,
                'estimated_hours': round(estimated_hours, 1),
                'complexity': self.assess_complexity(structured_req)
            }
            
            return effort
            
        except Exception as e:
            logger.error(f"工作量估算失败: {e}")
            return {}
    
    def assess_complexity(self, structured_req: Dict[str, Any]) -> str:
        """
        评估需求复杂度
        
        Args:
            structured_req: 结构化需求
            
        Returns:
            复杂度等级（simple/medium/complex）
        """
        try:
            total_items = (
                len(structured_req.get('business_modules', [])) +
                len(structured_req.get('interfaces', [])) +
                len(structured_req.get('ui_elements', [])) +
                len(structured_req.get('test_points', []))
            )
            
            if total_items <= 5:
                return 'simple'
            elif total_items <= 15:
                return 'medium'
            else:
                return 'complex'
                
        except Exception as e:
            logger.error(f"复杂度评估失败: {e}")
            return 'unknown'