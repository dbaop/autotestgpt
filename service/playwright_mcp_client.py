"""
Playwright MCP client — talks to @playwright/mcp via stdio JSON-RPC.

Replaces the cdp-bridge HTTP client with the same npm-powered MCP server
that Claude Code's /browser-automation skill uses internally.  Much more
reliable than uvx cdp-bridge (no first-time download hang, no HTTP port
conflicts, Microsoft-maintained).

Usage:
    client = PlaywrightMCPClient()
    client.initialize()
    client.navigate("https://example.com")
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PlaywrightMCPClient:
    """Thin stdio client for @playwright/mcp.  Spawns the process and
    communicates via newline-delimited JSON-RPC."""

    # Tool names as exposed by @playwright/mcp
    TOOL_NAVIGATE = "browser_navigate"
    TOOL_SNAPSHOT = "browser_snapshot"       # accessibility tree
    TOOL_SCREENSHOT = "browser_take_screenshot"
    TOOL_CLICK = "browser_click"
    TOOL_FILL = "browser_type"              # note: "browser_type", not "browser_fill"
    TOOL_EVALUATE = "browser_evaluate"       # execute JS
    TOOL_TABS = "browser_tabs"              # list tabs

    def __init__(self, headless: bool = False):
        self._headless = headless
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._id = 0
        self._available = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _find_npx() -> str:
        """Locate npx on the system, falling back to known Windows paths."""
        import shutil
        # Try PATH first
        npx = shutil.which("npx")
        if npx:
            return npx
        # Common locations on Windows
        for base in [
            os.path.expandvars(r"%ProgramFiles%\nodejs"),
            os.path.expandvars(r"%ProgramFiles(x86)%\nodejs"),
            os.path.expandvars(r"%APPDATA%\npm"),
            os.path.expandvars(r"%LOCALAPPDATA%\npm"),
            r"D:\Program Files\nodejs",
        ]:
            candidate = os.path.join(base, "npx.cmd")
            if os.path.exists(candidate):
                return candidate
            candidate = os.path.join(base, "npx")
            if os.path.exists(candidate):
                return candidate
        return "npx"  # last resort

    def initialize(self) -> bool:
        """Start the npx subprocess and send MCP initialize. Returns True on success."""
        if self._available:
            return True

        try:
            npx = self._find_npx()
            args = [npx, "-y", "@playwright/mcp@latest"]
            if self._headless:
                args.append("--headless")

            # Ensure nodejs is in PATH and force UTF-8 for subprocess pipes
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                        "http_proxy", "https_proxy", "no_proxy"):
                env.pop(key, None)

            self._process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=(os.name == "nt"),
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # MCP handshake: initialize
            result = self._rpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "autotestgpt", "version": "1.0"},
            })
            if result and result.get("serverInfo"):
                # Send initialized notification
                self._send_notification("notifications/initialized", {})
                self._available = True
                logger.info(
                    "Playwright MCP connected: %s v%s",
                    result["serverInfo"].get("name", "?"),
                    result["serverInfo"].get("version", "?"),
                )
                return True
        except Exception as exc:
            logger.warning("Playwright MCP init failed: %s", exc)
            self._cleanup()

        return False

    @property
    def is_available(self) -> bool:
        return self._available and self._process is not None and self._process.poll() is None

    def _cleanup(self):
        if self._process:
            try:
                self._process.stdin.close()
            except Exception:
                pass
            try:
                self._process.stdout.close()
            except Exception:
                pass
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None
        self._available = False

    def disconnect(self):
        self._cleanup()

    # ------------------------------------------------------------------
    # Public API — same interface as CdpBridgeClient
    # ------------------------------------------------------------------

    def call(self, tool_name: str, arguments: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Call any MCP tool by name. Returns parsed result or None on failure."""
        if not self._available and not self.initialize():
            return None
        try:
            raw = self._rpc("tools/call", {
                "name": tool_name,
                "arguments": arguments or {},
            })
            if raw is None:
                return None
            return self._decode_tool_result(raw)
        except Exception as exc:
            logger.warning("Playwright MCP call %s failed: %s", tool_name, exc)
            return None

    def navigate(self, url: str) -> Dict[str, Any]:
        result = self.call(self.TOOL_NAVIGATE, {"url": url})
        if result:
            # @playwright/mcp returns the page info directly
            return {"ok": True, "url": url, "title": result.get("title", "")}
        return {"ok": False, "url": url, "error": "navigate failed"}

    def scan(self, text_only: bool = True) -> Dict[str, Any]:
        """Capture page content via snapshot (backward-compatible with CdpBridgeClient)."""
        return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        """Capture accessibility snapshot (like browser_snapshot)."""
        result = self.call(self.TOOL_SNAPSHOT, {})
        if result:
            # result is the accessibility tree as text
            text = result.get("text", "") or str(result)
            return {"ok": True, "content": text[:5000], "length": len(text)}
        return {"ok": False, "error": "snapshot failed"}

    def screenshot(self) -> Dict[str, Any]:
        result = self.call(self.TOOL_SCREENSHOT, {})
        if result:
            data_url = result.get("data") or result.get("result", "")
            return {"ok": True, "data_url": str(data_url)}
        return {"ok": False, "error": "screenshot failed"}

    def execute_js(self, code: str) -> Dict[str, Any]:
        # @playwright/mcp browser_evaluate uses "function" not "script"
        result = self.call(self.TOOL_EVALUATE, {"function": code})
        if result:
            js_result = result.get("result", "") or str(result)
            return {"ok": True, "result": str(js_result)}
        # Fallback: old parameter name
        result = self.call(self.TOOL_EVALUATE, {"script": code})
        if result:
            js_result = result.get("result", "") or str(result)
            return {"ok": True, "result": str(js_result)}
        return {"ok": False, "error": "execute_js failed"}

    def click(self, selector: str) -> Dict[str, Any]:
        # @playwright/mcp uses "element" not "selector"
        result = self.call(self.TOOL_CLICK, {"element": selector})
        if result:
            return {"ok": True, "clicked": selector}
        return {"ok": False, "error": "click failed", "selector": selector}

    def fill(self, selector: str, value: str) -> Dict[str, Any]:
        # @playwright/mcp uses "element" + "text", not "selector" + "value"
        result = self.call(self.TOOL_FILL, {"element": selector, "text": value})
        if result:
            return {"ok": True, "filled": selector, "value": value}
        return {"ok": False, "error": "fill failed", "selector": selector}

    def extract_content(self) -> Dict[str, Any]:
        """Extract page content via snapshot + JS title."""
        snap = self.snapshot()
        content = snap.get("content", "") if snap.get("ok") else ""
        js = self.execute_js("document.title")
        title = js.get("result", "") if js.get("ok") else ""
        return {"ok": True, "title": title, "content": content, "length": len(content)}

    # ------------------------------------------------------------------
    # JSON-RPC over stdio
    # ------------------------------------------------------------------

    def _rpc(self, method: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": method,
                "params": params or {},
            }
            line = json.dumps(payload, ensure_ascii=False) + "\n"

            try:
                self._process.stdin.write(line)
                self._process.stdin.flush()
            except Exception as exc:
                logger.warning("Playwright MCP write failed: %s", exc)
                self._available = False
                return None

            # Read response — it may be multiple lines (streaming)
            try:
                while True:
                    resp_line = self._process.stdout.readline()
                    if not resp_line:
                        break
                    resp_line = resp_line.strip()
                    if not resp_line:
                        continue
                    try:
                        data = json.loads(resp_line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("id") != self._id:
                        # Notification or result for a different request
                        continue

                    if "result" in data:
                        return data["result"]
                    if "error" in data:
                        logger.warning(
                            "Playwright MCP error: %s",
                            data["error"].get("message", str(data["error"]))[:200],
                        )
                        return None
            except Exception as exc:
                logger.warning("Playwright MCP read failed: %s", exc)
                self._available = False
                return None

        return None

    def _send_notification(self, method: str, params: Dict[str, Any] = None):
        """Send a JSON-RPC notification (no response expected)."""
        with self._lock:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
            line = json.dumps(payload, ensure_ascii=False) + "\n"
            try:
                self._process.stdin.write(line)
                self._process.stdin.flush()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Tool result decoding (mirrors CdpBridgeClient._decode_tool_result)
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_tool_result(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize MCP tool-call result.  @playwright/mcp returns
        ``structuredContent`` or ``content[].text`` blocks."""
        if not isinstance(raw, dict):
            return {"result": raw}

        # structuredContent path (MCP spec)
        sc = raw.get("structuredContent")
        if isinstance(sc, dict):
            return dict(sc)

        # content blocks
        for block in raw.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                # Heuristic: if it looks like JSON, parse it
                stripped = text.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    try:
                        return json.loads(stripped)
                    except json.JSONDecodeError:
                        pass
                return {"text": text[:5000]}

        # Fallback: return the raw dict
        return dict(raw)
