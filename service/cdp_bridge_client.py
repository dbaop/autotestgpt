"""
CDP Bridge MCP client — talks to the cdp-bridge MCP server via HTTP.

Usage:
    client = CdpBridgeClient("http://localhost:18700")
    client.initialize()
    tabs = client.call("browser_get_tabs", {})
    client.navigate("https://example.com")
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CdpBridgeClient:
    """Thin HTTP client for the cdp-bridge MCP server (streamable-http transport)."""

    def __init__(self, base_url: str = "http://localhost:18700"):
        self._base_url = base_url.rstrip("/")
        self._session_id: Optional[str] = None
        self._req_id = 0
        self._available = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """Send MCP initialize and store the session ID. Returns True on success."""
        try:
            result = self._post(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "autotestgpt", "version": "1.0"},
                },
                init=True,
            )
            if result and result.get("serverInfo"):
                self._available = True
                logger.info("CDP Bridge connected: %s v%s",
                           result["serverInfo"].get("name", "?"),
                           result["serverInfo"].get("version", "?"))
                return True
        except Exception as exc:
            logger.warning("CDP Bridge init failed: %s", exc)
        return False

    @property
    def is_available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    # Public API — mirrors browser_probe_service methods
    # ------------------------------------------------------------------

    def call(self, tool_name: str, arguments: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Call any MCP tool by name. Returns the parsed result or None on failure."""
        if not self._available and not self.initialize():
            return None
        try:
            raw = self._post("tools/call", {
                "name": tool_name,
                "arguments": arguments or {},
            })
            if raw is None:
                return None
            parsed = self._decode_tool_result(raw)
            if parsed and parsed.get("_mcp_is_error"):
                logger.warning("CDP Bridge tool %s returned error: %s", tool_name, self._error_message(parsed))
            return parsed
        except Exception as exc:
            logger.warning("CDP Bridge call %s failed: %s", tool_name, exc)
            return None

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate the active tab to *url*."""
        result = self.call("browser_navigate", {"url": url})
        if result:
            if result.get("_mcp_is_error"):
                return {"ok": False, "url": url, "error": self._error_message(result)}
            status = str(result.get("status", "")).lower()
            if result.get("ok") is False or any(token in status for token in ("error", "fail")):
                return {"ok": False, "url": url, "error": self._error_message(result)}
            if "success" in status or "ok" in status or not status:
                return {"ok": True, "url": url, "msg": result.get("msg", "")}
            return {"ok": False, "url": url, "error": self._error_message(result, f"unexpected navigate status: {status}")}
        return {"ok": False, "error": "navigate failed"}

    def scan(self, text_only: bool = True) -> Dict[str, Any]:
        """Get page text/HTML content."""
        result = self.call("browser_scan", {"text_only": text_only})
        if result:
            if result.get("_mcp_is_error"):
                return {"ok": False, "error": self._error_message(result)}
            text = result.get("content", "") or result.get("text", "") or result.get("result", "") or str(result)
            return {"ok": True, "content": text, "length": len(text)}
        return {"ok": False, "error": "scan failed"}

    def screenshot(self) -> Dict[str, Any]:
        """Take a screenshot of the active tab."""
        result = self.call("browser_screenshot", {})
        if result:
            if result.get("_mcp_is_error"):
                return {"ok": False, "error": self._error_message(result)}
            return {"ok": True, "data_url": result.get("result") or result.get("text") or str(result)}
        return {"ok": False, "error": "screenshot failed"}

    def execute_js(self, code: str) -> Dict[str, Any]:
        """Execute JavaScript in the page."""
        result = self.call("browser_execute_js", {"script": code, "no_monitor": True})
        if result:
            if result.get("_mcp_is_error"):
                return {"ok": False, "error": self._error_message(result)}
            js_return = result.get("js_return", "") or result.get("result", "")
            return {"ok": True, "result": str(js_return)}
        return {"ok": False, "error": "execute_js failed"}

    def get_tabs(self) -> Dict[str, Any]:
        """List all open browser tabs."""
        result = self.call("browser_get_tabs", {})
        if result:
            if result.get("_mcp_is_error"):
                return {"ok": False, "error": self._error_message(result)}
            tabs = result.get("tabs", [])
            return {"ok": True, "tabs": tabs}
        return {"ok": False, "error": "get_tabs failed"}

    @staticmethod
    def _decode_tool_result(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize MCP tool output.

        cdp-bridge exposes most tool outputs as JSON strings either in
        ``content[].text`` or ``structuredContent.result``. Older code only
        looked at content blocks, which made some valid responses appear empty.
        """
        if not isinstance(raw, dict):
            return {"result": raw}

        is_error = bool(raw.get("isError"))
        candidates: list[Any] = []

        structured = raw.get("structuredContent")
        if isinstance(structured, dict):
            if "result" in structured:
                candidates.append(structured.get("result"))
            else:
                candidates.append(structured)

        for block in raw.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                candidates.append(block.get("text", ""))

        if "result" in raw:
            candidates.append(raw.get("result"))

        for candidate in candidates:
            parsed = CdpBridgeClient._coerce_tool_candidate(candidate)
            if parsed is not None:
                if is_error:
                    parsed["_mcp_is_error"] = True
                return parsed

        parsed = dict(raw)
        if is_error:
            parsed["_mcp_is_error"] = True
        return parsed

    @staticmethod
    def _coerce_tool_candidate(candidate: Any) -> Optional[Dict[str, Any]]:
        if candidate is None:
            return None
        if isinstance(candidate, dict):
            return dict(candidate)
        if isinstance(candidate, str):
            text = candidate.strip()
            if not text:
                return {"text": ""}
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
                return {"result": parsed}
            except json.JSONDecodeError:
                return {"text": candidate, "result": candidate}
        return {"result": candidate}

    @staticmethod
    def _error_message(result: Dict[str, Any], fallback: str = "CDP Bridge tool failed") -> str:
        for key in ("error", "message", "msg", "text", "result"):
            value = result.get(key)
            if value:
                return str(value)
        return fallback

    def extract_content(self) -> Dict[str, Any]:
        """Extract visible text content from the current page (via scan)."""
        scan_result = self.scan(text_only=True)
        if scan_result.get("ok"):
            content = scan_result.get("content", "")
            js = self.execute_js("document.title")
            title = js.get("result", "") if js.get("ok") else ""
            return {"ok": True, "title": title, "content": content, "length": len(content)}
        return scan_result

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    def _post(self, method: str, params: Dict[str, Any] = None,
              init: bool = False) -> Optional[Dict[str, Any]]:
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params or {},
        }
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if not init and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        req = urllib.request.Request(
            f"{self._base_url}/mcp",
            data=data,
            headers=headers,
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if init:
                    self._session_id = resp.headers.get("Mcp-Session-Id", "")
                body = resp.read().decode("utf-8")
                return self._parse_sse(body)
        except urllib.error.HTTPError as exc:
            logger.error("CDP Bridge HTTP %d: %s", exc.code, exc.read().decode("utf-8", errors="replace")[:200])
            return None
        except Exception as exc:
            logger.error("CDP Bridge request failed: %s", exc)
            return None

    @staticmethod
    def _parse_sse(body: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from an SSE event: message response."""
        for line in body.split("\n"):
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if "result" in data:
                        return data["result"]
                    if "error" in data:
                        logger.warning("CDP Bridge error: %s", data["error"])
                        return None
                except json.JSONDecodeError:
                    pass
        # Try parsing whole body as JSON (non-SSE response)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            pass
        return None
