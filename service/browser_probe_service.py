"""
Browser probe service — connects to Chrome via CDP Bridge MCP, direct CDP, or
launches standalone Chromium.

Priority:
  1. CDP Bridge MCP server (user's Chrome via extension — has DingTalk auth)
  2. Chrome CDP directly (--remote-debugging-port)
  3. Playwright standalone Chromium (last resort)

All methods are synchronous so they can be called directly from agent tool functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CDP_ENDPOINT = "http://localhost:9222"
_CDP_MCP_URL = "http://localhost:18700"
_PAGE_STABILIZE_MS = 1500  # wait for JS frameworks to render
_USER_DATA_DIR = Path(__file__).resolve().parents[1] / "workspace" / "browser_profile"

# User's actual Chrome profile — used for DingTalk/Feishu auth cookies
def _find_chrome_profile() -> str | None:
    import os
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        default_profile = Path(local_app_data) / "Google" / "Chrome" / "User Data"
        if default_profile.exists():
            return str(default_profile)
    return None


class BrowserProbe:
    """Lightweight browser controller with multi-backend support."""

    def __init__(self, cdp_endpoint: str = _CDP_ENDPOINT, cdp_mcp_url: str = _CDP_MCP_URL):
        self._cdp_endpoint = cdp_endpoint
        self._cdp_mcp_url = cdp_mcp_url
        self._playwright = None
        self._browser = None
        self._page = None
        self._mcp_client = None  # CdpBridgeClient instance
        self._mode: str = ""  # "mcp", "cdp", or "standalone"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to a browser backend. Tries MCP → CDP → standalone."""
        # ——— Strategy 1: CDP Bridge MCP (user's Chrome via extension) ———
        if self._try_mcp_connect():
            return True

        # ——— Strategy 2: connect to Chrome directly via CDP ———
        if self._try_cdp_connect():
            return True

        # ——— Strategy 3: launch standalone Chromium ———
        return self._try_standalone_launch()

    def prefer_mcp(self) -> bool:
        """Ensure we're on the CDP Bridge MCP backend if it's reachable.

        The backend is otherwise chosen once and cached on the module-level
        singleton. If the very first browser op happened during the startup
        window — before ``uvx cdp-bridge`` finished booting / the extension
        paired — ``connect()`` fell back to a Playwright backend (standalone
        Chromium or direct CDP) and that choice stuck for the whole process,
        even after the bridge became healthy. That's why the logs "keep using
        Playwright" although the CDP bridge is up.

        Call this at safe points (no live page state to lose) to let a healthy
        bridge reclaim the session. It only performs an HTTP initialize — it
        never launches a browser — so it is cheap when already on MCP (short
        circuit) and a no-op when the bridge is down.

        Returns True if we end up on the MCP backend.
        """
        if self._mode == "mcp" and self.is_connected:
            return True

        # Hold on to any Playwright fallback we may currently own so we can tear
        # it down only after the bridge connection is confirmed.
        stale_browser = self._browser
        stale_playwright = self._playwright

        if self._try_mcp_connect():  # sets _mode="mcp" and _mcp_client
            if stale_browser is not None or stale_playwright is not None:
                try:
                    if stale_browser:
                        stale_browser.close()
                except Exception:
                    pass
                try:
                    if stale_playwright:
                        stale_playwright.stop()
                except Exception:
                    pass
                self._page = None
                self._browser = None
                self._playwright = None
            logger.info("Upgraded browser backend to CDP Bridge MCP")
            return True

        return False


    def _try_mcp_connect(self) -> bool:
        try:
            from service.cdp_bridge_client import CdpBridgeClient
            self._mcp_client = CdpBridgeClient(self._cdp_mcp_url)
            if self._mcp_client.initialize():
                self._mode = "mcp"
                logger.info("Connected via CDP Bridge MCP at %s", self._cdp_mcp_url)
                return True
        except Exception as exc:
            logger.info("CDP Bridge MCP not available (%s), trying next backend...", exc)
        self._mcp_client = None
        return False

    def _try_cdp_connect(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(self._cdp_endpoint, timeout=5000)
            pages = self._browser.contexts[0].pages if self._browser.contexts else []
            self._page = pages[0] if pages else self._browser.contexts[0].new_page()
            self._mode = "cdp"
            logger.info("Connected to Chrome via CDP at %s", self._cdp_endpoint)
            return True
        except Exception as exc:
            logger.info("CDP connect failed (%s), falling back to standalone Chromium...", exc)
            self._disconnect_current()
            return False

    def _try_standalone_launch(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
            if self._playwright is None:
                self._playwright = sync_playwright().start()

            # Try user's real Chrome profile first (for DingTalk cookies)
            user_data_dir = None
            chrome_profile = _find_chrome_profile()
            if chrome_profile:
                try:
                    context = self._playwright.chromium.launch_persistent_context(
                        chrome_profile,
                        headless=False,
                        args=["--no-sandbox", "--disable-setuid-sandbox"],
                        viewport={"width": 1440, "height": 900},
                    )
                    user_data_dir = chrome_profile
                    logger.info("Using user Chrome profile: %s", user_data_dir)
                except Exception as exc:
                    logger.info("User Chrome profile locked (Chrome is running): %s. Falling back...", exc)

            # Fallback: workspace profile
            if user_data_dir is None:
                _USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
                user_data_dir = str(_USER_DATA_DIR)
                context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                    viewport={"width": 1440, "height": 900},
                )
                logger.info("Using workspace profile: %s", user_data_dir)

            self._browser = context
            pages = context.pages
            self._page = pages[0] if pages else context.new_page()
            self._mode = "standalone"
            logger.info("Launched Chromium (profile: %s)", user_data_dir)
            return True
        except Exception as exc:
            logger.error("Failed to launch Chromium: %s", exc)
            self._disconnect_current()
            return False

    def _disconnect_current(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._playwright = None
        self._mode = ""

    def disconnect(self):
        self._disconnect_current()

    @property
    def is_connected(self) -> bool:
        if self._mode == "mcp":
            return self._mcp_client is not None and self._mcp_client.is_available
        return self._page is not None and self._browser is not None

    @property
    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------
    # High-level operations (used by agent tools)
    # ------------------------------------------------------------------

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to *url* and return page metadata after stabilisation."""
        if self._mode == "mcp" and self._mcp_client:
            result = self._mcp_client.navigate(url)
            if result.get("ok"):
                import time
                time.sleep(1.5)  # stabilise
                # Get title
                js = self._mcp_client.execute_js("document.title")
                result["title"] = js.get("result", "") if js.get("ok") else ""
            return result

        if not self.is_connected and not self.connect():
            return {"ok": False, "error": "Could not start browser. Install Chromium: playwright install chromium"}

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(_PAGE_STABILIZE_MS)
            return {
                "ok": True,
                "url": self._page.url,
                "title": self._page.title(),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "url": url}

    def snapshot(self, max_elements: int = 200) -> Dict[str, Any]:
        """Capture a lightweight DOM / accessibility snapshot."""
        if self._mode == "mcp" and self._mcp_client:
            scan = self._mcp_client.scan(text_only=False)
            if scan.get("ok"):
                content = scan.get("content", "")
                return {
                    "ok": True,
                    "url": "",
                    "title": "",
                    "elements": [{"tag": "page", "text": content[:5000]}],
                    "count": 1,
                }
            return scan

        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected. Call navigate first."}

        try:
            elements = self._page.evaluate("""(max) => {
                const selectors = 'button, a, input, select, textarea, [role="button"], [role="link"], [role="textbox"], [role="combobox"], [onclick], form, nav, [data-testid], [id]';
                const nodes = document.querySelectorAll(selectors);
                const result = [];
                for (let i = 0; i < Math.min(nodes.length, max); i++) {
                    const el = nodes[i];
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) continue;
                    result.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        name: el.getAttribute('name') || null,
                        type: el.getAttribute('type') || null,
                        placeholder: el.getAttribute('placeholder') || null,
                        text: (el.textContent || '').trim().slice(0, 200),
                        aria_label: el.getAttribute('aria-label') || null,
                        role: el.getAttribute('role') || null,
                        data_testid: el.getAttribute('data-testid') || null,
                        classList: el.className && typeof el.className === 'string' ? el.className.split(' ').filter(Boolean).slice(0,5) : [],
                        href: el.tagName === 'A' ? el.getAttribute('href') : null,
                        visible: rect.width > 0 && rect.height > 0,
                        rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}
                    });
                }
                return result;
            }""", max_elements)

            return {
                "ok": True,
                "url": self._page.url,
                "title": self._page.title(),
                "elements": elements,
                "count": len(elements),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def screenshot(self) -> Dict[str, Any]:
        """Take a full-page screenshot, return as base64 PNG data URL."""
        if self._mode == "mcp" and self._mcp_client:
            return self._mcp_client.screenshot()

        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected."}

        try:
            import base64
            raw = self._page.screenshot(full_page=False, type="png")
            b64 = base64.b64encode(raw).decode()
            return {
                "ok": True,
                "format": "png",
                "data_url": f"data:image/png;base64,{b64}",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def click(self, selector: str) -> Dict[str, Any]:
        """Click the first element matching a CSS selector."""
        if self._mode == "mcp" and self._mcp_client:
            return self._mcp_client.execute_js(
                f"document.querySelector('{selector}')?.click(); 'clicked'"
            )

        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected."}

        try:
            self._page.click(selector, timeout=5000)
            self._page.wait_for_timeout(800)
            return {"ok": True, "clicked": selector, "url": self._page.url}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "selector": selector}

    def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """Type *value* into the first input matching *selector*."""
        if self._mode == "mcp" and self._mcp_client:
            escaped = value.replace("\\", "\\\\").replace("'", "\\'")
            return self._mcp_client.execute_js(
                f"var el=document.querySelector('{selector}');"
                f"if(el){{el.focus();el.value='{escaped}';"
                f"el.dispatchEvent(new Event('input',{{bubbles:true}}));'ok'}}else'not found'"
            )

        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected."}

        try:
            self._page.fill(selector, value, timeout=5000)
            return {"ok": True, "filled": selector, "value": value}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "selector": selector}

    def get_network_requests(self, limit: int = 50) -> Dict[str, Any]:
        """Return recently captured network requests (URL + status)."""
        if self._mode == "mcp" and self._mcp_client:
            js = self._mcp_client.execute_js(
                f"JSON.stringify(performance.getEntriesByType('resource').slice(-{limit}).map(e=>({{name:e.name,type:e.initiatorType,duration:Math.round(e.duration),size:e.transferSize||0}})))"
            )
            if js.get("ok"):
                import json
                try:
                    return {"ok": True, "requests": json.loads(js["result"]), "count": 0}
                except Exception:
                    pass
            return js

        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected."}

        try:
            requests = self._page.evaluate("""(max) => {
                const entries = performance.getEntriesByType('resource');
                return entries.slice(-max).map(e => ({
                    name: e.name,
                    type: e.initiatorType,
                    duration: Math.round(e.duration),
                    size: e.transferSize || 0
                }));
            }""", limit)
            return {"ok": True, "requests": requests, "count": len(requests)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def execute_js(self, code: str) -> Dict[str, Any]:
        """Execute arbitrary JavaScript in the page context."""
        if self._mode == "mcp" and self._mcp_client:
            return self._mcp_client.execute_js(code)

        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected."}

        try:
            result = self._page.evaluate(code)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def extract_content(self, max_chars: int = 50000) -> Dict[str, Any]:
        """Extract the main text content from the current page as markdown."""
        if self._mode == "mcp" and self._mcp_client:
            return self._mcp_client.extract_content()

        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected."}

        try:
            content = self._page.evaluate("""(maxChars) => {
                const platformSelectors = [
                    '[class*="doc-content"]', '[class*="document-content"]',
                    '[class*="ak-content"]', '[class*="editor-content"]',
                    '.dingtalk-doc-content', '[data-testid="doc-body"]',
                    '[class*="docx-content"]', '[class*="lark-doc"]',
                    '.block-content', '[data-zone-id="page-content"]',
                    '.yuque-doc-content', '[class*="lake-content"]', '.ne-viewer-body',
                    '.notion-page-content', '[class*="notion-page"]',
                    '.kix-page-content', '#docs-editor',
                    'article', 'main', '[role="main"]', '.markdown-body',
                    '.prose', '#content', '.post-content', '.article-content',
                ];

                let container = null;
                for (const sel of platformSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 100) { container = el; break; }
                }
                if (!container || container.innerText.trim().length < 50) {
                    container = document.body;
                }

                // innerText strips script/style/hidden elements automatically
                const raw = container.innerText;
                const text = raw.length > maxChars ? raw.slice(0, maxChars) + '...(truncated)' : raw;

                return {
                    title: document.title,
                    url: window.location.href,
                    content: text,
                    length: text.length,
                };
            }""", max_chars)

            return {
                "ok": True,
                "title": content.get("title", self._page.title()),
                "url": content.get("url", self._page.url),
                "content": content.get("content", ""),
                "length": content.get("length", 0),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


# Module-level singleton (lazily connected)
_probe: Optional[BrowserProbe] = None


def get_browser_probe(cdp_endpoint: str = _CDP_ENDPOINT) -> BrowserProbe:
    global _probe
    if _probe is None:
        _probe = BrowserProbe(cdp_endpoint=cdp_endpoint)
    return _probe
