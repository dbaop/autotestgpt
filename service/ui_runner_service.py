"""
UI test execution via the /browser-automation CDP channel.

Executes a Given-When-Then JSON DSL (aligned with the browser-automation skill's
functional-testing module) step-by-step through ``BrowserProbe`` — which drives a
real browser via CDP Bridge MCP → direct CDP → standalone Chromium (auto-fallback).

This is the CDP counterpart to ``ExecAgent.process()`` (pytest subprocess). It
returns a result dict with the SAME shape so callers can persist an
``ExecutionRecord`` uniformly.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

from service.browser_probe_service import get_browser_probe
from service.screenshot_service import save_screenshot_from_data_url

logger = logging.getLogger(__name__)

# Actions that are expected to trigger a navigation (give the page time to settle)
_NAV_SETTLE_MS = 1.0


def _resolve_url(url: str, base_url: str) -> str:
    """Resolve a (possibly relative) DSL url against base_url."""
    url = (url or "").strip()
    base = (base_url or "").strip()
    if not url:
        return base
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if not base:
        return url
    return base.rstrip("/") + "/" + url.lstrip("/")


def _js_str(value: str) -> str:
    """Escape a Python string for safe embedding inside single-quoted JS."""
    return (value or "").replace("\\", "\\\\").replace("'", "\\'")


def _capture_screenshot(probe, prefix: str) -> str | None:
    try:
        shot = probe.screenshot()
        if shot.get("ok") and shot.get("data_url"):
            return save_screenshot_from_data_url(shot["data_url"], prefix=prefix)
    except Exception as exc:  # pragma: no cover - screenshot is best-effort
        logger.warning("UI runner screenshot failed (%s): %s", prefix, exc)
    return None


def _run_when_step(probe, step: Dict[str, Any]) -> Dict[str, Any]:
    action = (step.get("action") or "").lower()
    selector = step.get("selector", "")
    value = step.get("value", "")

    if action == "navigate":
        r = probe.navigate(step.get("url", ""))
        time.sleep(_NAV_SETTLE_MS)
        ok = bool(r.get("ok"))
        return {"action": "navigate", "url": step.get("url", ""), "ok": ok, "error": r.get("error")}

    if action == "fill":
        r = probe.fill(selector, value)
        ok = bool(r.get("ok"))
        return {"action": "fill", "selector": selector, "ok": ok, "error": r.get("error")}

    if action == "click":
        r = probe.click(selector)
        time.sleep(_NAV_SETTLE_MS)  # click may trigger navigation (esp. MCP backend)
        ok = bool(r.get("ok"))
        return {"action": "click", "selector": selector, "ok": ok, "error": r.get("error")}

    if action == "select":
        code = (
            f"var e=document.querySelector('{_js_str(selector)}');"
            f"if(e){{e.value='{_js_str(str(value))}';"
            f"e.dispatchEvent(new Event('change',{{bubbles:true}}));'ok'}}else 'not found'"
        )
        r = probe.execute_js(code)
        ok = r.get("ok") and "not found" not in str(r.get("result", ""))
        return {"action": "select", "selector": selector, "ok": bool(ok), "error": r.get("error")}

    if action == "wait":
        cond = step.get("condition_js")
        if cond:
            deadline = time.time() + float(step.get("timeout", 5))
            while time.time() < deadline:
                r = probe.execute_js(f"!!({cond})")
                if r.get("ok") and str(r.get("result")).lower() in ("true", "1"):
                    return {"action": "wait", "ok": True}
                time.sleep(0.3)
            return {"action": "wait", "ok": False, "error": "wait condition timeout"}
        time.sleep(float(step.get("seconds", 1)))
        return {"action": "wait", "ok": True}

    return {"action": action or "unknown", "ok": False, "error": f"unsupported action: {action}"}


def _run_assertion(probe, assertion: Dict[str, Any]) -> Dict[str, Any]:
    atype = (assertion.get("type") or "").lower()
    selector = assertion.get("selector", "")

    if atype == "url_contains":
        expected = assertion.get("value", "")
        r = probe.execute_js("window.location.href")
        actual = str(r.get("result", "")) if r.get("ok") else ""
        return {"type": atype, "pass": expected in actual, "expected": expected, "actual": actual}

    if atype == "element_visible":
        code = (
            f"(function(){{var e=document.querySelector('{_js_str(selector)}');"
            f"return !!(e && e.offsetParent !== null);}})()"
        )
        r = probe.execute_js(code)
        passed = r.get("ok") and str(r.get("result")).lower() in ("true", "1")
        return {"type": atype, "selector": selector, "pass": bool(passed)}

    if atype == "element_text":
        contains = assertion.get("contains", assertion.get("value", ""))
        code = (
            f"(function(){{var e=document.querySelector('{_js_str(selector)}');"
            f"return e ? e.textContent : '';}})()"
        )
        r = probe.execute_js(code)
        actual = str(r.get("result", "")) if r.get("ok") else ""
        return {
            "type": atype, "selector": selector,
            "pass": contains in actual, "expected": contains, "actual": actual[:200],
        }

    if atype == "element_count":
        code = f"document.querySelectorAll('{_js_str(selector)}').length"
        r = probe.execute_js(code)
        try:
            actual = int(r.get("result")) if r.get("ok") else -1
        except (TypeError, ValueError):
            actual = -1
        if assertion.get("min") is not None:
            passed = actual >= int(assertion["min"])
            expected = f">={assertion['min']}"
        else:
            expected = int(assertion.get("value", 0))
            passed = actual == expected
        return {"type": atype, "selector": selector, "pass": bool(passed), "expected": expected, "actual": actual}

    return {"type": atype or "unknown", "pass": False, "error": f"unsupported assertion: {atype}"}


def run_ui_dsl(dsl: Dict[str, Any], base_url: str = "", screenshot_prefix: str = "ui") -> Dict[str, Any]:
    """Execute a Given-When-Then UI DSL against a real browser via CDP.

    Returns a dict shaped like ``ExecAgent.process()`` so an ExecutionRecord can
    be created uniformly:
        status: success | failed | error
        execution_time, error, report_path, screenshots, result{steps, assertions, passed}
    """
    started = time.time()
    screenshots: List[str] = []

    if not isinstance(dsl, dict):
        return {
            "status": "error", "execution_time": 0.0,
            "error": "invalid DSL (not an object)", "report_path": None,
            "screenshots": [], "result": {"steps": [], "assertions": [], "passed": False},
        }

    probe = get_browser_probe()
    try:
        connected = probe.is_connected or probe.connect()
    except Exception as exc:
        connected = False
        logger.warning("BrowserProbe.connect raised: %s", exc)
    if not connected:
        return {
            "status": "error", "execution_time": round(time.time() - started, 3),
            "error": "浏览器不可用：CDP bridge / 直连 CDP / standalone Chromium 均连接失败。",
            "report_path": None, "screenshots": [],
            "result": {"steps": [], "assertions": [], "passed": False},
        }

    steps: List[Dict[str, Any]] = []
    assertions: List[Dict[str, Any]] = []

    try:
        # ---- Given: navigate ----
        given = dsl.get("given") or {}
        target_url = _resolve_url(given.get("url", ""), base_url)
        if not target_url:
            return {
                "status": "error", "execution_time": round(time.time() - started, 3),
                "error": "缺少测试地址：given.url 与 base_url(test_url) 均为空。",
                "report_path": None, "screenshots": [],
                "result": {"steps": [], "assertions": [], "passed": False},
            }
        nav = probe.navigate(target_url)
        time.sleep(_NAV_SETTLE_MS)
        steps.append({"action": "navigate", "url": target_url, "ok": bool(nav.get("ok")), "error": nav.get("error")})

        before = _capture_screenshot(probe, f"{screenshot_prefix}_before")
        if before:
            screenshots.append(before)

        if not nav.get("ok"):
            return {
                "status": "error", "execution_time": round(time.time() - started, 3),
                "error": f"导航失败: {nav.get('error', target_url)}",
                "report_path": None, "screenshots": screenshots,
                "result": {"steps": steps, "assertions": [], "passed": False},
            }

        # ---- When: actions ----
        for step in dsl.get("when", []) or []:
            steps.append(_run_when_step(probe, step))

        # ---- Then: assertions ----
        for assertion in dsl.get("then", []) or []:
            assertions.append(_run_assertion(probe, assertion))

        after = _capture_screenshot(probe, f"{screenshot_prefix}_after")
        if after:
            screenshots.append(after)

        steps_ok = all(s.get("ok") for s in steps)
        asserts_ok = all(a.get("pass") for a in assertions)
        passed = steps_ok and asserts_ok and bool(assertions)
        status = "success" if passed else "failed"

        error = None
        if not passed:
            failed_bits = [s for s in steps if not s.get("ok")] + [a for a in assertions if not a.get("pass")]
            error = "未通过的步骤/断言: " + json.dumps(failed_bits, ensure_ascii=False)[:800]

        return {
            "status": status, "execution_time": round(time.time() - started, 3),
            "error": error, "report_path": None, "screenshots": screenshots,
            "result": {"steps": steps, "assertions": assertions, "passed": passed},
        }

    except Exception as exc:
        logger.error("UI DSL execution failed: %s", exc)
        return {
            "status": "error", "execution_time": round(time.time() - started, 3),
            "error": str(exc), "report_path": None, "screenshots": screenshots,
            "result": {"steps": steps, "assertions": assertions, "passed": False},
        }
