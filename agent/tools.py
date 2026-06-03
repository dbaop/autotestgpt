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


def tool_get_requirement_environment(requirement_id: int) -> Dict[str, Any]:
    """Read the saved test environment config for a requirement."""
    from models import Requirement
    from flask import has_app_context, current_app

    if has_app_context():
        req = Requirement.query.get(requirement_id)
    else:
        from main import app
        with app.app_context():
            req = Requirement.query.get(requirement_id)

    if not req:
        return {"error": f"Requirement {requirement_id} not found"}

    progress = req.execution_progress or {}
    structured = req.structured_data or {}
    env = {}
    if isinstance(structured, dict):
        env.update(structured.get("test_environment") or {})
    if isinstance(progress, dict):
        env.update(progress.get("test_environment") or {})

    return {
        "requirement_id": requirement_id,
        "test_url": env.get("test_url"),
        "login_state": env.get("login_state", "unknown"),
        "credential_ref": env.get("credential_ref"),
        "allow_explore": env.get("allow_explore", True),
        "last_probe_at": env.get("last_probe_at"),
        "probe_status": env.get("probe_status"),
    }


# ---------------------------------------------------------------------------
# CDP browser tools (backed by BrowserProbe service)
# ---------------------------------------------------------------------------

def _get_probe():
    from service.browser_probe_service import get_browser_probe
    return get_browser_probe()


def tool_browser_navigate(url: str) -> Dict[str, Any]:
    """Navigate the browser to *url* via CDP and return page title / final URL."""
    logger.info("Tool browser_navigate url=%r", url)
    return _get_probe().navigate(url)


def tool_browser_snapshot(max_elements: int = 200) -> Dict[str, Any]:
    """Capture interactive elements (buttons/inputs/links) from the current page.

    Returns tag, id, text, placeholder, aria_label, data_testid, CSS classes,
    and bounding rect for each visible element.  Use this BEFORE generating
    Playwright / Selenium selectors so every selector is based on real DOM.
    """
    logger.info("Tool browser_snapshot max_elements=%d", max_elements)
    return _get_probe().snapshot(max_elements=max_elements)


def tool_browser_screenshot() -> Dict[str, Any]:
    """Take a PNG screenshot of the current viewport (returns base64 data URL)."""
    logger.info("Tool browser_screenshot")
    return _get_probe().screenshot()


def tool_browser_click(selector: str) -> Dict[str, Any]:
    """Click the first visible element matching a CSS selector."""
    logger.info("Tool browser_click selector=%r", selector)
    return _get_probe().click(selector)


def tool_browser_fill(selector: str, value: str) -> Dict[str, Any]:
    """Type *value* into the input/textarea matching *selector*."""
    logger.info("Tool browser_fill selector=%r", selector)
    return _get_probe().fill(selector, value)


def tool_browser_get_network(limit: int = 50) -> Dict[str, Any]:
    """Return recently captured network requests (URL, type, duration, size)."""
    logger.info("Tool browser_get_network limit=%d", limit)
    return _get_probe().get_network_requests(limit=limit)


def tool_browser_exec_js(code: str) -> Dict[str, Any]:
    """Execute arbitrary JavaScript in the page and return the result."""
    logger.info("Tool browser_exec_js")
    return _get_probe().execute_js(code)


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
    "get_requirement_environment": {
        "function": tool_get_requirement_environment,
        "description": "Get the saved test environment configuration for the current requirement. "
                       "Returns test_url, login_state, credential_ref, and allow_explore. "
                       "Use this BEFORE asking the user for URLs or credentials — the info may already be saved.",
        "parameters": {
            "requirement_id": {
                "type": "integer",
                "description": "The requirement ID to query environment for",
            },
        },
    },
    # ── CDP browser tools ──
    "browser_navigate": {
        "function": tool_browser_navigate,
        "description": "Navigate the browser to a URL via CDP. Use this to open the target "
                       "application before exploring its DOM or taking screenshots.",
        "parameters": {
            "url": {"type": "string", "description": "Full URL to navigate to"},
        },
    },
    "browser_snapshot": {
        "function": tool_browser_snapshot,
        "description": "Capture all interactive elements (buttons, inputs, links, selects) "
                       "from the current page. Returns tag, id, text, placeholder, aria_label, "
                       "data_testid, CSS classes, and bounding rect. "
                       "CRITICAL: call this BEFORE generating Playwright selectors so every "
                       "selector is based on real DOM, not guesswork.",
        "parameters": {
            "max_elements": {
                "type": "integer",
                "description": "Maximum number of elements to return (default 200)",
                "default": 200,
            },
        },
    },
    "browser_screenshot": {
        "function": tool_browser_screenshot,
        "description": "Take a PNG screenshot of the current viewport. Returns a base64 "
                       "data URL. Use for visual verification or debugging.",
        "parameters": {},
    },
    "browser_click": {
        "function": tool_browser_click,
        "description": "Click an element on the page by CSS selector.",
        "parameters": {
            "selector": {"type": "string", "description": "CSS selector of the element to click"},
        },
    },
    "browser_fill": {
        "function": tool_browser_fill,
        "description": "Type text into an input/textarea identified by CSS selector.",
        "parameters": {
            "selector": {"type": "string", "description": "CSS selector of the input element"},
            "value": {"type": "string", "description": "Text to type into the input"},
        },
    },
    "browser_get_network": {
        "function": tool_browser_get_network,
        "description": "Get recently captured network requests from the page. Use to verify "
                       "API calls, check response statuses, and validate backend behavior.",
        "parameters": {
            "limit": {
                "type": "integer",
                "description": "Max requests to return (default 50)",
                "default": 50,
            },
        },
    },
    "browser_exec_js": {
        "function": tool_browser_exec_js,
        "description": "Execute arbitrary JavaScript in the page context and return the result. "
                       "Use for extracting dynamic data or testing frontend logic.",
        "parameters": {
            "code": {"type": "string", "description": "JavaScript code to execute"},
        },
    },
}

# Tool sets per agent type
AGENT_TOOLS: Dict[str, List[str]] = {
    "req_agent": ["search_knowledge_base", "ask_user", "get_requirement_environment"],
    "browser_agent": [
        "browser_navigate", "browser_snapshot", "browser_screenshot",
        "browser_click", "browser_fill", "browser_get_network", "browser_exec_js",
        "get_requirement_environment", "ask_user",
    ],
    "case_agent": ["search_knowledge_base", "find_reusable_suites", "ask_user", "get_requirement_environment"],
    "code_agent": [
        "search_knowledge_base", "ask_user", "read_workspace_file",
        "get_requirement_environment",
        "browser_snapshot", "browser_navigate", "browser_screenshot",
    ],
    "exec_agent": [
        "ask_user", "read_workspace_file", "get_requirement_environment",
        "browser_navigate", "browser_snapshot", "browser_screenshot",
        "browser_click", "browser_fill",
    ],
    "review_agent": ["search_knowledge_base", "ask_user", "read_workspace_file", "get_requirement_environment"],
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
