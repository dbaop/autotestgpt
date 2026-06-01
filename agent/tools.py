"""
Agent tool registry and implementations.

Each tool is a function that agents can call during their act() loop.
Tools return results that are fed back into the LLM conversation context.
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_search_knowledge_base(
    query: str,
    knowledge_base_ids: Optional[List[int]] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Search the knowledge base for relevant documentation, API specs, test patterns."""
    from service.knowledge_service import knowledge_service

    results = knowledge_service.search_entries(query, knowledge_base_ids=knowledge_base_ids, limit=limit)
    logger.info("Tool search_knowledge_base query=%r → %d results", query, len(results))
    return results


def tool_find_reusable_suites(keywords: List[str]) -> List[Dict[str, Any]]:
    """Find reusable test suites matching the given keywords."""
    from models import TestSuite

    suites = TestSuite.query.filter_by(is_reusable=True).all()
    matches: List[Dict[str, Any]] = []
    for suite in suites:
        suite_tags = suite.tags or []
        suite_pattern = suite.requirement_pattern or ""
        score = 0
        for kw in keywords:
            if kw in suite_tags or kw.lower() in suite_pattern.lower():
                score += 1
        if score >= 2:
            matches.append({
                "id": suite.id,
                "name": suite.name,
                "description": suite.description,
                "tags": suite_tags,
                "score": score,
                "case_count": len(suite.test_cases) if suite.test_cases else 0,
            })
    matches.sort(key=lambda m: -m["score"])
    logger.info("Tool find_reusable_suites → %d matches", len(matches))
    return matches


def tool_read_workspace_file(file_path: str) -> str:
    """Read a file from the workspace directory (for reviewing generated code)."""
    full_path = os.path.join(Config.WORKSPACE, file_path)
    real_workspace = os.path.realpath(Config.WORKSPACE)
    real_path = os.path.realpath(full_path)
    if not real_path.startswith(real_workspace + os.sep) and real_path != real_workspace:
        raise ValueError(f"File outside workspace: {file_path}")
    if not os.path.exists(real_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(real_path, "r", encoding="utf-8") as f:
        content = f.read()
    logger.info("Tool read_workspace_file %r → %d chars", file_path, len(content))
    return content


# ---------------------------------------------------------------------------
# Tool definitions (for LLM function-calling prompts)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "search_knowledge_base": {
        "function": tool_search_knowledge_base,
        "description": "Search the knowledge base for relevant documentation, API specifications, "
                       "historical test cases, and domain knowledge. Use this when you need to "
                       "understand the system under test or find reference material.",
        "parameters": {
            "query": {"type": "string", "description": "Search query string"},
            "knowledge_base_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Optional list of knowledge base IDs to search within",
            },
            "limit": {"type": "integer", "description": "Maximum number of results to return", "default": 5},
        },
    },
    "ask_user": {
        "function": None,  # Special: pauses the agent loop, handled by orchestrator
        "description": "Ask the user a clarifying question and wait for their response. "
                       "Use this when you are uncertain about requirements, missing critical "
                       "information (URLs, credentials, system behavior), or need the user "
                       "to confirm an important decision.",
        "parameters": {
            "question": {"type": "string", "description": "The question to ask the user"},
            "context": {
                "type": "string",
                "description": "Why this question is important (helps the user understand what you need)",
            },
        },
    },
    "find_reusable_suites": {
        "function": tool_find_reusable_suites,
        "description": "Find reusable test suites that match given keywords. "
                       "Returns existing test suites that can be reused instead of generating new ones.",
        "parameters": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords to search for (e.g., ['login', 'authentication'])",
            },
        },
    },
    "read_workspace_file": {
        "function": tool_read_workspace_file,
        "description": "Read a file from the workspace directory. Use this to review generated "
                       "test scripts or other artifacts.",
        "parameters": {
            "file_path": {
                "type": "string",
                "description": "Relative path within the workspace directory",
            },
        },
    },
}

# Tool sets per agent type
AGENT_TOOLS: Dict[str, List[str]] = {
    "req_agent": ["search_knowledge_base", "ask_user"],
    "case_agent": ["search_knowledge_base", "find_reusable_suites", "ask_user"],
    "code_agent": ["search_knowledge_base", "ask_user", "read_workspace_file"],
    "exec_agent": ["ask_user", "read_workspace_file"],
    "review_agent": ["search_knowledge_base", "ask_user", "read_workspace_file"],
}


def get_tools_for_agent(agent_type: str) -> Dict[str, Dict[str, Any]]:
    """Return the tool definitions available to a specific agent type."""
    tool_names = AGENT_TOOLS.get(agent_type, [])
    return {name: TOOL_DEFINITIONS[name] for name in tool_names if name in TOOL_DEFINITIONS}


def format_tools_prompt(tools: Dict[str, Dict[str, Any]]) -> str:
    """Format tool definitions into a prompt section for the LLM."""
    if not tools:
        return ""

    lines = ["## Available Tools", ""]
    for name, defn in tools.items():
        params_desc = ", ".join(
            f"{k} ({v.get('type', 'string')})" for k, v in defn.get("parameters", {}).items()
        )
        lines.append(f"- **{name}**: {defn['description']}")
        if params_desc:
            lines.append(f"  Parameters: {params_desc}")
        lines.append("")

    lines.append(
        "To use a tool, output exactly:\n"
        '```json\n{"tool": "<tool_name>", "arguments": {...}}\n```\n'
        "After the tool result is returned, continue with your response.\n"
        "Use ask_user when you genuinely cannot proceed without the user's input."
    )
    return "\n".join(lines)


def execute_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a tool by name with the given arguments.

    Returns the tool result, or a sentinel dict for ask_user.
    """
    if name == "ask_user":
        return {
            "__tool_type__": "ask_user",
            "question": arguments.get("question", ""),
            "context": arguments.get("context", ""),
        }

    if name not in TOOL_DEFINITIONS:
        raise ValueError(f"Unknown tool: {name}")

    func = TOOL_DEFINITIONS[name]["function"]
    if func is None:
        raise ValueError(f"Tool {name} has no executable function")

    return func(**arguments)
