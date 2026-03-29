"""
代码生成智能体
"""

import json
import logging
import os
from typing import Dict, Any, List
from .base_agent import BaseAgent
from config import Config

logger = logging.getLogger(__name__)

class CodeAgent(BaseAgent):
    """代码生成智能体"""
    
    def __init__(self):
        super().__init__(model="deepseek/deepseek-chat", temperature=0.1)
        self.system_prompt = """你是一个专业的测试代码生成专家。你的任务是根据测试用例生成可执行的自动化测试代码。

请按照以下JSON格式输出：

{
  "scripts": [
    {
      "id": "对应测试用例ID",
      "title": "脚本标题",
      "description": "脚本描述",
      "language": "python/javascript",
      "framework": "pytest/playwright/jest",
      "code": "完整的测试代码",
      "dependencies": ["依赖包1", "依赖包2"],
      "execution_command": "执行命令",
      "expected_output": "预期输出"
    }
  ]
}

对于Python测试代码，请遵循以下规范：
1. 使用pytest框架
2. 包含必要的导入语句
3. 添加详细的注释
4. 包含断言语句
5. 处理异常情况

对于API测试，使用requests库。
对于UI测试，使用playwright库。

请确保输出是有效的JSON格式，不要包含其他解释性文本。"""
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成测试代码
        
        Args:
            input_data: 包含测试用例的字典
            
        Returns:
            生成的测试脚本
        """
        try:
            # 验证输入
            if not self.validate_input(input_data, ['test_cases']):
                raise ValueError("输入数据缺少'test_cases'字段")
            
            test_cases = input_data['test_cases']
            logger.info(f"开始生成测试代码，测试用例数: {len(test_cases.get('test_cases', []))}")
            
            # 生成代码
            scripts = []
            for test_case in test_cases.get('test_cases', []):
                script = self.generate_single_script(test_case, test_cases)
                if script:
                    scripts.append(script)
            
            result = {
                "scripts": scripts,
                "metadata": {
                    'agent': 'CodeAgent',
                    'model': self.model,
                    'script_count': len(scripts),
                    'generated_at': self.get_timestamp()
                }
            }
            
            # 记录处理日志
            self.log_processing(input_data, result)
            
            return result
            
        except Exception as e:
            logger.error(f"代码生成失败: {e}")
            raise
    
    def generate_single_script(self, test_case: Dict[str, Any], all_test_cases: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成单个测试脚本
        
        Args:
            test_case: 单个测试用例
            all_test_cases: 所有测试用例数据
            
        Returns:
            测试脚本
        """
        try:
            test_type = test_case.get('test_type', 'api').lower()
            
            # 根据测试类型选择模板
            if test_type == 'api':
                return self.generate_api_script(test_case)
            elif test_type == 'ui':
                return self.generate_ui_script(test_case)
            elif test_type == 'performance':
                return self.generate_performance_script(test_case)
            elif test_type == 'security':
                return self.generate_security_script(test_case)
            else:
                return self.generate_generic_script(test_case)
                
        except Exception as e:
            logger.error(f"生成测试脚本失败 (ID: {test_case.get('id', 'unknown')}): {e}")
            return None
    
    def generate_api_script(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """生成API测试脚本"""
        prompt = f"""请为以下API测试用例生成Python测试代码：

测试用例ID: {test_case.get('id')}
标题: {test_case.get('title')}
描述: {test_case.get('description')}
测试步骤: {json.dumps(test_case.get('test_steps', []), ensure_ascii=False)}
测试数据: {json.dumps(test_case.get('test_data', {}), ensure_ascii=False)}

要求：
1. 使用requests库进行HTTP请求
2. 使用pytest框架
3. 包含完整的断言
4. 添加详细的注释
5. 处理异常情况
6. 使用环境变量配置基础URL

请生成可直接执行的测试代码。"""
        
        response = self.call_llm(prompt, self.system_prompt)
        script_data = self.parse_json_response(response)
        
        # 确保返回的是单个脚本
        if 'scripts' in script_data and len(script_data['scripts']) > 0:
            script = script_data['scripts'][0]
        else:
            script = script_data
        
        # 添加元数据
        script['id'] = test_case.get('id')
        script['test_case_title'] = test_case.get('title')
        script['test_type'] = 'api'
        
        return script
    
    def generate_ui_script(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """生成UI测试脚本"""
        prompt = f"""请为以下UI测试用例生成Python测试代码：

测试用例ID: {test_case.get('id')}
标题: {test_case.get('title')}
描述: {test_case.get('description')}
测试步骤: {json.dumps(test_case.get('test_steps', []), ensure_ascii=False)}
测试数据: {json.dumps(test_case.get('test_data', {}), ensure_ascii=False)}

要求：
1. 使用playwright库进行浏览器自动化
2. 使用pytest框架
3. 使用Page Object Model设计模式
4. 包含完整的断言
5. 添加详细的注释
6. 处理异常情况
7. 支持headless模式

请生成可直接执行的测试代码。"""
        
        response = self.call_llm(prompt, self.system_prompt)
        script_data = self.parse_json_response(response)
        
        # 确保返回的是单个脚本
        if 'scripts' in script_data and len(script_data['scripts']) > 0:
            script = script_data['scripts'][0]
        else:
            script = script_data
        
        # 添加元数据
        script['id'] = test_case.get('id')
        script['test_case_title'] = test_case.get('title')
        script['test_type'] = 'ui'
        
        return script
    
    def generate_performance_script(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """生成性能测试脚本"""
        prompt = f"""请为以下性能测试用例生成Python测试代码：

测试用例ID: {test_case.get('id')}
标题: {test_case.get('title')}
描述: {test_case.get('description')}
测试步骤: {json.dumps(test_case.get('test_steps', []), ensure_ascii=False)}

要求：
1. 使用locust或pytest-benchmark库
2. 模拟并发用户
3. 测量响应时间
4. 生成性能报告
5. 包含性能断言（如响应时间阈值）

请生成可直接执行的性能测试代码。"""
        
        response = self.call_llm(prompt, self.system_prompt)
        script_data = self.parse_json_response(response)
        
        # 确保返回的是单个脚本
        if 'scripts' in script_data and len(script_data['scripts']) > 0:
            script = script_data['scripts'][0]
        else:
            script = script_data
        
        # 添加元数据
        script['id'] = test_case.get('id')
        script['test_case_title'] = test_case.get('title')
        script['test_type'] = 'performance'
        
        return script
    
    def generate_security_script(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """生成安全测试脚本"""
        prompt = f"""请为以下安全测试用例生成Python测试代码：

测试用例ID: {test_case.get('id')}
标题: {test_case.get('title')}
描述: {test_case.get('description')}
测试步骤: {json.dumps(test_case.get('test_steps', []), ensure_ascii=False)}

要求：
1. 测试常见安全漏洞（如SQL注入、XSS、CSRF等）
2. 使用requests库发送恶意请求
3. 验证安全防护机制
4. 包含安全断言

请生成可直接执行的安全测试代码。"""
        
        response = self.call_llm(prompt, self.system_prompt)
        script_data = self.parse_json_response(response)
        
        # 确保返回的是单个脚本
        if 'scripts' in script_data and len(script_data['scripts']) > 0:
            script = script_data['scripts'][0]
        else:
            script = script_data
        
        # 添加元数据
        script['id'] = test_case.get('id')
        script['test_case_title'] = test_case.get('title')
        script['test_type'] = 'security'
        
        return script
    
    def generate_generic_script(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """生成通用测试脚本"""
        prompt = f"""请为以下测试用例生成Python测试代码：

测试用例ID: {test_case.get('id')}
标题: {test_case.get('title')}
描述: {test_case.get('description')}
测试步骤: {json.dumps(test_case.get('test_steps', []), ensure_ascii=False)}
测试数据: {json.dumps(test_case.get('test_data', {}), ensure_ascii=False)}

要求：
1. 使用pytest框架
2. 包含完整的断言
3. 添加详细的注释
4. 处理异常情况

请生成可直接执行的测试代码。"""
        
        response = self.call_llm(prompt, self.system_prompt)
        script_data = self.parse_json_response(response)
        
        # 确保返回的是单个脚本
        if 'scripts' in script_data and len(script_data['scripts']) > 0:
            script = script_data['scripts'][0]
        else:
            script = script_data
        
        # 添加元数据
        script['id'] = test_case.get('id')
        script['test_case_title'] = test_case.get('title')
        script['test_type'] = test_case.get('test_type', 'generic')
        
        return script
    
    def save_scripts_to_files(self, scripts_data: Dict[str, Any], base_dir: str = None):
        """
        保存脚本到文件
        
        Args:
            scripts_data: 脚本数据
            base_dir: 基础目录
        """
        if base_dir is None:
            base_dir = os.path.join(Config.WORKSPACE, 'scripts')
        
        os.makedirs(base_dir, exist_ok=True)
        
        saved_files = []
        for script in scripts_data.get('scripts', []):
            try:
                # 生成文件名
                script_id = script.get('id', 'unknown').replace('/', '_').replace('\\', '_')
                language = script.get('language', 'python')
                
                if language == 'python':
                    ext = '.py'
                elif language == 'javascript':
                    ext = '.js'
                else:
                    ext = '.txt'
                
                filename = f"test_{script_id}{ext}"
                filepath = os.path.join(base_dir, filename)
                
                # 保存代码
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(script.get('code', ''))
                
                # 更新脚本信息
                script['file_path'] = filepath
                script['filename'] = filename
                
                saved_files.append(filepath)
                logger.info(f"脚本已保存: {filepath}")
                
            except Exception as e:
                logger.error(f"保存脚本失败 (ID: {script.get('id', 'unknown')}): {e}")
        
        return saved_files
    
    def get_timestamp(self):
        """获取时间戳"""
        from datetime import datetime
        return datetime.utcnow().isoformat()