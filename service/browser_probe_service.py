"""
Browser probe service — connects to an existing Chrome instance via CDP.

Uses Playwright's connect_over_cdp to attach to the user's browser (where the
CDP bridge MCP Chrome extension is already installed).  All methods are
synchronous so they can be called directly from agent tool functions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CDP_ENDPOINT = "http://localhost:9222"
_PAGE_STABILIZE_MS = 1500  # wait for JS frameworks to render


class BrowserProbe:
    """Lightweight browser controller backed by Playwright-over-CDP."""

    def __init__(self, cdp_endpoint: str = _CDP_ENDPOINT):
        self._cdp_endpoint = cdp_endpoint
        self._playwright = None
        self._browser = None
        self._page = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to the existing Chrome instance.  Returns True on success."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright is not installed; run: pip install playwright && playwright install chromium")
            return False

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(self._cdp_endpoint, timeout=10000)
            pages = self._browser.contexts[0].pages if self._browser.contexts else []
            self._page = pages[0] if pages else self._browser.contexts[0].new_page()
            logger.info("Connected to Chrome via CDP at %s", self._cdp_endpoint)
            return True
        except Exception as exc:
            logger.warning("Failed to connect to Chrome CDP at %s: %s", self._cdp_endpoint, exc)
            self.disconnect()
            return False

    def disconnect(self):
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

    @property
    def is_connected(self) -> bool:
        return self._page is not None and self._browser is not None

    # ------------------------------------------------------------------
    # High-level operations (used by agent tools)
    # ------------------------------------------------------------------

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to *url* and return page metadata after stabilisation."""
        if not self.is_connected and not self.connect():
            return {"ok": False, "error": "Could not connect to Chrome via CDP. Is Chrome running with --remote-debugging-port=9222?"}

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
        """Capture a lightweight DOM / accessibility snapshot.

        Returns interactive elements: buttons, links, inputs, selects, and
        their visible text, CSS selectors, and ARIA attributes.
        """
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
        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected."}

        try:
            self._page.fill(selector, value, timeout=5000)
            return {"ok": True, "filled": selector, "value": value}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "selector": selector}

    def get_network_requests(self, limit: int = 50) -> Dict[str, Any]:
        """Return recently captured network requests (URL + status)."""
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
        if not self.is_connected:
            return {"ok": False, "error": "Browser not connected."}

        try:
            result = self._page.evaluate(code)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


# Module-level singleton (lazily connected)
_probe: Optional[BrowserProbe] = None


def get_browser_probe(cdp_endpoint: str = _CDP_ENDPOINT) -> BrowserProbe:
    global _probe
    if _probe is None:
        _probe = BrowserProbe(cdp_endpoint=cdp_endpoint)
    return _probe
