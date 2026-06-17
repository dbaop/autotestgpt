from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from service.browser_probe_service import get_browser_probe
from service.ui_runner_service import run_ui_dsl

logger = logging.getLogger(__name__)

_HEALABLE_ACTIONS = {"fill", "click", "select"}
_HEALABLE_ASSERTIONS = {"element_visible", "element_text", "element_count"}


def element_to_selector(element: Dict[str, Any]) -> Optional[str]:
    element_id = (element.get("id") or "").strip()
    if element_id:
        return f"#{element_id}"

    test_id = (element.get("data_testid") or "").strip()
    if test_id:
        return f"[data-testid='{test_id}']"

    name = (element.get("name") or "").strip()
    tag = (element.get("tag") or "input").strip() or "input"
    if name:
        return f"{tag}[name='{name}']"

    placeholder = (element.get("placeholder") or "").strip()
    if placeholder and tag in {"input", "textarea"}:
        return f"{tag}[placeholder='{placeholder}']"

    aria_label = (element.get("aria_label") or "").strip()
    if aria_label and tag in {"button", "a", "input", "textarea"}:
        return f"{tag}[aria-label='{aria_label}']"

    text = (element.get("text") or "").strip()
    if text and tag in {"button", "a"} and len(text) <= 40:
        escaped = text.replace("'", "\\'")
        return f"{tag}:has-text('{escaped}')"

    return None


def is_healable_failure(result: Dict[str, Any]) -> bool:
    if result.get("status") not in {"failed", "error"}:
        return False

    payload = result.get("result") or {}
    for step in payload.get("steps") or []:
        if not step.get("ok") and step.get("selector"):
            return True
    for assertion in payload.get("assertions") or []:
        if not assertion.get("pass") and assertion.get("selector"):
            return True
    return False


def collect_failed_selector_targets(dsl: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = result.get("result") or {}
    failed_selectors = {
        step.get("selector")
        for step in payload.get("steps") or []
        if not step.get("ok") and step.get("selector")
    }
    failed_selectors.update(
        assertion.get("selector")
        for assertion in payload.get("assertions") or []
        if not assertion.get("pass") and assertion.get("selector")
    )

    targets: List[Dict[str, Any]] = []
    for index, step in enumerate(dsl.get("when") or []):
        selector = step.get("selector")
        if selector in failed_selectors:
            targets.append(
                {
                    "selector": selector,
                    "action": (step.get("action") or "").lower(),
                    "value": step.get("value", ""),
                    "location": f"when[{index}]",
                }
            )
    for index, assertion in enumerate(dsl.get("then") or []):
        selector = assertion.get("selector")
        if selector in failed_selectors:
            targets.append(
                {
                    "selector": selector,
                    "action": (assertion.get("type") or "").lower(),
                    "value": assertion.get("contains", assertion.get("value", "")),
                    "location": f"then[{index}]",
                }
            )
    return targets


def _selector_tokens(selector: str) -> List[str]:
    normalized = (selector or "").lower()
    tokens = re.findall(r"[a-z0-9\u4e00-\u9fff_-]{2,}", normalized)
    deduped: List[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
    return deduped


def _score_element_for_target(element: Dict[str, Any], target: Dict[str, Any]) -> Tuple[float, Optional[str]]:
    if element.get("visible") is False:
        return 0.0, None

    new_selector = element_to_selector(element)
    if not new_selector:
        return 0.0, None

    action = (target.get("action") or "").lower()
    tag = (element.get("tag") or "").lower()
    score = 0.0

    if action in _HEALABLE_ACTIONS and action == "fill" and tag in {"input", "textarea"}:
        score += 2.0
    if action in _HEALABLE_ACTIONS and action == "click" and tag in {"button", "a"}:
        score += 2.0
    if action in _HEALABLE_ASSERTIONS and tag:
        score += 1.0

    old_selector = (target.get("selector") or "").lower()
    haystack = " ".join(
        part
        for part in [
            element.get("id") or "",
            element.get("name") or "",
            element.get("placeholder") or "",
            element.get("aria_label") or "",
            element.get("text") or "",
            " ".join(element.get("classList") or []),
        ]
        if part
    ).lower()

    for token in _selector_tokens(old_selector):
        if token in haystack:
            score += 2.5

    value = str(target.get("value") or "").lower()
    if value and value in haystack:
        score += 1.5

    if element.get("id") and element["id"] in old_selector:
        score += 4.0
    if element.get("data_testid") and element["data_testid"] in old_selector:
        score += 4.0

    return score, new_selector


def suggest_selector_fixes(
    dsl: Dict[str, Any],
    result: Dict[str, Any],
    snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not snapshot.get("ok"):
        return []

    elements = snapshot.get("elements") or []
    fixes: List[Dict[str, Any]] = []
    seen_old: set[str] = set()

    for target in collect_failed_selector_targets(dsl, result):
        old_selector = target.get("selector")
        if not old_selector or old_selector in seen_old:
            continue

        best_score = 0.0
        best_selector: Optional[str] = None
        best_reason = ""

        for element in elements:
            score, new_selector = _score_element_for_target(element, target)
            if score > best_score and new_selector and new_selector != old_selector:
                best_score = score
                best_selector = new_selector
                best_reason = (
                    f"matched {element.get('tag')} "
                    f"id={element.get('id') or '-'} "
                    f"placeholder={element.get('placeholder') or '-'} "
                    f"text={(element.get('text') or '')[:30]}"
                )

        if best_selector and best_score >= 2.0:
            fixes.append(
                {
                    "old_selector": old_selector,
                    "new_selector": best_selector,
                    "reason": best_reason.strip(),
                    "location": target.get("location"),
                    "score": round(best_score, 3),
                }
            )
            seen_old.add(old_selector)

    return fixes


def apply_fixes_to_dsl(dsl: Dict[str, Any], fixes: List[Dict[str, Any]]) -> Dict[str, Any]:
    patched = copy.deepcopy(dsl)
    replacements = {
        fix["old_selector"]: fix["new_selector"]
        for fix in fixes
        if fix.get("old_selector") and fix.get("new_selector")
    }
    if not replacements:
        return patched

    for step in patched.get("when") or []:
        selector = step.get("selector")
        if selector in replacements:
            step["selector"] = replacements[selector]

    for assertion in patched.get("then") or []:
        selector = assertion.get("selector")
        if selector in replacements:
            assertion["selector"] = replacements[selector]

    return patched


def build_execution_result_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(result.get("result") or {})
    if result.get("heal_attempted"):
        payload["heal_attempted"] = True
        payload["healed"] = bool(result.get("healed"))
        payload["heal_fixes"] = result.get("heal_fixes") or []
        if result.get("heal_error"):
            payload["heal_error"] = result.get("heal_error")
    return payload


def build_execution_detail_extras(result: Dict[str, Any]) -> Dict[str, Any]:
    extras: Dict[str, Any] = {}
    if not result.get("heal_attempted"):
        return extras
    extras["heal_attempted"] = True
    extras["healed"] = bool(result.get("healed"))
    extras["heal_fixes"] = result.get("heal_fixes") or []
    if result.get("heal_error"):
        extras["heal_error"] = result.get("heal_error")
    return extras


def build_heal_message(
    phase: str,
    script_id: int,
    *,
    healed: Optional[bool] = None,
    heal_fixes: Optional[List[Dict[str, Any]]] = None,
    heal_error: Optional[str] = None,
    via: Optional[str] = None,
) -> str:
    if phase == "attempting":
        return f"脚本 #{script_id} 选择器失效，正在 snapshot 页面并尝试自愈..."
    if phase == "recovery":
        return f"脚本 #{script_id} 通过 recovery_steps 兜底步骤恢复执行。"
    if phase == "success":
        fixes = heal_fixes or []
        if fixes:
            first = fixes[0]
            return (
                f"脚本 #{script_id} 自愈成功：{first.get('old_selector')} → {first.get('new_selector')}"
            )
        return f"脚本 #{script_id} 自愈成功。"
    if phase == "failed":
        if heal_error:
            return f"脚本 #{script_id} 自愈失败：{heal_error}"
        return f"脚本 #{script_id} 自愈失败。"
    return f"脚本 #{script_id} 自愈事件：{phase}"


def build_heal_sse_event(
    script_id: int,
    phase: str,
    *,
    healed: Optional[bool] = None,
    heal_fixes: Optional[List[Dict[str, Any]]] = None,
    heal_error: Optional[str] = None,
    via: Optional[str] = None,
) -> Dict[str, Any]:
    fixes = heal_fixes or []
    return {
        "type": "heal_event",
        "agent": "exec_agent",
        "script_id": script_id,
        "phase": phase,
        "healed": healed,
        "heal_fixes": fixes,
        "heal_error": heal_error,
        "via": via,
        "message": build_heal_message(
            phase,
            script_id,
            healed=healed,
            heal_fixes=fixes,
            heal_error=heal_error,
            via=via,
        ),
    }


def collect_recovery_step_events(result: Dict[str, Any], script_id: int) -> List[Dict[str, Any]]:
    steps = (result.get("result") or {}).get("steps") or []
    events: List[Dict[str, Any]] = []
    for step in steps:
        if step.get("via") != "recovery_steps":
            continue
        events.append(
            build_heal_sse_event(
                script_id,
                "recovery",
                healed=True,
                via="recovery_steps",
                heal_fixes=[
                    {
                        "old_selector": step.get("original_selector") or step.get("selector"),
                        "new_selector": step.get("selector"),
                        "reason": "recovery_steps fallback",
                    }
                ],
            )
        )
    return events


def attempt_ui_dsl_heal(
    dsl: Dict[str, Any],
    failed_result: Dict[str, Any],
    base_url: str = "",
    screenshot_prefix: str = "ui",
) -> Dict[str, Any]:
    if not is_healable_failure(failed_result):
        return {
            "result": failed_result,
            "heal_attempted": False,
            "healed": False,
            "heal_fixes": [],
            "fixed_dsl": None,
            "heal_error": None,
        }

    probe = get_browser_probe()
    if not (probe.is_connected or probe.connect()):
        return {
            "result": {
                **failed_result,
                "heal_attempted": True,
                "healed": False,
                "heal_fixes": [],
                "fixed_dsl": None,
                "heal_error": "browser unavailable for snapshot",
            },
            "heal_attempted": True,
            "healed": False,
            "heal_fixes": [],
            "fixed_dsl": None,
            "heal_error": "browser unavailable for snapshot",
        }

    snapshot = probe.snapshot()
    fixes = suggest_selector_fixes(dsl, failed_result, snapshot)
    if not fixes:
        return {
            "result": {
                **failed_result,
                "heal_attempted": True,
                "healed": False,
                "heal_fixes": [],
                "fixed_dsl": None,
                "heal_error": "no selector fixes found from snapshot",
            },
            "heal_attempted": True,
            "healed": False,
            "heal_fixes": [],
            "fixed_dsl": None,
            "heal_error": "no selector fixes found from snapshot",
        }

    fixed_dsl = apply_fixes_to_dsl(dsl, fixes)
    retry = run_ui_dsl(
        fixed_dsl,
        base_url=base_url,
        screenshot_prefix=f"{screenshot_prefix}_heal",
    )
    healed = retry.get("status") == "success"
    merged = {
        **retry,
        "heal_attempted": True,
        "healed": healed,
        "heal_fixes": fixes,
        "fixed_dsl": fixed_dsl if healed else None,
        "heal_error": None if healed else retry.get("error"),
    }
    return {
        "result": merged,
        "heal_attempted": True,
        "healed": healed,
        "heal_fixes": fixes,
        "fixed_dsl": fixed_dsl if healed else None,
        "heal_error": merged.get("heal_error"),
    }


def run_ui_dsl_with_self_heal(
    dsl: Dict[str, Any],
    base_url: str = "",
    screenshot_prefix: str = "ui",
    max_heal_attempts: int = 1,
) -> Dict[str, Any]:
    result = run_ui_dsl(dsl, base_url=base_url, screenshot_prefix=screenshot_prefix)
    if result.get("status") == "success" or max_heal_attempts <= 0:
        return {**result, "heal_attempted": False, "healed": False, "heal_fixes": [], "fixed_dsl": None}

    heal_outcome = attempt_ui_dsl_heal(
        dsl,
        result,
        base_url=base_url,
        screenshot_prefix=screenshot_prefix,
    )
    return heal_outcome["result"]
