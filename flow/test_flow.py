"""
测试工作流定义
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from agent.req_agent import ReqAgent
from agent.case_agent import CaseAgent
from agent.code_agent import CodeAgent
from agent.exec_agent import ExecAgent
from models import db, Requirement, TestCase, TestScript, ExecutionRecord, CodeReviewTask, CodeReviewFinding
from service.defect_service import defect_service
from service.report_service import report_service
from service.review_service import run_review_task

logger = logging.getLogger(__name__)


def _emit_event(requirement_id: int, agent: str, event_type: str, message: str, payload: Optional[Dict[str, Any]] = None):
    try:
        from service.agent_event_service import emit_agent_event

        emit_agent_event(requirement_id, agent, event_type, message, payload)
    except Exception as exc:
        logger.warning("emit_agent_event failed: %s", exc)


def _now():
    return datetime.now(timezone.utc)


class FlowDataAccess:
    """工作流数据访问层，封装所有 DB 读写操作"""

    @staticmethod
    def get_requirement(req_id: int):
        return db.session.get(Requirement, req_id)

    @staticmethod
    def update_requirement(req_id: int, **fields):
        req = db.session.get(Requirement, req_id)
        if req:
            for k, v in fields.items():
                setattr(req, k, v)
            req.updated_at = _now()
            db.session.commit()
        return req

    @staticmethod
    def get_cases(req_id: int):
        return TestCase.query.filter_by(requirement_id=req_id).all()

    @staticmethod
    def load_test_environment(req_id: int) -> dict:
        """从 Requirement.execution_progress 读取测试环境配置。"""
        requirement = db.session.get(Requirement, req_id)
        if requirement and requirement.execution_progress:
            return requirement.execution_progress.get("test_environment") or {}
        return {}

    @staticmethod
    def get_scripts_for_requirement(req_id: int):
        cases = TestCase.query.filter_by(requirement_id=req_id).all()
        case_ids = [c.id for c in cases]
        if not case_ids:
            return []
        return TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).all()

    @staticmethod
    def save_cases(case_list, requirement_id: int, test_suite_id=None, skip_reused=True):
        for case_data in case_list:
            if skip_reused and case_data.get('reused') and case_data.get('original_case_id'):
                continue
            tc = TestCase(
                requirement_id=requirement_id,
                test_suite_id=test_suite_id,
                title=case_data.get('title', '未命名'),
                description=case_data.get('description', ''),
                test_type=case_data.get('test_type', 'api'),
                priority=case_data.get('priority', 'medium'),
                steps=case_data.get('test_steps', []),
                expected_results=case_data.get('test_data', {}).get('expected_output'),
            )
            db.session.add(tc)
        db.session.commit()

    @staticmethod
    def save_scripts(scripts, requirement_id: int):
        cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
        for script_data in scripts:
            test_case_id = None
            script_id = str(script_data.get('id', ''))
            for case in cases:
                if case.title and script_id in case.title:
                    test_case_id = case.id
                    break
            if not test_case_id and cases:
                test_case_id = cases[0].id
            if test_case_id:
                code = script_data.get('code', '')
                if isinstance(code, list):
                    code = '\n'.join(str(line) for line in code)
                ts = TestScript(
                    test_case_id=test_case_id,
                    script_type=script_data.get('language', 'python'),
                    script_content=code,
                    file_path=script_data.get('file_path', ''),
                    status='generated',
                )
                db.session.add(ts)
        db.session.commit()

    @staticmethod
    def update_script_status(script_id: int, status: str):
        script = db.session.get(TestScript, script_id)
        if script:
            script.status = status
            db.session.commit()

    @staticmethod
    def create_execution_record(**kwargs):
        record = ExecutionRecord(**kwargs)
        db.session.add(record)
        return record

    @staticmethod
    def create_review_task(repo_url: str, branch: str, days: int, repo_path: str = "", repo_type: str = "remote"):
        task = CodeReviewTask(
            repo_url=repo_url or None,
            repo_path=repo_path or None,
            repo_type=repo_type,
            branch=branch,
            days=days,
            status='pending',
        )
        db.session.add(task)
        db.session.commit()
        return task

    @staticmethod
    def get_review_task(task_id: int):
        return db.session.get(CodeReviewTask, task_id)

    @staticmethod
    def count_review_findings(task_id: int):
        return CodeReviewFinding.query.filter_by(task_id=task_id).count()

    @staticmethod
    def set_execution_progress(req_id: int, progress: dict):
        req = db.session.get(Requirement, req_id)
        if req:
            req.execution_progress = progress
            db.session.commit()

    @staticmethod
    def build_test_cases_dict(req_id: int) -> Dict[str, Any]:
        cases = TestCase.query.filter_by(requirement_id=req_id).all()
        return {'test_cases': [
            {
                'id': c.id,
                'title': c.title,
                'description': c.description,
                'test_type': c.test_type,
                'priority': c.priority,
                'test_steps': c.steps,
            }
            for c in cases
        ]}

    @staticmethod
    def build_test_scripts_dict(req_id: int) -> Dict[str, Any]:
        scripts = FlowDataAccess.get_scripts_for_requirement(req_id)
        return {'scripts': [
            {
                'id': str(s.id),
                'code': s.script_content,
                'language': s.script_type,
                'file_path': s.file_path,
            }
            for s in scripts
        ]}


class AutoTestFlow:
    """自动化测试工作流（纯编排，数据访问通过 FlowDataAccess）"""

    def __init__(self):
        self.req_agent = ReqAgent()
        self.case_agent = CaseAgent()
        self.code_agent = CodeAgent()
        self.exec_agent = ExecAgent()
        self.da = FlowDataAccess()

        self.status = 'idle'
        self.current_step = None
        self.start_time = None
        self.end_time = None
        self.errors = []

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.start_time = _now()
            self.status = 'running'

            logger.info(f"开始执行工作流, 输入: {json.dumps(input_data, ensure_ascii=False)[:200]}...")

            requirement_id = input_data['requirement_id']
            project_id = input_data.get('project_id', 1)
            resume_from = input_data.get('resume_from')
            review_config = self._get_review_config(input_data)

            if not requirement_id:
                raise ValueError("缺少requirement_id")

            test_cases = {}
            # Resume 或从头开始
            if resume_from == 'code_generated':
                test_scripts = self.da.build_test_scripts_dict(requirement_id)
            elif resume_from == 'cases_generated':
                test_cases = self.da.build_test_cases_dict(requirement_id)
                self.current_step = 'generate_code'
                test_scripts = self.generate_code(test_cases, requirement_id)
            elif resume_from == 'executed':
                self.status = 'completed'
                self.end_time = _now()
                return {'status': 'success', 'requirement_id': requirement_id, 'message': '流程已完成'}
            else:
                test_env = input_data.get('test_environment') or {}
                if test_env.get('test_url'):
                    _emit_event(
                        requirement_id,
                        'BrowserAgent',
                        'progress',
                        f"打开测试地址 {test_env['test_url']}（agent-browser）",
                        test_env,
                    )

                self.current_step = 'parse_requirement'
                structured_req = self.parse_requirement(input_data['demand'], requirement_id)

                self.current_step = 'design_test_cases'
                test_cases = self.design_test_cases(structured_req, requirement_id)

                self.current_step = 'generate_code'
                test_scripts = self.generate_code(test_cases, requirement_id)

            self.current_step = 'execute_tests'
            execution_results = self.execute_tests(requirement_id)

            steps = ['parse_requirement', 'design_test_cases', 'generate_code', 'execute_tests']
            review_result = defect_result = report_result = None

            if review_config:
                self.current_step = 'code_review'
                review_result = self.run_code_review(review_config)
                steps.append('code_review')
                _emit_event(
                    requirement_id,
                    'CodeReviewAgent',
                    'completed',
                    f"发现 {review_result.get('finding_count', 0)} 条高风险变更",
                )

                if review_result.get('task_id'):
                    self.current_step = 'defect_analysis'
                    defect_result = defect_service.analyze_requirement(requirement_id, review_result['task_id'])
                    steps.append('defect_analysis')
                    _emit_event(
                        requirement_id,
                        'BugAgent',
                        'completed',
                        f"沉淀 {defect_result.get('defect_count', 0)} 条缺陷候选",
                    )

                    self.current_step = 'report_generation'
                    report = report_service.generate_requirement_report(requirement_id, review_result['task_id'])
                    report_result = report.to_dict()
                    steps.append('report_generation')

            self.status = 'completed'
            self.end_time = _now()

            result = {
                'status': 'success',
                'workflow_id': id(self),
                'requirement_id': requirement_id,
                'project_id': project_id,
                'steps_completed': steps,
                'statistics': {
                    'requirements_parsed': 1,
                    'test_cases_generated': len(test_cases.get('test_cases', [])),
                    'scripts_generated': len(test_scripts.get('scripts', [])),
                    'tests_executed': len(execution_results.get('executions', [])),
                    'review_findings': review_result.get('finding_count', 0) if review_result else 0,
                    'defect_candidates': defect_result.get('defect_count', 0) if defect_result else 0,
                    'execution_time': (self.end_time - self.start_time).total_seconds(),
                },
                'timestamps': {
                    'start': self.start_time.isoformat(),
                    'end': self.end_time.isoformat(),
                },
            }

            if review_result:
                result['review'] = review_result
            if defect_result:
                result['defects'] = defect_result
            if report_result:
                result['report'] = report_result

            logger.info(f"工作流执行完成")
            return result

        except Exception as e:
            self.status = 'failed'
            self.errors.append(str(e))
            self.end_time = _now()
            logger.error(f"工作流执行失败: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'failed_step': self.current_step,
                'errors': self.errors,
                'timestamps': {
                    'start': self.start_time.isoformat() if self.start_time else None,
                    'end': self.end_time.isoformat() if self.end_time else None,
                },
            }

    def _get_review_config(self, input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        review_data = input_data.get('review') or input_data.get('review_config') or {}
        if not review_data and input_data.get('review_repo_url'):
            review_data = {
                'repo_url': input_data.get('review_repo_url'),
                'repo_path': input_data.get('review_repo_path'),
                'branch': input_data.get('review_branch'),
                'days': input_data.get('review_days'),
            }

        repo_url = (review_data.get('repo_url') or '').strip() if isinstance(review_data, dict) else ''
        repo_path = (review_data.get('repo_path') or '').strip() if isinstance(review_data, dict) else ''
        if not repo_url and not repo_path:
            return None

        branch = (review_data.get('branch') or 'main').strip()
        try:
            days = int(review_data.get('days') or 7)
        except (TypeError, ValueError):
            days = 7

        config = {'branch': branch or 'main', 'days': max(days, 1)}
        if repo_path:
            config['repo_path'] = repo_path
            config['repo_type'] = 'local'
        else:
            config['repo_url'] = repo_url
            config['repo_type'] = 'remote'
        return config

    # ------------------------------------------------------------------
    # 各步骤
    # ------------------------------------------------------------------

    def parse_requirement(self, demand: str, requirement_id: int) -> Dict[str, Any]:
        logger.info(f"步骤1: 解析需求 (ID: {requirement_id})")
        _emit_event(requirement_id, 'ReqAgent', 'started', '开始解析需求')
        try:
            # Preserve original_document from structured_data before ReqAgent overwrites it
            requirement = self.da.get_requirement(requirement_id)
            orig_doc = (requirement.structured_data or {}).get("original_document") if requirement else None

            structured_req = self.req_agent.process({'demand': demand})

            # Carry forward the original_document reference for downstream agents
            if orig_doc:
                structured_req["original_document"] = orig_doc

            self.da.update_requirement(
                requirement_id,
                title=structured_req.get('title', ''),
                description=structured_req.get('description', ''),
                structured_data=structured_req,
                status='parsed',
            )
            _emit_event(requirement_id, 'ReqAgent', 'completed', '需求解析完成')
            logger.info(f"需求解析完成: {structured_req.get('title', '未命名')}")
            return structured_req
        except Exception as e:
            _emit_event(requirement_id, 'ReqAgent', 'failed', f'需求解析失败: {e}')
            logger.error(f"需求解析失败: {e}")
            self.errors.append(f"需求解析失败: {e}")
            raise

    def design_test_cases(self, structured_req: Dict[str, Any], requirement_id: int) -> Dict[str, Any]:
        logger.info(f"步骤2: 设计测试用例 (需求ID: {requirement_id})")
        _emit_event(requirement_id, 'CaseAgent', 'started', '开始设计测试用例')
        try:
            test_cases = self.case_agent.process({
                'structured_req': structured_req,
                'requirement_id': requirement_id,
            })

            suite_id = test_cases.get('metadata', {}).get('test_suite_id')
            self.da.save_cases(test_cases.get('test_cases', []), requirement_id, suite_id)
            self.da.update_requirement(requirement_id, status='cases_generated')

            count = len(test_cases.get('test_cases', []))
            _emit_event(requirement_id, 'CaseAgent', 'completed', f'生成 {count} 条测试用例')
            logger.info(f"测试用例设计完成, 生成 {count} 个用例")
            return test_cases
        except Exception as e:
            _emit_event(requirement_id, 'CaseAgent', 'failed', f'用例设计失败: {e}')
            logger.error(f"测试用例设计失败: {e}")
            self.errors.append(f"测试用例设计失败: {e}")
            raise

    def generate_code(self, test_cases: Dict[str, Any], requirement_id: int) -> Dict[str, Any]:
        logger.info(f"步骤3: 生成测试代码 (需求ID: {requirement_id})")
        _emit_event(requirement_id, 'CodeAgent', 'started', '开始生成 Playwright/API 脚本')
        try:
            env = self.da.load_test_environment(requirement_id)
            test_scripts = self.code_agent.process({
                'test_cases': test_cases,
                'test_environment': env,
            })
            self.da.save_scripts(test_scripts.get('scripts', []), requirement_id)
            self.da.update_requirement(requirement_id, status='code_generated')
            script_count = len(test_scripts.get('scripts', []))
            _emit_event(requirement_id, 'CodeAgent', 'completed', f'生成 {script_count} 个自动化脚本')
            logger.info(f"测试代码生成完成, 生成 {script_count} 个脚本")
            return test_scripts
        except Exception as e:
            _emit_event(requirement_id, 'CodeAgent', 'failed', f'脚本生成失败: {e}')
            logger.error(f"测试代码生成失败: {e}")
            self.errors.append(f"测试代码生成失败: {e}")
            raise

    def execute_tests(self, requirement_id: int) -> Dict[str, Any]:
        logger.info(f"步骤4: 执行测试 (需求ID: {requirement_id})")
        _emit_event(requirement_id, 'ExecAgent', 'started', '开始执行 Playwright/pytest')
        self.da.update_requirement(requirement_id, status='executing')
        self.da.set_execution_progress(requirement_id, {
            'total': 0, 'executed': 0, 'current_step': '准备中',
            'start_time': _now().isoformat(), 'details': [],
        })

        scripts = self.da.get_scripts_for_requirement(requirement_id)
        if not scripts:
            self.da.update_requirement(requirement_id, status='executed')
            self.da.set_execution_progress(requirement_id, {
                'total': 0, 'executed': 0, 'completed': True,
                'end_time': _now().isoformat(), 'details': [],
            })
            return {'executions': [], 'message': '没有测试脚本可执行'}

        total = len(scripts)
        executed = 0
        all_results = []
        details = []

        for idx, script in enumerate(scripts):
            try:
                detail = {
                    'script_id': script.id,
                    'script_name': script.file_path,
                    'case_id': script.test_case_id,
                    'status': 'running',
                    'start_time': _now().isoformat(),
                    'steps': [],
                }
                details.append(detail)

                self.da.update_script_status(script.id, 'running')
                self.da.set_execution_progress(requirement_id, {
                    'total': total, 'executed': executed,
                    'current_script_id': script.id,
                    'current_step': f'执行脚本 {idx + 1}/{total}',
                    'start_time': _now().isoformat(), 'details': details,
                })

                result = self.exec_agent.process({
                    'script_id': script.id,
                    'script_content': script.script_content,
                    'file_path': script.file_path,
                    'script_type': script.script_type,
                    'test_url': env.get('test_url', ''),
                })

                elapsed = result.get('execution_time', 0)
                detail['status'] = result.get('status', 'completed')
                detail['end_time'] = _now().isoformat()
                detail['execution_time'] = elapsed
                detail['error'] = result.get('error')
                detail['result'] = result.get('result', {})

                self.da.create_execution_record(
                    test_script_id=script.id,
                    status=result.get('status', 'unknown'),
                    result_data=result.get('result', {}),
                    error_message=result.get('error'),
                    execution_time=elapsed,
                    report_path=result.get('report_path'),
                    screenshot_paths=result.get('screenshots', []),
                    started_at=_now(),
                    finished_at=_now(),
                )
                all_results.append(result)
                self.da.update_script_status(script.id, 'executed')
                executed += 1

            except Exception as e:
                logger.error(f"执行脚本失败 (ID: {script.id}): {e}")
                detail['status'] = 'error'
                detail['end_time'] = _now().isoformat()
                detail['error'] = str(e)

                self.da.create_execution_record(
                    test_script_id=script.id,
                    status='error',
                    error_message=str(e),
                    started_at=_now(),
                    finished_at=_now(),
                )
                all_results.append({'script_id': script.id, 'status': 'error', 'error': str(e)})
                self.da.update_script_status(script.id, 'error')
                executed += 1

            db.session.commit()

        self.da.update_requirement(requirement_id, status='executed')
        self.da.set_execution_progress(requirement_id, {
            'total': total, 'executed': executed, 'completed': True,
            'end_time': _now().isoformat(), 'details': details,
        })

        _emit_event(requirement_id, 'ExecAgent', 'completed', f'执行完成，共 {len(all_results)} 个脚本')
        logger.info(f"测试执行完成, 执行 {len(all_results)} 个脚本")
        return {'executions': all_results}

    def run_code_review(self, review_config: Dict[str, Any]) -> Dict[str, Any]:
        task = self.da.create_review_task(
            review_config.get('repo_url', ''),
            review_config.get('branch', 'main'),
            review_config.get('days', 7),
            repo_path=review_config.get('repo_path', ''),
            repo_type=review_config.get('repo_type', 'remote'),
        )
        run_review_task(task.id)
        refreshed = self.da.get_review_task(task.id)
        finding_count = self.da.count_review_findings(task.id)
        return {
            'task_id': task.id,
            'repo_url': task.repo_url,
            'repo_path': task.repo_path,
            'repo_type': task.repo_type,
            'branch': task.branch,
            'days': task.days,
            'status': refreshed.status if refreshed else task.status,
            'summary': refreshed.summary if refreshed else task.summary,
            'error_message': refreshed.error_message if refreshed else task.error_message,
            'finding_count': finding_count,
        }

    # ------------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        return {
            'status': self.status,
            'current_step': self.current_step,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'errors': self.errors,
            'error_count': len(self.errors),
        }

    def cancel(self):
        if self.status == 'running':
            self.status = 'cancelled'
            self.end_time = _now()
            logger.info("工作流已取消")

    def pause(self):
        if self.status == 'running':
            self.status = 'paused'
            logger.info("工作流已暂停")

    def resume(self):
        if self.status == 'paused':
            self.status = 'running'
            logger.info("工作流已恢复")
