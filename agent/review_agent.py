"""
LLM 驱动的代码审查 Agent — 支持多模型并行分析。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Generator, List, Optional

from agent.tool_agent import ToolCapableAgent
from agent.tools import format_tools_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 两套 system prompt：安全/逻辑 和 质量/性能
# ---------------------------------------------------------------------------

SECURITY_LOGIC_PROMPT = """你是一位资深安全审计专家。请审查以下 git diff 代码变更，聚焦以下方面：

1. **安全漏洞**：SQL 注入、XSS、命令注入、敏感信息泄露、权限绕过、不安全的反序列化
2. **逻辑错误**：边界条件错误、空指针/None 引用、资源泄漏、死锁风险、竞态条件
3. **数据完整性**：数据校验缺失、类型转换错误、事务边界问题

对每个发现的问题，输出 JSON 格式：
{
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "security|logic|data_integrity",
      "title": "简短标题（中文，不超过30字）",
      "description": "详细描述问题所在",
      "suggestion": "修复建议",
      "file_path": "涉及的文件路径（如果能从 diff 中识别）",
      "line_hint": "相关行号或代码片段"
    }
  ],
  "summary": "整体安全性评价（中文，不超过100字）"
}

如果没有发现问题，返回 {"findings": [], "summary": "未发现安全或逻辑问题"}。"""

QUALITY_PERF_PROMPT = """你是一位资深代码质量与性能优化专家。请审查以下 git diff 代码变更，聚焦以下方面：

1. **代码质量**：命名规范、函数复杂度、重复代码、错误处理、可读性
2. **性能问题**：N+1 查询、不必要的循环、内存浪费、阻塞调用、缓存缺失
3. **最佳实践**：设计模式使用、SOLID 原则、测试覆盖、文档完整性

对每个发现的问题，输出 JSON 格式：
{
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "quality|performance|best_practice",
      "title": "简短标题（中文，不超过30字）",
      "description": "详细描述问题所在",
      "suggestion": "修复建议",
      "file_path": "涉及的文件路径（如果能从 diff 中识别）",
      "line_hint": "相关行号或代码片段"
    }
  ],
  "summary": "整体质量评价（中文，不超过100字）"
}

如果没有发现问题，返回 {"findings": [], "summary": "未发现质量或性能问题"}。"""


class ReviewAgent(ToolCapableAgent):
    """LLM 代码审查 Agent — 支持工具调用的可配置审查。"""

    def __init__(self, review_type: str = "security_logic", **kwargs):
        kwargs.setdefault("agent_type", "review_agent")
        super().__init__(**kwargs)
        self.review_type = review_type
        self.system_prompt = self.custom_system_prompt or (
            SECURITY_LOGIC_PROMPT if review_type == "security_logic" else QUALITY_PERF_PROMPT
        )

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        commit_sha = input_data.get("commit_sha", "unknown")
        commit_msg = input_data.get("commit_msg", "")
        diff_text = input_data.get("diff_text", "")

        if not diff_text.strip():
            return {"findings": [], "summary": "无代码变更内容可供审查", "error": None}

        prompt = self._build_prompt(commit_sha, commit_msg, diff_text)
        try:
            response = self.call_llm(prompt, system_prompt=self.system_prompt)
            result = self.parse_json_response(response)
            logger.info(
                "ReviewAgent[%s] 审查完成，发现 %d 个问题",
                self.review_type,
                len(result.get("findings", [])),
            )
            result["error"] = None
            return result
        except Exception as exc:
            logger.error("ReviewAgent[%s] 审查失败: %s", self.review_type, exc)
            return {"findings": [], "summary": "", "error": str(exc)}

    # ------------------------------------------------------------------
    # act() — interactive code review
    # ------------------------------------------------------------------

    def act(
        self,
        conversation_messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Generator[Dict[str, Any], Optional[str], None]:
        """Interactive code review with file reading and knowledge search."""
        tools_prompt = format_tools_prompt(self._tools)
        full_system = (system_instruction or self.system_prompt) + "\n\n" + tools_prompt

        yield from super().act(conversation_messages, full_system)

    def _try_extract_artifact(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract review findings from the agent response."""
        try:
            data = self.parse_json_response(response)
            if "findings" in data or "summary" in data:
                return {"key": "review_findings", "data": data}
        except Exception:
            pass
        return None

    def _build_prompt(self, commit_sha: str, commit_msg: str, diff_text: str) -> str:
        max_diff_chars = 6000
        truncated = diff_text if len(diff_text) <= max_diff_chars else (
            diff_text[:max_diff_chars] + f"\n\n... (diff truncated, {len(diff_text) - max_diff_chars} more characters)"
        )
        return (
            f"Commit: {commit_sha}\n"
            f"Message: {commit_msg}\n\n"
            f"=== GIT DIFF ===\n{truncated}\n=== END DIFF ==="
        )


def merge_review_results(security: Dict, quality: Dict) -> List[Dict[str, Any]]:
    """合并两个 Agent 的审查结果为统一的 findings 列表。"""
    findings: List[Dict[str, Any]] = []
    for result in [security, quality]:
        for f in (result or {}).get("findings", []) or []:
            f["review_type"] = "security_logic" if result is security else "quality_perf"
            findings.append(f)
    return findings
