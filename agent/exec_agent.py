"""
执行与报告智能体
"""

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

from jinja2 import Environment, FileSystemLoader

from .tool_agent import ToolCapableAgent
from .tools import format_tools_prompt
from config import Config

logger = logging.getLogger(__name__)

_TEMPLATE_ENV = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), '..', 'templates')))

STATUS_MAP = {
    'success': ('green', '通过'),
    'failed': ('orange', '失败'),
    'error': ('red', '错误'),
    'timeout': ('purple', '超时'),
}


class ExecAgent(ToolCapableAgent):
    """执行与报告智能体 — 支持工具调用"""

    def __init__(self):
        super().__init__(model="gpt-4", temperature=0.1, agent_type="exec_agent")

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if not self.validate_input(input_data, ['script_id', 'script_content']):
                raise ValueError("input_data missing required fields: script_id, script_content")

            script_id = input_data['script_id']
            script_content = input_data['script_content']
            file_path = input_data.get('file_path')
            script_type = input_data.get('script_type', 'python')
            test_url = input_data.get('test_url', '')

            logger.info(f"开始执行测试脚本: {script_id} (类型: {script_type})")

            # Capture before-screenshot if test_url is available
            screenshots = self._capture_execution_screenshots(
                script_id=script_id, test_url=test_url,
            )

            execution_result = self.execute_script(
                script_content=script_content,
                file_path=file_path,
                script_type=script_type,
                script_id=script_id,
            )

            # Capture after-screenshot
            after_screenshots = self._capture_execution_screenshots(
                script_id=script_id, test_url=test_url, suffix="after",
            )
            screenshots.extend(after_screenshots)

            report_data = self.generate_report(execution_result, script_id)

            result = {
                'script_id': script_id,
                'status': execution_result['status'],
                'execution_time': execution_result['execution_time'],
                'output': execution_result['output'],
                'error': execution_result['error'],
                'report_path': report_data.get('report_path'),
                'report_url': report_data.get('report_url'),
                'screenshots': screenshots,
                'started_at': execution_result['started_at'],
                'finished_at': execution_result['finished_at'],
                'result': {
                    'passed': execution_result['status'] == 'success',
                    'assertions': execution_result.get('assertions', 0),
                    'failures': execution_result.get('failures', 0),
                    'errors': execution_result.get('errors', 0),
                },
            }

            self.log_processing(input_data, result)
            return result

        except Exception as e:
            logger.error(f"执行测试失败: {e}")
            return {
                'script_id': input_data.get('script_id', 'unknown'),
                'status': 'error',
                'error': str(e),
                'screenshots': [],
                'started_at': datetime.now(timezone.utc).isoformat(),
                'finished_at': datetime.now(timezone.utc).isoformat(),
            }

    # ------------------------------------------------------------------
    # 脚本执行
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # act() — interactive execution
    # ------------------------------------------------------------------

    def act(
        self,
        conversation_messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Generator[Dict[str, Any], Optional[str], None]:
        """Interactive test execution with file reading, CDP probing, and self-healing."""
        tools_prompt = format_tools_prompt(self._tools)
        full_system = (
            "You are a test execution engineer with browser CDP access for self-healing "
            "and visual evidence collection.\n\n"
            "## Your workflow\n"
            "1. Read the test scripts with read_workspace_file.\n"
            "2. Use get_requirement_environment to get the test URL.\n"
            "3. Use browser_navigate to open the test URL, then browser_screenshot "
            "to capture a BEFORE screenshot — the user needs visual evidence of what passed or failed.\n"
            "4. Execute the scripts and collect results.\n"
            "5. After execution, use browser_screenshot again to capture an AFTER screenshot.\n"
            "6. If a test FAILS with a selector/locator error (e.g. 'selector not found', "
            "'element not visible', 'no such element'):\n"
            "   a. Use browser_navigate to open the same URL the test was targeting.\n"
            "   b. Use browser_snapshot to capture the current DOM.\n"
            "   c. Compare the failed selector with the actual DOM elements.\n"
            "   d. Find the correct selector from the snapshot and report the fix.\n"
            "7. If the page looks different from what the test expects, take a browser_screenshot.\n"
            "8. Produce a **script_fix** artifact with the corrected selectors.\n\n"
            + tools_prompt
        )
        yield from super().act(conversation_messages, full_system)

    def _try_extract_artifact(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract a script_fix artifact from the agent response (self-healing)."""
        try:
            data = self.parse_json_response(response)
            if isinstance(data, dict) and ("fixed_selectors" in data or "fixed_script" in data):
                return {"key": "script_fix", "data": data}
        except Exception:
            pass
        return None

    def execute_script(self, script_content: str, file_path: Optional[str] = None,
                       script_type: str = 'python', script_id: str = None) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc)

        try:
            resolved_path = self._resolve_file_path(script_content, file_path, script_id, script_type)
            cmd = self._build_command(script_type, resolved_path)
            return self._run_subprocess(cmd, resolved_path, started_at, parse_pytest=(script_type == 'python'))

        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            return {
                'status': 'error',
                'error': str(e),
                'output': '',
                'execution_time': (finished_at - started_at).total_seconds(),
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat(),
            }

    def _resolve_file_path(self, script_content: str, file_path: Optional[str],
                           script_id: str, script_type: str) -> str:
        if file_path and os.path.exists(file_path):
            return file_path

        ext = '.py' if script_type in ('python', 'playwright') else '.js'
        if script_type == 'playwright':
            sub_dir = 'ui_tests'
        else:
            sub_dir = 'temp'

        target_dir = os.path.join(Config.WORKSPACE, sub_dir)
        os.makedirs(target_dir, exist_ok=True)

        filename = f"test_{script_id or 'temp'}{ext}"
        resolved = os.path.join(target_dir, filename)

        with open(resolved, 'w', encoding='utf-8') as f:
            f.write(script_content)

        return resolved

    def _build_command(self, script_type: str, file_path: str):
        if script_type == 'python' or script_type == 'playwright':
            return ['python', '-m', 'pytest', os.path.abspath(file_path), '-v', '--tb=short', '--disable-warnings']
        elif script_type == 'javascript':
            return ['node', file_path]
        else:
            raise ValueError(f"不支持的脚本类型: {script_type}")

    # ------------------------------------------------------------------
    # 通用子进程执行
    # ------------------------------------------------------------------

    def _run_subprocess(self, cmd, file_path: str, started_at, parse_pytest: bool = False) -> Dict[str, Any]:
        try:
            logger.info(f"执行命令: {' '.join(cmd)}")
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=os.path.dirname(file_path),
            )
            elapsed = time.time() - start_time
            finished_at = datetime.now(timezone.utc)

            output = result.stdout + result.stderr

            assertions = failures = errors = 0
            if parse_pytest:
                assertions, failures, errors = self._parse_pytest_summary(output)

            if result.returncode == 0:
                status = 'success'
                error = None
            elif parse_pytest and result.returncode == 5:
                # pytest exit code 5 = no tests collected (script lacks a test_*
                # function / isn't a valid pytest module). Make this explicit.
                status = 'failed'
                error = (
                    "pytest 未收集到任何用例（返回码 5）。生成的脚本可能缺少 test_ 函数、"
                    "不是 pytest 格式，或为说明文字/非 Python 代码。\n\n"
                    f"[STDOUT]\n{result.stdout}"
                )
            else:
                status = 'failed'
                error_parts = []
                if result.stderr:
                    error_parts.append(f"[STDERR]\n{result.stderr}")
                if result.stdout:
                    error_parts.append(f"[STDOUT]\n{result.stdout}")
                error_parts.append(f"[返回码] {result.returncode}")
                error = '\n\n'.join(error_parts)

            return {
                'status': status,
                'output': output,
                'error': error,
                'execution_time': elapsed,
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat(),
                'assertions': assertions,
                'failures': failures,
                'errors': errors,
                'returncode': result.returncode,
            }

        except subprocess.TimeoutExpired:
            finished_at = datetime.now(timezone.utc)
            return {
                'status': 'error',
                'error': f"脚本执行超时 (超过5分钟)\n\n脚本路径: {file_path}",
                'output': '',
                'execution_time': (finished_at - started_at).total_seconds(),
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat(),
            }
        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            import traceback
            return {
                'status': 'error',
                'error': f"[{type(e).__name__}] {e}\n\n{os.path.basename(file_path)}\n\n{traceback.format_exc()}",
                'output': '',
                'execution_time': (finished_at - started_at).total_seconds(),
                'started_at': started_at.isoformat(),
                'finished_at': finished_at.isoformat(),
            }

    # ------------------------------------------------------------------
    # 截图采集
    # ------------------------------------------------------------------

    def _capture_execution_screenshots(self, script_id, test_url="", suffix="before") -> list:
        """Take a screenshot of the test target page via BrowserProbe.

        Does not raise — failures are logged and returned as empty list.
        """
        screenshots = []
        if not test_url:
            return screenshots
        try:
            from service.browser_probe_service import get_browser_probe
            from service.screenshot_service import save_screenshot_from_data_url

            probe = get_browser_probe()
            nav = probe.navigate(test_url)
            if not nav.get("ok"):
                logger.info("Screenshot skip: browser navigate failed for %s", test_url)
                return screenshots

            result = probe.screenshot()
            if result.get("ok") and result.get("data_url"):
                path = save_screenshot_from_data_url(
                    result["data_url"], prefix=f"exec_{script_id}_{suffix}",
                )
                if path:
                    screenshots.append(path)
        except Exception as exc:
            logger.warning("Screenshot capture failed (non-fatal): %s", exc)
        return screenshots

    @staticmethod
    def _parse_pytest_summary(output: str):
        assertions = failures = errors = 0
        for line in output.split('\n'):
            if 'passed' in line:
                m = re.search(r'(\d+) passed', line)
                if m:
                    assertions = int(m.group(1))
            if 'failed' in line:
                m = re.search(r'(\d+) failed', line)
                if m:
                    failures = int(m.group(1))
            if 'error' in line and 'passed' not in line and 'failed' not in line:
                m = re.search(r'(\d+) error', line)
                if m:
                    errors = int(m.group(1))
        return assertions, failures, errors

    # ------------------------------------------------------------------
    # 报告生成
    # ------------------------------------------------------------------

    def generate_report(self, execution_result: Dict[str, Any], script_id: str) -> Dict[str, Any]:
        try:
            report_dir = os.path.join(Config.REPORT_DIR, 'html')
            os.makedirs(report_dir, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_filename = f"report_{script_id}_{timestamp}.html"
            report_path = os.path.join(report_dir, report_filename)

            html_content = self._render_html_report(execution_result, script_id)

            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"测试报告已生成: {report_path}")

            json_report_path = report_path.replace('.html', '.json')
            with open(json_report_path, 'w', encoding='utf-8') as f:
                json.dump(execution_result, f, ensure_ascii=False, indent=2, default=str)

            return {
                'report_path': report_path,
                'json_report_path': json_report_path,
                'report_url': f"/reports/{report_filename}",
            }

        except Exception as e:
            logger.error(f"生成报告失败: {e}")
            return {}

    def _render_html_report(self, execution_result: Dict[str, Any], script_id: str) -> str:
        status = execution_result.get('status', 'unknown')
        status_color, status_text = STATUS_MAP.get(status, ('gray', status))

        template = _TEMPLATE_ENV.get_template('report.html')
        return template.render(
            script_id=script_id,
            status_color=status_color,
            status_text=status_text,
            execution_time=execution_result.get('execution_time', 0),
            assertions=execution_result.get('assertions', 0),
            passed=execution_result.get('assertions', 0),
            screenshots=execution_result.get('screenshots', []),
            started_at=execution_result.get('started_at', 'N/A'),
            finished_at=execution_result.get('finished_at', 'N/A'),
            returncode=execution_result.get('returncode', 'N/A'),
            error=execution_result.get('error', ''),
            output=execution_result.get('output', ''),
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
