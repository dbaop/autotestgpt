"""
测试用例设计智能体
"""

import json
import logging
from typing import Dict, Any, List
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

class CaseAgent(BaseAgent):
    """测试用例设计智能体"""
    
    def __init__(self):
        super().__init__(model="gpt-4", temperature=0.1)
        self.system_prompt = """你是一个专业的测试用例设计师。你的任务是根据结构化需求设计详细的测试用例。

请按照以下JSON格式输出测试用例：

{
  "test_cases": [
    {
      "id": "TC-001",
      "title": "测试用例标题",
      "description": "测试用例描述",
      "test_type": "api/ui/performance/security",
      "priority": "high/medium/low",
      "preconditions": ["前置条件1", "前置条件2"],
      "test_steps": [
        {
          "step": 1,
          "action": "操作描述",
          "expected": "预期结果"
        }
      ],
      "test_data": {
        "input": "输入数据",
        "expected_output": "预期输出"
      },
      "tags": ["标签1", "标签2"]
    }
  ]
}

请确保输出是有效的JSON格式，不要包含其他解释性文本。"""
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        设计测试用例
        
        Args:
            input_data: 包含结构化需求的字典
            
        Returns:
            测试用例数据
        """
        try:
            # 验证输入
            if not self.validate_input(input_data, ['structured_req']):
                raise ValueError("输入数据缺少'structured_req'字段")
            
            structured_req = input_data['structured_req']
            logger.info(f"开始设计测试用例，需求模块数: {len(structured_req.get('business_modules', []))}")
            
            # 构建提示词
            prompt = self.build_prompt(structured_req)
            
            # 调用大模型
            response = self.call_llm(prompt, self.system_prompt)
            
            # 解析JSON响应
            test_cases = self.parse_json_response(response)
            
            # 添加元数据
            test_cases['metadata'] = {
                'agent': 'CaseAgent',
                'model': self.model,
                'requirement_title': structured_req.get('title', '未知'),
                'test_case_count': len(test_cases.get('test_cases', [])),
                'generated_at': self.get_timestamp()
            }
            
            # 记录处理日志
            self.log_processing(input_data, test_cases)
            
            return test_cases
            
        except Exception as e:
            logger.error(f"测试用例设计失败: {e}")
            raise
    
    def build_prompt(self, structured_req: Dict[str, Any]) -> str:
        """
        构建提示词
        
        Args:
            structured_req: 结构化需求
            
        Returns:
            提示词文本
        """
        prompt_parts = []
        
        # 添加需求基本信息
        prompt_parts.append(f"需求标题: {structured_req.get('title', '未指定')}")
        prompt_parts.append(f"需求描述: {structured_req.get('description', '未指定')}")
        
        # 添加业务模块
        business_modules = structured_req.get('business_modules', [])
        if business_modules:
            prompt_parts.append("\n业务模块:")
            for module in business_modules:
                prompt_parts.append(f"  - {module.get('name')} ({module.get('priority')}): {module.get('description')}")
        
        # 添加接口
        interfaces = structured_req.get('interfaces', [])
        if interfaces:
            prompt_parts.append("\n接口列表:")
            for interface in interfaces:
                prompt_parts.append(f"  - {interface.get('method')} {interface.get('endpoint')}: {interface.get('description')}")
        
        # 添加UI元素
        ui_elements = structured_req.get('ui_elements', [])
        if ui_elements:
            prompt_parts.append("\nUI元素:")
            for element in ui_elements:
                prompt_parts.append(f"  - {element.get('type')} '{element.get('name')}': {element.get('description')}")
        
        # 添加测试点
        test_points = structured_req.get('test_points', [])
        if test_points:
            prompt_parts.append("\n测试点:")
            for point in test_points:
                prompt_parts.append(f"  - {point.get('id')} ({point.get('type')}, {point.get('priority')}): {point.get('description')}")
        
        # 添加测试场景
        test_scenarios = structured_req.get('test_scenarios', [])
        if test_scenarios:
            prompt_parts.append("\n测试场景:")
            for scenario in test_scenarios:
                prompt_parts.append(f"  - {scenario.get('name')}: {scenario.get('description')}")
        
        # 添加指令
        prompt_parts.append("\n请根据以上需求设计详细的测试用例。")
        prompt_parts.append("请确保测试用例覆盖所有业务模块、接口和测试点。")
        prompt_parts.append("为每个测试用例指定合适的测试类型（api/ui/performance/security）和优先级。")
        
        return "\n".join(prompt_parts)
    
    def get_timestamp(self):
        """获取时间戳"""
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def categorize_test_cases(self, test_cases: List[Dict[str, Any]]) -> Dict[str, List]:
        """
        分类测试用例
        
        Args:
            test_cases: 测试用例列表
            
        Returns:
            分类后的测试用例
        """
        categories = {
            'api': [],
            'ui': [],
            'performance': [],
            'security': [],
            'other': []
        }
        
        for test_case in test_cases:
            test_type = test_case.get('test_type', 'other').lower()
            
            if test_type in categories:
                categories[test_type].append(test_case)
            else:
                categories['other'].append(test_case)
        
        return categories
    
    def calculate_coverage(self, test_cases: List[Dict[str, Any]], structured_req: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算测试覆盖率
        
        Args:
            test_cases: 测试用例列表
            structured_req: 结构化需求
            
        Returns:
            覆盖率统计
        """
        try:
            # 统计需求元素
            total_elements = (
                len(structured_req.get('business_modules', [])) +
                len(structured_req.get('interfaces', [])) +
                len(structured_req.get('ui_elements', [])) +
                len(structured_req.get('test_points', []))
            )
            
            if total_elements == 0:
                return {'coverage_percentage': 0, 'covered_elements': 0, 'total_elements': 0}
            
            # 简单估算：每个测试用例覆盖1个元素
            covered_elements = min(len(test_cases), total_elements)
            coverage_percentage = round((covered_elements / total_elements) * 100, 1)
            
            return {
                'coverage_percentage': coverage_percentage,
                'covered_elements': covered_elements,
                'total_elements': total_elements,
                'test_case_count': len(test_cases)
            }
            
        except Exception as e:
            logger.error(f"覆盖率计算失败: {e}")
            return {'coverage_percentage': 0, 'error': str(e)}
    
    def generate_test_matrix(self, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成测试矩阵
        
        Args:
            test_cases: 测试用例列表
            
        Returns:
            测试矩阵
        """
        matrix = {
            'by_type': {},
            'by_priority': {},
            'by_module': {}
        }
        
        # 按类型统计
        for test_case in test_cases:
            test_type = test_case.get('test_type', 'unknown')
            matrix['by_type'][test_type] = matrix['by_type'].get(test_type, 0) + 1
            
            # 按优先级统计
            priority = test_case.get('priority', 'medium')
            matrix['by_priority'][priority] = matrix['by_priority'].get(priority, 0) + 1
            
            # 按模块统计（从tags中提取）
            tags = test_case.get('tags', [])
            for tag in tags:
                if tag.startswith('module:'):
                    module = tag.replace('module:', '')
                    matrix['by_module'][module] = matrix['by_module'].get(module, 0) + 1
        
        return matrix