"""
执行与报告智能体
"""

import json
import logging
import subprocess
import os
import tempfile
import time
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from .base_agent import BaseAgent
from config import Config

logger = logging.getLogger(__name__)

class ExecAgent(BaseAgent):
    """执行与报告智能体"""
    
    def __init__(self):
        super().__init__(model="gpt-4", temperature=0.1)
        
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行测试脚本并生成报告
        
        Args:
            input_data: 包含脚本信息的字典
            
        Returns:
            执行结果
        """
        try:
            # 验证输入
            required_fields = ['script_id', 'script_content']
            if not self.validate_input(input_data, required_fields):
                raise ValueError(f"输入数据缺少必需字段: {required_fields}")
            
            script_id = input_data['script_id']
            script_content = input_data['script_content']
            file_path = input_data.get('file_path')
            script_type = input_data.get('script_type', 'python')
            
            logger.info(f"开始执行测试脚本: {script_id} (类型: {script_type})")
            
            # 执行测试
            execution_result = self.execute_script(
                script_content=script_content,
                file_path=file_path,
                script_type=script_type,
                script_id=script_id
            )
            
            # 生成报告
            report_data = self.generate_report(execution_result, script_id)
            
            # 合并结果
            result = {
                'script_id': script_id,
                'status': execution_result['status'],
                'execution_time': execution_result['execution_time'],
                'output': execution_result['output'],
                'error': execution_result['error'],
                'report_path': report_data.get('report_path'),
                'report_url': report_data.get('report_url'),
                'started_at': execution_result['started_at'],
                'finished_at': execution_result['finished_at'],
                'result': {
                    'passed': execution_result['status'] == 'success',
                    'assertions': execution_result.get('assertions', 0),
                    'failures': execution_result.get('failures', 0),
                    'errors': execution_result.get('errors', 0)
                }
            }
            
            # 记录处理日志
            self.log_processing(input_data, result)
            
            return result
            
        except Exception as e:
            logger.error(f"执行测试失败: {e}")
            return {
                'script_id': input_data.get('script_id', 'unknown'),
                'status': 'error',
                'error': str(e),
                'started_at': datetime.utcnow().isoformat(),
                'finished_at': datetime.utcnow().isoformat()
            }
    
    def execute_script(self, script_content: str, file_path: Optional[str] = None, 
                      script_type: str = 'python', script_id: str = None) -> Dict[str, Any]:
        """
        执行测试脚本
        
        Args:
            script_content: 脚本内容
            file_path: 脚本文件路径（如果已保存）
            script_type: 脚本类型
            script_id: 脚本ID
            
        Returns:
            执行结果
        """
        started_at = datetime.utcnow()
        
        try:
            # 如果文件不存在，创建临时文件
            if not file_path or not os.path.exists(file_path):
                temp_dir = os.path.join(Config.WORKSPACE, 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                
                filename = f"test_{script_id or 'temp'}.py"
                file_path = os.path.join(temp_dir, filename)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(script_content)
            
            # 根据脚本类型选择执行方式
            if script_type == 'python':
                return self.execute_python_script(file_path, started_at)
            elif script_type == 'javascript':
                return self.execute_javascript_script(file_path, started_at)
            else:
                raise ValueError(f"不支持的脚本类型: {script_type}")
                
        except Exception as e:
            finished_at = datetime.utcnow()
            execution_time = (finished_at - started_at).total_seconds()
            
            return {
                'status': 'error',
                'error': str(e),
                'output': '',
                'execution_time': execution_time,
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat()
            }
    
    def execute_python_script(self, file_path: str, started_at: datetime) -> Dict[str, Any]:
        """执行Python脚本"""
        try:
            # 使用pytest执行测试
            cmd = [
                'python', '-m', 'pytest',
                file_path,
                '--tb=short',
                '--disable-warnings',
                '--json-report',
                f'--json-report-file={file_path}.report.json'
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 执行命令
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                cwd=os.path.dirname(file_path)
            )
            end_time = time.time()
            
            execution_time = end_time - start_time
            finished_at = datetime.utcnow()
            
            # 解析pytest输出
            output = result.stdout + result.stderr
            
            # 检查JSON报告文件
            report_file = f"{file_path}.report.json"
            report_data = {}
            if os.path.exists(report_file):
                try:
                    with open(report_file, 'r', encoding='utf-8') as f:
                        report_data = json.load(f)
                except Exception as e:
                    logger.warning(f"解析JSON报告失败: {e}")
            
            # 确定执行状态
            if result.returncode == 0:
                status = 'success'
                error = None
            else:
                status = 'failed'
                error = result.stderr if result.stderr else "测试执行失败"
            
            return {
                'status': status,
                'output': output,
                'error': error,
                'execution_time': execution_time,
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat(),
                'assertions': report_data.get('summary', {}).get('total', 0),
                'failures': report_data.get('summary', {}).get('failed', 0),
                'errors': report_data.get('summary', {}).get('errors', 0)
            }
            
        except subprocess.TimeoutExpired:
            finished_at = datetime.utcnow()
            execution_time = (finished_at - started_at).total_seconds()
            
            logger.error(f"脚本执行超时 (超过5分钟): {file_path}")
            return {
                'status': 'error',
                'error': '脚本执行超时 (超过5分钟)',
                'output': '',
                'execution_time': execution_time,
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat()
            }
        except Exception as e:
            finished_at = datetime.utcnow()
            execution_time = (finished_at - started_at).total_seconds()
            
            logger.error(f"执行Python脚本失败: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'output': '',
                'execution_time': execution_time,
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat()
            }
    
    def execute_javascript_script(self, file_path: str, started_at: datetime) -> Dict[str, Any]:
        """执行JavaScript脚本"""
        try:
            # 使用Node.js执行
            cmd = ['node', file_path]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 执行命令
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                cwd=os.path.dirname(file_path)
            )
            end_time = time.time()
            
            execution_time = end_time - start_time
            finished_at = datetime.utcnow()
            
            output = result.stdout + result.stderr
            
            if result.returncode == 0:
                status = 'success'
                error = None
            else:
                status = 'failed'
                error = result.stderr if result.stderr else "测试执行失败"
            
            return {
                'status': status,
                'error': error,
                'output': output,
                'execution_time': execution_time,
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat(),
                'returncode': result.returncode
            }
            
        except Exception as e:
            finished_at = datetime.utcnow()
            execution_time = (finished_at - started_at).total_seconds()
            
            return {
                'status': 'error',
                'error': str(e),
                'output': '',
                'execution_time': execution_time,
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat()
            }
    
    def generate_report(self, execution_result: Dict[str, Any], script_id: str) -> Dict[str, Any]:
        """
        生成测试报告
        
        Args:
            execution_result: 执行结果
            script_id: 脚本ID
            
        Returns:
            报告信息
        """
        try:
            # 创建报告目录
            report_dir = os.path.join(Config.REPORT_DIR, 'html')
            os.makedirs(report_dir, exist_ok=True)
            
            # 生成报告文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_filename = f"report_{script_id}_{timestamp}.html"
            report_path = os.path.join(report_dir, report_filename)
            
            # 生成HTML报告
            html_content = self.generate_html_report(execution_result, script_id)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"测试报告已生成: {report_path}")
            
            # 生成JSON报告（用于API）
            json_report_path = report_path.replace('.html', '.json')
            with open(json_report_path, 'w', encoding='utf-8') as f:
                json.dump(execution_result, f, ensure_ascii=False, indent=2, default=str)
            
            return {
                'report_path': report_path,
                'json_report_path': json_report_path,
                'report_url': f"/reports/{report_filename}"
            }
            
        except Exception as e:
            logger.error(f"生成报告失败: {e}")
            return {}
    
    def generate_html_report(self, execution_result: Dict[str, Any], script_id: str) -> str:
        """生成HTML报告"""
        status = execution_result['status']
        execution_time = execution_result.get('execution_time', 0)
        error = execution_result.get('error', '')
        output = execution_result.get('output', '')
        
        # 状态颜色
        if status == 'success':
            status_color = 'green'
            status_text = '通过'
        elif status == 'failed':
            status_color = 'orange'
            status_text = '失败'
        elif status == 'error':
            status_color = 'red'
            status_text = '错误'
        elif status == 'timeout':
            status_color = 'purple'
            status_text = '超时'
        else:
            status_color = 'gray'
            status_text = status
        
        # 生成HTML
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试报告 - {script_id}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        .header {{
            border-bottom: 2px solid #eee;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .title {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
        }}
        .subtitle {{
            font-size: 16px;
            color: #666;
        }}
        .status-badge {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            color: white;
            background-color: {status_color};
            margin-top: 10px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: #f8f9fa;
            border-radius: 6px;
            padding: 20px;
            text-align: center;
        }}
        .summary-card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}
        .summary-card .label {{
            font-size: 14px;
            color: #666;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section-title {{
            font-size: 18px;
            font-weight: bold;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }}
        .output {{
            background: #f8f9fa;
            border-radius: 6px;
            padding: 15px;
            font-family: monospace;
            white-space: pre-wrap;
            max-height: 400px;
            overflow-y: auto;
            font-size: 12px;
        }}
        .error {{
            background: #fff5f5;
            border-left: 4px solid #f56565;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .timestamp {{
            color: #888;
            font-size: 14px;
            margin-top: 5px;
        }}
        .metadata {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metadata-item {{
            background: #f8f9fa;
            padding: 10px 15px;
            border-radius: 4px;
        }}
        .metadata-label {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }}
        .metadata-value {{
            font-size: 14px;
            color: #333;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">测试执行报告</div>
            <div class="subtitle">脚本ID: {script_id}</div>
            <div class="status-badge">{status_text}</div>
            <div class="timestamp">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        
        <div class="summary">
            <div class="summary-card">
                <div class="value">{status_text}</div>
                <div class="label">执行状态</div>
            </div>
            <div class="summary-card">
                <div class="value">{execution_time:.2f}s</div>
                <div class="label">执行时间</div>
            </div>
            <div class="summary-card">
                <div class="value">{execution_result.get('assertions', 0)}</div>
                <div class="label">断言数量</div>
            </div>
            <div class="summary-card">
                <div class="value">{execution_result.get('passed', 0)}</div>
                <div class="label">通过数量</div>
            </div>
        </div>
        
        <div class="metadata">
            <div class="metadata-item">
                <div class="metadata-label">开始时间</div>
                <div class="metadata-value">{execution_result.get('started_at', 'N/A')}</div>
            </div>
            <div class="metadata-item">
                <div class="metadata-label">结束时间</div>
                <div class="metadata-value">{execution_result.get('finished_at', 'N/A')}</div>
            </div>
            <div class="metadata-item">
                <div class="metadata-label">返回码</div>
                <div class="metadata-value">{execution_result.get('returncode', 'N/A')}</div>
            </div>
        </div>
        
        {f'<div class="section"><div class="section-title">错误信息</div><div class="error">{error}</div></div>' if error else ''}
        
        <div class="section">
            <div class="section-title">执行输出</div>
            <div class="output">{output}</div>
        </div>
    </div>
</body>
</html>"""
        
        return html