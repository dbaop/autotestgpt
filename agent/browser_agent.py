"""
Browser agent — explores the target application via CDP and produces a page map.

The page map captures real DOM structure (selectors, interactive elements,
navigation flows) so downstream agents (CaseAgent, CodeAgent) can generate
accurate test code instead of guessing selectors.
"""

import json
import logging
from typing import Any, Dict, Generator, List, Optional

from .tool_agent import ToolCapableAgent
from .tools import format_tools_prompt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a browser automation explorer. Your job is to open the target
web application, understand its structure, and produce a detailed "page map" that
describes every interactive element with real CSS selectors.

## Workflow (MUST follow this order)

1. Use **get_requirement_environment** to get the saved test_url.
2. Use **browser_navigate** to open that URL.
3. Use **browser_snapshot** to capture all interactive elements (buttons, inputs, links, etc.).
4. If the page has a login form, describe its fields and the login flow.
5. Click through 1-2 key navigation paths (e.g. main menu items) and snapshot each resulting page.
6. Use **browser_screenshot** if a visual check would help.
7. Produce a JSON **page_map** artifact with this structure:

```json
{
  "base_url": "https://...",
  "pages": [
    {
      "url": "...",
      "title": "...",
      "route": "/login",
      "elements": [
        {
          "tag": "input",
          "selector": "[data-testid='username']",
          "fallback_selectors": ["#username", "input[name='email']"],
          "type": "text",
          "label": "Username",
          "placeholder": "Enter username",
          "purpose": "login_username"
        }
      ],
      "actions": ["fill username", "fill password", "click login button"],
      "navigation_from": []
    }
  ],
  "flows": [
    {
      "name": "login",
      "steps": ["navigate /login", "fill username", "fill password", "click submit", "expect redirect /dashboard"]
    }
  ]
}
```

## Selector priority (from most to least reliable)
1. data-testid
2. id
3. aria-label
4. name attribute
5. placeholder text
6. unique CSS class combinations
7. text content (for buttons/links)

## Rules
- NEVER guess a selector — only report selectors you actually saw in the DOM snapshot.
- If a page requires authentication and you can't proceed, describe what you see and note the blocker.
- If the site redirects to a login page, document the login page elements.
- After producing the page_map, also produce a plain-language summary of what you found.
"""


class BrowserAgent(ToolCapableAgent):
    """Explores the target app via CDP and produces a page_map artifact.

    The page_map is consumed by CaseAgent (to understand available UI elements)
    and CodeAgent (to generate accurate Playwright selectors).
    """

    def __init__(self):
        super().__init__(model="deepseek/deepseek-chat", temperature=0.1, agent_type="browser_agent")
        self.system_prompt = self.custom_system_prompt or SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # act()
    # ------------------------------------------------------------------

    def act(
        self,
        conversation_messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Generator[Dict[str, Any], Optional[str], None]:
        tools_prompt = format_tools_prompt(self._tools)
        full_system = self.system_prompt + "\n\n" + tools_prompt

        if system_instruction:
            full_system = system_instruction + "\n\n" + full_system

        # Prefer the CDP bridge (user's logged-in Chrome) before exploration
        # starts, so a stale Playwright fallback from a startup-time race doesn't
        # shadow a now-healthy bridge. Done here (pre-navigation) so no page
        # state is lost; best-effort.
        try:
            from service.browser_probe_service import get_browser_probe

            get_browser_probe().prefer_mcp()
        except Exception:
            pass

        yield from super().act(conversation_messages, full_system)

    # ------------------------------------------------------------------
    # Artifact extraction
    # ------------------------------------------------------------------

    def _try_extract_artifact(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract a page_map artifact from the agent's final response."""
        try:
            data = self.parse_json_response(response)
            if isinstance(data, dict) and "pages" in data:
                page_map = self._normalize_page_map(data)
                return {"key": "page_map", "data": page_map}
        except Exception:
            pass

        # Also try extracting from embedded JSON
        import re
        fenced = re.search(r'```(?:json)?\s*(\{.*?"pages"\s*:.*?\})\s*```', response, re.DOTALL)
        if fenced:
            try:
                data = json.loads(fenced.group(1))
                if "pages" in data:
                    page_map = self._normalize_page_map(data)
                    return {"key": "page_map", "data": page_map}
            except Exception:
                pass

        return None

    def _normalize_page_map(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure the page_map has the expected structure."""
        pages = data.get("pages", [])
        for page in pages:
            page.setdefault("url", "")
            page.setdefault("title", "")
            page.setdefault("route", "")
            page.setdefault("elements", [])
            page.setdefault("actions", [])
            page.setdefault("navigation_from", [])
            for el in page.get("elements", []):
                el.setdefault("tag", "")
                el.setdefault("selector", "")
                el.setdefault("fallback_selectors", [])
                el.setdefault("purpose", "")
        data.setdefault("flows", [])
        data.setdefault("base_url", "")
        return data

    # ------------------------------------------------------------------
    # process() — backward compat
    # ------------------------------------------------------------------

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Backward-compatible synchronous entry point."""
        test_url = input_data.get("test_url", "")
        requirement_id = input_data.get("requirement_id")

        if not test_url:
            return {"error": "test_url is required for BrowserAgent", "page_map": None}

        conversation = [
            {"role": "user", "content": f"Explore {test_url} and produce a complete page map."}
        ]
        instruction = f"Requirement ID: {requirement_id or 'N/A'}. Explore the target app thoroughly."

        final_message = ""
        page_map = None
        for event in self.act(conversation, instruction):
            if event.get("type") == "message" and event.get("complete"):
                final_message = event["content"]
            elif event.get("type") == "artifact" and event["key"] == "page_map":
                page_map = event["data"]

        if not page_map and final_message:
            extracted = self._try_extract_artifact(final_message)
            if extracted:
                page_map = extracted["data"]

        return {
            "message": final_message,
            "page_map": page_map,
        }
