"""
测试工作流定义
"""

import json
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime

from agent.req_agent import ReqAgent
from agent.case_agent import CaseAgent
from agent.code_agent import CodeAgent
from agent.exec_agent import ExecAgent
from models import db, Requirement, TestCase, TestScript, ExecutionRecord

logger = logging.getLogger(__name__)

class AutoTestFlow:
    """自动化测试工作流"""
    
    def __init__(self):
        self.req_agent = ReqAgent()
        self.case_agent = CaseAgent()
        self.code_agent = CodeAgent()
        self.exec_agent = ExecAgent()
        
        # 工作流状态
        self.status = 'idle'
        self.current_step = None
        self.start_time = None
        self.end_time = None
        self.errors = []
        
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行完整的工作流
        
        Args:
            input_data: 输入数据，包含demand字段
            
        Returns:
            工作流执行结果
        """
        try:
            self.start_time = datetime.utcnow()
            self.status = 'running'
            
            logger.info(f"开始执行工作流，输入数据: {json.dumps(input_data, ensure_ascii=False)[:200]}...")
            
            # 获取需求ID
            requirement_id = input_data.get('requirement_id')
            project_id = input_data.get('project_id', 1)
            
            if not requirement_id:
                raise ValueError("缺少requirement_id")
            
            # 步骤1: 需求解析
            self.current_step = 'parse_requirement'
            structured_req = self.parse_requirement(input_data['demand'], requirement_id)
            
            # 步骤2: 测试用例设计
            self.current_step = 'design_test_cases'
            test_cases = self.design_test_cases(structured_req, requirement_id)
            
            # 步骤3: 代码生成
            self.current_step = 'generate_code'
            test_scripts = self.generate_code(test_cases, requirement_id)
            
            # 步骤4: 执行测试
            self.current_step = 'execute_tests'
            execution_results = self.execute_tests(test_scripts, requirement_id)
            
            # 完成工作流
            self.status = 'completed'
            self.end_time = datetime.utcnow()
            
            result = {
                'status': 'success',
                'workflow_id': id(self),
                'requirement_id': requirement_id,
                'project_id': project_id,
                'steps_completed': ['parse_requirement', 'design_test_cases', 'generate_code', 'execute_tests'],
                'statistics': {
                    'requirements_parsed': 1,
                    'test_cases_generated': len(test_cases.get('test_cases', [])),
                    'scripts_generated': len(test_scripts.get('scripts', [])),
                    'tests_executed': len(execution_results.get('executions', [])),
                    'execution_time': (self.end_time - self.start_time).total_seconds()
                },
                'timestamps': {
                    'start': self.start_time.isoformat(),
                    'end': self.end_time.isoformat()
                }
            }
            
            logger.info(f"工作流执行完成: {result}")
            return result
            
        except Exception as e:
            self.status = 'failed'
            self.errors.append(str(e))
            self.end_time = datetime.utcnow()
            
            logger.error(f"工作流执行失败: {e}")
            
            return {
                'status': 'failed',
                'error': str(e),
                'failed_step': self.current_step,
                'errors': self.errors,
                'timestamps': {
                    'start': self.start_time.isoformat() if self.start_time else None,
                    'end': self.end_time.isoformat() if self.end_time else None
                }
            }
    
    def parse_requirement(self, demand: str, requirement_id: int) -> Dict[str, Any]:
        """解析需求"""
        try:
            logger.info(f"步骤1: 解析需求 (ID: {requirement_id})")
            
            # 调用需求解析智能体
            input_data = {'demand': demand}
            structured_req = self.req_agent.process(input_data)
            
            # 更新需求记录
            with db.session.begin():
                requirement = Requirement.query.get(requirement_id)
                if requirement:
                    requirement.title = structured_req.get('title', requirement.title)
                    requirement.description = structured_req.get('description', requirement.description)
                    requirement.structured_data = structured_req
                    requirement.status = 'parsed'
                    requirement.updated_at = datetime.utcnow()
                    db.session.commit()
            
            logger.info(f"需求解析完成: {structured_req.get('title', '未命名')}")
            return structured_req
            
        except Exception as e:
            logger.error(f"需求解析失败: {e}")
            self.errors.append(f"需求解析失败: {e}")
            raise
    
    def design_test_cases(self, structured_req: Dict[str, Any], requirement_id: int) -> Dict[str, Any]:
        """设计测试用例"""
        try:
            logger.info(f"步骤2: 设计测试用例 (需求ID: {requirement_id})")
            
            # 调用测试用例设计智能体
            input_data = {'structured_req': structured_req}
            test_cases = self.case_agent.process(input_data)
            
            # 保存测试用例到数据库
            with db.session.begin():
                requirement = Requirement.query.get(requirement_id)
                if requirement:
                    for case_data in test_cases.get('test_cases', []):
                        test_case = TestCase(
                            requirement_id=requirement_id,
                            title=case_data.get('title', '未命名'),
                            description=case_data.get('description', ''),
                            test_type=case_data.get('test_type', 'api'),
                            priority=case_data.get('priority', 'medium'),
                            steps=case_data.get('test_steps', []),
                            expected_results=case_data.get('test_data', {}).get('expected_output')
                        )
                        db.session.add(test_case)
                    
                    requirement.updated_at = datetime.utcnow()
                    db.session.commit()
            
            logger.info(f"测试用例设计完成，生成 {len(test_cases.get('test_cases', []))} 个测试用例")
            return test_cases
            
        except Exception as e:
            logger.error(f"测试用例设计失败: {e}")
            self.errors.append(f"测试用例设计失败: {e}")
            raise
    
    def generate_code(self, test_cases: Dict[str, Any], requirement_id: int) -> Dict[str, Any]:
        """生成测试代码"""
        try:
            logger.info(f"步骤3: 生成测试代码 (需求ID: {requirement_id})")
            
            # 调用代码生成智能体
            input_data = {'test_cases': test_cases}
            test_scripts = self.code_agent.process(input_data)
            
            # 保存测试脚本到数据库和文件
            saved_files = self.code_agent.save_scripts_to_files(test_scripts)
            
            # 保存脚本信息到数据库
            with db.session.begin():
                # 获取该需求的所有测试用例
                requirement_cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
                case_map = {case.id: case for case in requirement_cases}
                
                for script_data in test_scripts.get('scripts', []):
                    # 查找对应的测试用例（通过ID匹配）
                    test_case_id = None
                    script_id = script_data.get('id', '')
                    
                    # 尝试从ID中提取测试用例ID
                    if script_id.startswith('TC-'):
                        # 查找对应的测试用例
                        for case in requirement_cases:
                            if case.title and script_id in case.title:
                                test_case_id = case.id
                                break
                    
                    # 如果没找到，使用第一个测试用例
                    if not test_case_id and requirement_cases:
                        test_case_id = requirement_cases[0].id
                    
                    if test_case_id:
                        test_script = TestScript(
                            test_case_id=test_case_id,
                            script_type=script_data.get('language', 'python'),
                            script_content=script_data.get('code', ''),
                            file_path=script_data.get('file_path', ''),
                            status='generated'
                        )
                        db.session.add(test_script)
                
                # 更新需求状态
                requirement = Requirement.query.get(requirement_id)
                if requirement:
                    requirement.updated_at = datetime.utcnow()
                    db.session.commit()
            
            logger.info(f"测试代码生成完成，生成 {len(test_scripts.get('scripts', []))} 个脚本，保存 {len(saved_files)} 个文件")
            return test_scripts
            
        except Exception as e:
            logger.error(f"测试代码生成失败: {e}")
            self.errors.append(f"测试代码生成失败: {e}")
            raise
    
    def execute_tests(self, test_scripts: Dict[str, Any], requirement_id: int) -> Dict[str, Any]:
        """执行测试"""
        try:
            logger.info(f"步骤4: 执行测试 (需求ID: {requirement_id})")
            
            # 获取该需求的测试脚本
            with db.session.begin():
                requirement_cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
                case_ids = [case.id for case in requirement_cases]
                
                test_scripts_db = TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).all()
            
            if not test_scripts_db:
                logger.warning(f"没有找到测试脚本，跳过执行")
                return {'executions': [], 'message': '没有测试脚本可执行'}
            
            # 执行测试
            execution_results = []
            for test_script in test_scripts_db:
                try:
                    logger.info(f"执行测试脚本: {test_script.id} ({test_script.file_path})")
                    
                    # 调用执行智能体
                    input_data = {
                        'script_id': test_script.id,
                        'script_content': test_script.script_content,
                        'file_path': test_script.file_path,
                        'script_type': test_script.script_type
                    }
                    
                    execution_result = self.exec_agent.process(input_data)
                    
                    # 保存执行记录
                    execution_record = ExecutionRecord(
                        test_script_id=test_script.id,
                        status=execution_result.get('status', 'unknown'),
                        result_data=execution_result.get('result', {}),
                        error_message=execution_result.get('error'),
                        execution_time=execution_result.get('execution_time'),
                        report_path=execution_result.get('report_path'),
                        started_at=datetime.fromisoformat(execution_result.get('started_at')) if execution_result.get('started_at') else datetime.utcnow(),
                        finished_at=datetime.utcnow()
                    )
                    
                    db.session.add(execution_record)
                    execution_results.append(execution_result)
                    
                    # 更新脚本状态
                    test_script.status = 'executed'
                    
                except Exception as e:
                    logger.error(f"执行测试脚本失败 (ID: {test_script.id}): {e}")
                    
                    # 记录失败的执行
                    execution_record = ExecutionRecord(
                        test_script_id=test_script.id,
                        status='error',
                        error_message=str(e),
                        started_at=datetime.utcnow(),
                        finished_at=datetime.utcnow()
                    )
                    
                    db.session.add(execution_record)
                    execution_results.append({
                        'script_id': test_script.id,
                        'status': 'error',
                        'error': str(e)
                    })
            
            # 提交所有更改
            db.session.commit()
            
            # 更新需求状态
            with db.session.begin():
                requirement = Requirement.query.get(requirement_id)
                if requirement:
                    requirement.status = 'executed'
                    requirement.updated_at = datetime.utcnow()
                    db.session.commit()
            
            logger.info(f"测试执行完成，执行 {len(execution_results)} 个脚本")
            return {'executions': execution_results}
            
        except Exception as e:
            logger.error(f"测试执行失败: {e}")
            self.errors.append(f"测试执行失败: {e}")
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """获取工作流状态"""
        return {
            'status': self.status,
            'current_step': self.current_step,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'errors': self.errors,
            'error_count': len(self.errors)
        }
    
    def cancel(self):
        """取消工作流"""
        if self.status == 'running':
            self.status = 'cancelled'
            self.end_time = datetime.utcnow()
            logger.info("工作流已取消")
    
    def pause(self):
        """暂停工作流"""
        if self.status == 'running':
            self.status = 'paused'
            logger.info("工作流已暂停")
    
    def resume(self):
        """恢复工作流"""
        if self.status == 'paused':
            self.status = 'running'
            logger.info("工作流已恢复")