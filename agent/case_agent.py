"""
Test case design agent.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

from .tool_agent import ToolCapableAgent
from .tools import format_tools_prompt
from models import db, Requirement, TestCase, TestSuite
from service.knowledge_service import knowledge_service

logger = logging.getLogger(__name__)


class CaseAgent(ToolCapableAgent):
    """Generate or reuse test cases from structured requirements."""

    def __init__(self):
        super().__init__(model="gpt-4", temperature=0.1, agent_type="case_agent")
        self.system_prompt = self.custom_system_prompt or """你是专业的测试用例设计师。
必须使用中文输出测试用例内容，包括 title、description、preconditions、test_steps.action、test_steps.expected、test_data.expected_output 和 tags。
你的测试对象是需求中描述的业务系统/功能模块，不是需求文档本身。不要生成"测试文档解析"这类用例。
只返回合法 JSON，字段名保持英文，格式如下：
{
  "test_cases": [
    {
      "id": "TC-001",
      "title": "用例标题",
      "description": "用例描述",
      "test_type": "api/ui/performance/security",
      "priority": "high/medium/low",
      "preconditions": ["前置条件 1"],
      "test_steps": [
        {
          "step": 1,
          "action": "执行操作",
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
}"""

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.validate_input(input_data, ["structured_req"]):
            raise ValueError("Missing required field: structured_req")

        structured_req = input_data["structured_req"]
        requirement_id = input_data.get("requirement_id")

        reusable_suite = self.find_reusable_suite(structured_req)
        if reusable_suite and requirement_id:
            logger.info("Reusing existing test suite %s", reusable_suite.id)
            return self.reuse_test_suite(reusable_suite, requirement_id)

        knowledge_context = self.get_knowledge_context(structured_req, requirement_id)
        prompt = self.build_prompt(structured_req, knowledge_context.get("prompt_text"))
        response = self.call_llm(prompt, self.system_prompt)
        test_cases = self.parse_test_case_response(response)
        test_suite = self.create_test_suite(structured_req, test_cases)

        test_cases["metadata"] = {
            "agent": "CaseAgent",
            "model": self.model,
            "requirement_title": structured_req.get("title", "Unknown"),
            "test_case_count": len(test_cases.get("test_cases", [])),
            "generated_at": self.get_timestamp(),
            "test_suite_id": test_suite.id if test_suite else None,
            "knowledge_entry_count": len(knowledge_context.get("items", [])),
            "knowledge_entries": knowledge_context.get("items", []),
        }

        self.log_processing(input_data, test_cases)
        return test_cases

    # ------------------------------------------------------------------
    # act() — interactive test case design
    # ------------------------------------------------------------------

    def act(
        self,
        conversation_messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Generator[Dict[str, Any], Optional[str], None]:
        """Interactive test case design with knowledge search and reuse."""
        tools_prompt = format_tools_prompt(self._tools)
        full_system = self.system_prompt + "\n\n" + tools_prompt

        yield from super().act(conversation_messages, full_system)

    def _try_extract_artifact(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract test cases from the agent response."""
        try:
            data = self.parse_test_case_response(response)
            if "test_cases" in data:
                return {"key": "test_cases", "data": data}
        except Exception:
            pass
        return None

    def parse_test_case_response(self, response: str) -> Dict[str, Any]:
        import json
        import re

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            start = response.find('{')
            end = response.rfind('}')
            json_str = response[start:end + 1] if start != -1 and end != -1 and end > start else response

        parsed = json.loads(json_str)
        if "test_cases" in parsed:
            return parsed
        if "scripts" in parsed:
            raise ValueError("LLM returned scripts instead of test cases")
        return {"test_cases": [parsed]}

    def get_knowledge_context(self, structured_req: Dict[str, Any], requirement_id: Optional[int]) -> Dict[str, Any]:
        knowledge_base_ids: List[int] = []
        if requirement_id:
            requirement = db.session.get(Requirement, requirement_id)
            if requirement and requirement.knowledge_base_id:
                knowledge_base_ids.append(requirement.knowledge_base_id)

        return knowledge_service.build_case_context(
            structured_req,
            knowledge_base_ids=knowledge_base_ids or None,
            limit=3,
        )

    def find_reusable_suite(self, structured_req: Dict[str, Any]) -> Optional[TestSuite]:
        keywords = self.extract_keywords(structured_req)
        reusable_suites = TestSuite.query.filter_by(is_reusable=True).all()

        best_match = None
        best_match_count = 0

        for suite in reusable_suites:
            suite_tags = suite.tags or []
            suite_pattern = suite.requirement_pattern or ""
            match_count = 0

            for keyword in keywords:
                if keyword in suite_tags or keyword.lower() in suite_pattern.lower():
                    match_count += 1

            title = structured_req.get("title", "").lower()
            if title and title in suite_pattern.lower():
                match_count += 2

            if match_count > best_match_count and match_count >= 2:
                best_match_count = match_count
                best_match = suite

        return best_match

    def extract_keywords(self, structured_req: Dict[str, Any]) -> List[str]:
        keywords: List[str] = []

        title = structured_req.get("title", "")
        if title:
            keywords.extend([part.strip() for part in title.replace("/", " ").split() if len(part.strip()) > 1])

        for module in structured_req.get("business_modules", []):
            name = module.get("name", "")
            if name:
                keywords.append(name)

        for interface in structured_req.get("interfaces", []):
            endpoint = interface.get("endpoint", "")
            if endpoint:
                parts = endpoint.strip("/").split("/")
                keywords.extend([part for part in parts if len(part) > 1 and not part.startswith(":")])

        deduped: List[str] = []
        for keyword in keywords:
            if keyword and keyword not in deduped:
                deduped.append(keyword)
        return deduped

    def create_test_suite(self, structured_req: Dict[str, Any], test_cases: Dict[str, Any]) -> Optional[TestSuite]:
        try:
            keywords = self.extract_keywords(structured_req)
            requirement_pattern = structured_req.get("title", "")
            if structured_req.get("description"):
                requirement_pattern = f"{requirement_pattern} {structured_req.get('description', '')}".strip()

            suite = TestSuite(
                name=f"Suite - {structured_req.get('title', 'Untitled')[:50]}",
                description=f"Generated from requirement: {structured_req.get('title', '')}",
                tags=keywords,
                requirement_pattern=requirement_pattern[:500],
                is_reusable=True,
                usage_count=0,
            )
            db.session.add(suite)
            db.session.commit()
            return suite
        except Exception as exc:
            logger.error("Failed to create test suite: %s", exc)
            db.session.rollback()
            return None

    def reuse_test_suite(self, test_suite: TestSuite, requirement_id: int) -> Dict[str, Any]:
        try:
            test_suite.usage_count += 1
            db.session.commit()

            new_cases = []
            for case in test_suite.test_cases:
                cloned_case = TestCase(
                    requirement_id=requirement_id,
                    test_suite_id=test_suite.id,
                    title=case.title,
                    description=case.description,
                    test_type=case.test_type,
                    priority=case.priority,
                    steps=case.steps,
                    expected_results=case.expected_results,
                )
                db.session.add(cloned_case)
                new_cases.append(
                    {
                        "id": case.id,
                        "title": case.title,
                        "description": case.description,
                        "test_type": case.test_type,
                        "priority": case.priority,
                        "steps": case.steps,
                        "expected_results": case.expected_results,
                        "reused": True,
                        "original_case_id": case.id,
                    }
                )

            db.session.commit()
            return {
                "test_cases": new_cases,
                "metadata": {
                    "agent": "CaseAgent",
                    "model": self.model,
                    "test_case_count": len(new_cases),
                    "reused": True,
                    "test_suite_id": test_suite.id,
                    "test_suite_name": test_suite.name,
                    "usage_count": test_suite.usage_count,
                    "knowledge_entry_count": 0,
                    "knowledge_entries": [],
                },
            }
        except Exception as exc:
            logger.error("Failed to reuse test suite: %s", exc)
            db.session.rollback()
            raise

    def build_prompt(self, structured_req: Dict[str, Any], knowledge_prompt: Optional[str] = None) -> str:
        prompt_parts: List[str] = []
        prompt_parts.append(f"Requirement title: {structured_req.get('title', 'Unknown')}")
        prompt_parts.append(f"Requirement description: {structured_req.get('description', 'Unknown')}")

        business_modules = structured_req.get("business_modules", [])
        if business_modules:
            prompt_parts.append("\nBusiness modules:")
            for module in business_modules:
                prompt_parts.append(
                    f"  - {module.get('name')} ({module.get('priority')}): {module.get('description')}"
                )

        interfaces = structured_req.get("interfaces", [])
        if interfaces:
            prompt_parts.append("\nInterfaces:")
            for interface in interfaces:
                prompt_parts.append(
                    f"  - {interface.get('method')} {interface.get('endpoint')}: {interface.get('description')}"
                )

        ui_elements = structured_req.get("ui_elements", [])
        if ui_elements:
            prompt_parts.append("\nUI elements:")
            for element in ui_elements:
                prompt_parts.append(
                    f"  - {element.get('type')} {element.get('name')}: {element.get('description')}"
                )

        test_points = structured_req.get("test_points", [])
        if test_points:
            prompt_parts.append("\nTest points:")
            for point in test_points:
                prompt_parts.append(
                    f"  - {point.get('id')} ({point.get('type')}, {point.get('priority')}): {point.get('description')}"
                )

        test_scenarios = structured_req.get("test_scenarios", [])
        if test_scenarios:
            prompt_parts.append("\nTest scenarios:")
            for scenario in test_scenarios:
                prompt_parts.append(f"  - {scenario.get('name')}: {scenario.get('description')}")

        if knowledge_prompt:
            prompt_parts.append(f"\n{knowledge_prompt}")

        prompt_parts.append("\n请为上述需求设计详细测试用例。")
        prompt_parts.append("必须使用中文描述测试用例内容，字段名保持 JSON 约定。")
        prompt_parts.append("覆盖业务模块、接口、页面元素和重要风险场景。")
        prompt_parts.append("优先输出可落地的用例，包含正常路径和异常路径校验。")

        return "\n".join(prompt_parts)

    def get_timestamp(self) -> str:
        return datetime.utcnow().isoformat()
