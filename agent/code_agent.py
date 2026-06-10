"""
Code generation agent.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

from .tool_agent import ToolCapableAgent
from .tools import format_tools_prompt
from config import Config

logger = logging.getLogger(__name__)


class CodeAgent(ToolCapableAgent):
    """Generate executable test scripts from test cases."""

    def __init__(self):
        super().__init__(model="deepseek/deepseek-chat", temperature=0.1, agent_type="code_agent")
        if self.custom_system_prompt:
            self.api_test_prompt = self.custom_system_prompt
            self.ui_test_prompt = self.custom_system_prompt
        else:
            self.api_test_prompt = (
                "You are a senior API test automation engineer. "
                "Return strict JSON with key `scripts` as a list of script objects."
            )
            self.ui_test_prompt = (
                "You are a senior UI automation engineer with Playwright expertise. "
                "You have access to browser_snapshot, browser_navigate, and browser_screenshot tools. "
                "ALWAYS use real selectors from the page_map artifact. "
                "If the page_map doesn't cover an element you need, call browser_snapshot to find it. "
                "Never guess or invent CSS selectors — every selector must be verifiable. "
                "Return strict JSON with key `scripts` as a list of script objects.\n\n"
                "For EVERY UI test case, each script object MUST include BOTH:\n"
                "  1. `code`: a Playwright Python script (deliverable, for archival/manual reuse).\n"
                "  2. `dsl`: a Given-When-Then JSON object executed in a real browser via CDP. Shape:\n"
                "     {\n"
                '       "given": {"action": "navigate", "url": "/login or full URL"},\n'
                '       "when": [ {"action": "fill|click|select|wait", "selector": "<real css>", "value": "<for fill/select>"} ],\n'
                '       "then": [ {"type": "url_contains", "value": "/dashboard"},\n'
                '                 {"type": "element_visible", "selector": "<css>"},\n'
                '                 {"type": "element_text", "selector": "<css>", "contains": "<text>"},\n'
                '                 {"type": "element_count", "selector": "<css>", "min": 1} ]\n'
                "     }\n"
                "  - `when.action` ∈ navigate|fill|click|select|wait. `then.type` ∈ "
                "url_contains|element_visible|element_text|element_count.\n"
                "  - Every selector MUST come from the page_map (real DOM). `given.url` may be relative "
                "(it is resolved against the test URL). Include at least one `then` assertion."
            )

    def build_prompt(self, test_cases: Dict[str, Any], test_environment: Dict[str, Any] = None,
                     page_map: Dict[str, Any] = None) -> str:
        test_case_list = test_cases.get("test_cases", [])
        if not test_case_list:
            return "Generate one minimal pytest script."

        prompt_parts: List[str] = [
            "Generate executable automated test code for the following test cases.",
            "Return JSON with `scripts`.",
            "CRITICAL: Use ONLY real CSS selectors from the page_map below. "
            "Do NOT invent or guess selectors. If a needed element is not in the page_map, "
            "use browser_snapshot to find it first.",
        ]

        env = test_environment or {}
        if env.get("test_url"):
            prompt_parts.append(f"\nTest environment URL: {env['test_url']}")
            prompt_parts.append("Use this URL as the base for API requests and Playwright page.goto().")
        if env.get("login_state"):
            prompt_parts.append(f"Login state: {env['login_state']}")
        if env.get("credential_ref"):
            prompt_parts.append(f"Credentials: {env['credential_ref']}")

        # 注入 page_map 中的真实选择器
        if page_map:
            prompt_parts.append("\n## Page Map (real DOM selectors — use these EXACTLY)")
            prompt_parts.append(f"Base URL: {page_map.get('base_url', 'N/A')}")
            for page in page_map.get("pages", []):
                prompt_parts.append(f"\n### Page: {page.get('title', '')} ({page.get('route', page.get('url', ''))})")
                elements = page.get("elements", [])
                if elements:
                    prompt_parts.append("| Tag | Selector | Fallback | Type | Label | Purpose |")
                    prompt_parts.append("|-----|----------|----------|------|-------|---------|")
                    for el in elements:
                        selector = el.get("selector", "")
                        fallback = ", ".join(el.get("fallback_selectors", [])[:2])
                        prompt_parts.append(
                            f"| {el.get('tag', '')} | `{selector}` | {fallback} | "
                            f"{el.get('type', '')} | {el.get('label', el.get('placeholder', ''))} | "
                            f"{el.get('purpose', '')} |"
                        )
                actions = page.get("actions", [])
                if actions:
                    prompt_parts.append(f"Actions: {' → '.join(actions)}")
            flows = page_map.get("flows", [])
            if flows:
                prompt_parts.append("\n## Discovered Flows")
                for flow in flows:
                    steps = " → ".join(flow.get("steps", []))
                    prompt_parts.append(f"- **{flow.get('name', '')}**: {steps}")

        for i, tc in enumerate(test_case_list, 1):
            prompt_parts.append(f"\n### Test Case {i}")
            prompt_parts.append(f"ID: {tc.get('id', f'TC-{i}')}")
            prompt_parts.append(f"Title: {tc.get('title', 'Untitled')}")
            prompt_parts.append(f"Description: {tc.get('description', '')}")
            prompt_parts.append(f"Type: {tc.get('test_type', 'api')}")
            prompt_parts.append(f"Priority: {tc.get('priority', 'medium')}")

            if tc.get("steps"):
                prompt_parts.append("Steps:")
                for step in tc["steps"]:
                    if isinstance(step, dict):
                        prompt_parts.append(
                            f"- {step.get('action', '')} -> {step.get('expected', '')}"
                        )
                    else:
                        prompt_parts.append(f"- {step}")

            if tc.get("test_data"):
                prompt_parts.append(f"Test data: {tc['test_data']}")

        return "\n".join(prompt_parts)

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.validate_input(input_data, ["test_cases"]):
            raise ValueError("input_data missing `test_cases`")

        test_cases = input_data["test_cases"]
        test_environment = input_data.get("test_environment") or {}
        test_case_list = test_cases.get("test_cases", [])

        has_ui_test = any(
            str(tc.get("test_type", "")).lower() == "ui" for tc in test_case_list
        )

        prompt = self.build_prompt(test_cases, test_environment)
        system_prompt = self.ui_test_prompt if has_ui_test else self.api_test_prompt

        response = self.call_llm(prompt, system_prompt)
        payload = self.parse_json_response(response)

        generated_scripts = self._normalize_scripts(payload, default_ui=has_ui_test)

        # Persist generated files without changing in-memory structure.
        self.save_scripts_to_files({"scripts": generated_scripts})

        result = {
            "scripts": generated_scripts,
            "metadata": {
                "agent": "CodeAgent",
                "model": self.model,
                "script_count": len(generated_scripts),
                "test_type": "ui" if has_ui_test else "api",
                "generated_at": self.get_timestamp(),
            },
        }

        self.log_processing(input_data, result)
        return result

    # ------------------------------------------------------------------
    # act() — interactive code generation
    # ------------------------------------------------------------------

    def act(
        self,
        conversation_messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Generator[Dict[str, Any], Optional[str], None]:
        """Interactive code generation with knowledge search and file reading."""
        tools_prompt = format_tools_prompt(self._tools)
        # IMPORTANT: combine (not replace) the strict JSON/dsl contract with the
        # orchestrator-provided instruction (page_map / env). Replacing it with
        # system_instruction alone made the model return prose + ```javascript
        # blocks instead of the required {"scripts":[...]} JSON envelope.
        hard_rule = (
            "\n\nHARD OUTPUT RULES (must follow):\n"
            "- Return ONLY a single JSON object of the form {\"scripts\": [...]}. "
            "No prose, no explanation, no markdown headings outside the JSON.\n"
            "- The `code` field MUST be valid Python using `from playwright.sync_api import sync_playwright`. "
            "NEVER emit JavaScript, Node.js, or `require('@playwright/test')`. "
            "NEVER write a single-line JS snippet like `page.click(...)`. "
            "Think: import → with sync_playwright() as p → launch → goto → act → assert.\n"
            "- For UI cases, also include the `dsl` object (given/when/then). "
            "The `then` assertions MUST verify the test case's stated goal — "
            "do NOT hallucinate URLs or text that don't belong to the page under test. "
            "For example, if the test navigates to /knowledge, assert url_contains '/knowledge', "
            "NOT '/dashboard'. If you don't know the exact expected text, "
            "use element_visible on a known selector from the page_map instead."
        )
        full_system = (
            self.ui_test_prompt
            + "\n\n"
            + (system_instruction or "")
            + "\n\n"
            + tools_prompt
            + hard_rule
        )

        yield from super().act(conversation_messages, full_system)

    def _try_extract_artifact(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract test scripts from the agent response."""
        try:
            data = self.parse_json_response(response)
            scripts = data.get("scripts", [])
            if scripts:
                normalized = self._normalize_scripts({"scripts": scripts}, default_ui=False)
                self.save_scripts_to_files({"scripts": normalized})
                return {"key": "test_scripts", "data": {"scripts": normalized}}
        except Exception:
            pass
        return None

    def _normalize_scripts(self, payload: Dict[str, Any], default_ui: bool) -> List[Dict[str, Any]]:
        scripts = payload.get("scripts", [])
        if not isinstance(scripts, list):
            scripts = [payload]

        normalized: List[Dict[str, Any]] = []
        for idx, script in enumerate(scripts, 1):
            if not isinstance(script, dict):
                continue

            script_id = str(script.get("id") or f"TC-{idx}")
            language = script.get("language") or "python"
            framework = script.get("framework") or ("playwright" if default_ui else "pytest")
            code = script.get("code") or self._default_code(default_ui, script_id)
            if isinstance(code, list):
                code = "\n".join(str(line) for line in code)
            code = self._fix_code_newlines(str(code))

            entry = {
                "id": script_id,
                "title": script.get("title", f"Auto script {script_id}"),
                "description": script.get("description", ""),
                "language": language,
                "framework": framework,
                "code": code,
                "dependencies": script.get("dependencies", ["pytest"]),
                "execution_command": script.get("execution_command", "pytest -q"),
                "expected_output": script.get("expected_output", "tests pass"),
            }
            # Preserve the Given-When-Then DSL for CDP execution (UI cases)
            if isinstance(script.get("dsl"), dict):
                entry["dsl"] = script["dsl"]
            normalized.append(entry)

        if not normalized:
            normalized.append(
                {
                    "id": "TC-001",
                    "title": "Fallback generated script",
                    "description": "Fallback script due to empty LLM response",
                    "language": "python",
                    "framework": "playwright" if default_ui else "pytest",
                    "code": self._default_code(default_ui, "TC-001"),
                    "dependencies": ["pytest"],
                    "execution_command": "pytest -q",
                    "expected_output": "tests pass",
                }
            )

        return normalized

    @staticmethod
    def _fix_code_newlines(code: str) -> str:
        """Fix LLM-generated code that has literal \\n instead of real newlines."""
        if not code or "\n" in code:
            return code
        if "\\n" in code:
            return code.replace("\\n", "\n")
        return code

    def _default_code(self, default_ui: bool, script_id: str) -> str:
        safe_name = script_id.replace("-", "_")
        if default_ui:
            return (
                "from playwright.sync_api import Page\n\n"
                f"def test_{safe_name}(page: Page):\n"
                "    page.goto('about:blank')\n"
                "    assert page.url is not None\n"
            )
        return (
            f"def test_{safe_name}():\n"
            "    assert True\n"
        )

    def save_scripts_to_files(self, scripts_data: Dict[str, Any], base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.join(Config.WORKSPACE, "scripts")

        os.makedirs(base_dir, exist_ok=True)

        saved_files: List[str] = []
        for script in scripts_data.get("scripts", []):
            try:
                script_id = str(script.get("id", "unknown")).replace("/", "_").replace("\\\\", "_")
                language = script.get("language", "python")
                ext = ".py" if language == "python" else ".js" if language == "javascript" else ".txt"

                filename = f"test_{script_id}{ext}"
                filepath = os.path.join(base_dir, filename)

                code_content = script.get("code", "")
                if isinstance(code_content, list):
                    code_content = "\n".join(str(line) for line in code_content)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(str(code_content))

                script["file_path"] = filepath
                script["filename"] = filename

                saved_files.append(filepath)
                logger.info(f"script saved: {filepath}")
            except Exception as e:
                logger.error(f"failed to save script {script.get('id', 'unknown')}: {e}")

        return saved_files

    def get_timestamp(self):
        return datetime.utcnow().isoformat()
