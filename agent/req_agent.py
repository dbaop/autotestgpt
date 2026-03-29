"""
需求解析智能体
"""

import json
import logging
from typing import Dict, Any
from .base_agent import BaseAgent
from config import Config

logger = logging.getLogger(__name__)

class ReqAgent(BaseAgent):
    """需求解析智能体"""
    
    def __init__(self):
        super().__init__(model="gpt-4", temperature=0.1)
        self.system_prompt = """你是一个专业的测试需求分析师。你的任务是将自然语言需求解析为结构化的测试需求。

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