"""
Agent workbench aggregation service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from models import (
    AgentEvent,
    CodeReviewFinding,
    CodeReviewTask,
    DefectCandidate,
    ExecutionRecord,
    FinalReport,
    Requirement,
    TestCase,
    TestScript,
    db,
)

AGENT_DEFS = [
    ("req_agent", "ReqAgent", 0),
    ("browser_agent", "BrowserAgent", 1),
    ("case_agent", "CaseAgent", 2),
    ("code_agent", "CodeAgent", 3),
    ("code_review_agent", "CodeReviewAgent", 4),
    ("exec_agent", "ExecAgent", 5),
    ("bug_agent", "BugAgent", 6),
]

STATUS_ORDER = [
    "pending",
    "parsed",
    "cases_generated",
    "code_generated",
    "executing",
    "executed",
    "completed",
    "error",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _merge_environment(requirement: Requirement) -> dict[str, Any]:
    progress = requirement.execution_progress or {}
    structured = requirement.structured_data or {}
    env = {}
    if isinstance(structured, dict):
        env.update(structured.get("test_environment") or {})
    if isinstance(progress, dict):
        env.update(progress.get("test_environment") or {})
    return {
        "test_url": env.get("test_url"),
        "login_state": env.get("login_state", "unknown"),
        "credential_ref": env.get("credential_ref"),
        "allow_explore": env.get("allow_explore", True),
        "last_probe_at": env.get("last_probe_at"),
        "probe_status": env.get("probe_status"),
    }


def _artifact_counts(requirement_id: int) -> dict[str, int]:
    cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
    case_ids = [c.id for c in cases]
    scripts = (
        TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).all()
        if case_ids
        else []
    )
    ui_scripts = sum(1 for s in scripts if (s.script_type or "").lower() == "playwright")
    api_scripts = len(scripts) - ui_scripts

    requirement = db.session.get(Requirement, requirement_id)
    progress = (requirement.execution_progress or {}) if requirement else {}
    review_task_id = None
    if isinstance(progress, dict):
        review = progress.get("review") or {}
        review_task_id = review.get("task_id")

    review_findings = (
        CodeReviewFinding.query.filter_by(task_id=review_task_id).count()
        if review_task_id
        else 0
    )
    defects = DefectCandidate.query.filter_by(requirement_id=requirement_id).count()
    reports = FinalReport.query.filter_by(requirement_id=requirement_id).count()

    return {
        "cases": len(cases),
        "ui_scripts": ui_scripts,
        "api_scripts": api_scripts,
        "review_findings": review_findings,
        "defects": defects,
        "reports": reports,
    }


def _agent_status_map(status: str) -> dict[str, str]:
    queued = {
        "req_agent": "queued",
        "browser_agent": "queued",
        "case_agent": "queued",
        "code_agent": "queued",
        "code_review_agent": "queued",
        "exec_agent": "queued",
        "bug_agent": "queued",
    }
    done = {key: "done" for key in queued}
    templates: dict[str, dict[str, str]] = {
        "pending": {**queued, "req_agent": "running"},
        "parsed": {**queued, "req_agent": "done", "case_agent": "running"},
        "cases_generated": {
            **queued,
            "req_agent": "done",
            "case_agent": "done",
            "code_agent": "running",
        },
        "code_generated": {
            **queued,
            "req_agent": "done",
            "case_agent": "done",
            "code_agent": "done",
            "exec_agent": "running",
        },
        "executing": {
            **queued,
            "req_agent": "done",
            "case_agent": "done",
            "code_agent": "done",
            "exec_agent": "running",
            "code_review_agent": "running",
        },
        "executed": {
            **queued,
            "req_agent": "done",
            "case_agent": "done",
            "code_agent": "done",
            "exec_agent": "done",
            "code_review_agent": "done",
            "bug_agent": "running",
        },
        "completed": done,
        "error": {
            **queued,
            "req_agent": "failed",
        },
    }
    return templates.get(status, queued)


def _current_action(agent_id: str, requirement: Requirement, artifacts: dict[str, int]) -> str:
    env = _merge_environment(requirement)
    status = requirement.status
    if agent_id == "req_agent":
        return "解析需求结构与测试点"
    if agent_id == "browser_agent":
        if env.get("test_url"):
            return f"使用 agent-browser 探活 {env['test_url']}"
        return "等待测试地址"
    if agent_id == "case_agent":
        if status in ("cases_generated", "code_generated", "executing", "executed", "completed"):
            return f"已生成 {artifacts['cases']} 条用例"
        return "设计场景与边界用例"
    if agent_id == "code_agent":
        if artifacts["ui_scripts"] or artifacts["api_scripts"]:
            return f"沉淀 Playwright/API 脚本 {artifacts['ui_scripts'] + artifacts['api_scripts']} 个"
        return "生成自动化脚本"
    if agent_id == "code_review_agent":
        if artifacts["review_findings"]:
            return f"扫描代码变更，发现 {artifacts['review_findings']} 条风险"
        return "等待代码 Review 任务"
    if agent_id == "exec_agent":
        return "执行 Playwright/pytest 并收集 trace"
    if agent_id == "bug_agent":
        if artifacts["defects"]:
            return f"归因失败并沉淀 {artifacts['defects']} 条缺陷候选"
        return "等待执行结果"
    return "待命"


def _build_agents(requirement: Requirement, artifacts: dict[str, int]) -> list[dict[str, Any]]:
    status_map = _agent_status_map(requirement.status)
    env = _merge_environment(requirement)
    if env.get("test_url") and requirement.status not in ("pending",):
        status_map["browser_agent"] = (
            "done" if requirement.status in ("parsed", "cases_generated", "code_generated", "executing", "executed", "completed") else status_map["browser_agent"]
        )
    if requirement.status in ("cases_generated", "code_generated", "executing", "executed", "completed"):
        status_map["case_agent"] = "done"
    if requirement.status in ("code_generated", "executing", "executed", "completed"):
        status_map["code_agent"] = "done"
    progress = requirement.execution_progress or {}
    if isinstance(progress, dict) and progress.get("review"):
        if requirement.status in ("executed", "completed"):
            status_map["code_review_agent"] = "done"
        elif requirement.status == "executing":
            status_map["code_review_agent"] = "running"
    if artifacts["defects"] or requirement.status in ("executed", "completed"):
        status_map["bug_agent"] = "done" if requirement.status in ("executed", "completed") else status_map["bug_agent"]

    return [
        {
            "id": agent_id,
            "name": display_name,
            "status": status_map.get(agent_id, "queued"),
            "current_action": _current_action(agent_id, requirement, artifacts),
        }
        for agent_id, display_name, _ in AGENT_DEFS
    ]


def _synthetic_events(requirement: Requirement, artifacts: dict[str, int]) -> list[dict[str, Any]]:
    env = _merge_environment(requirement)
    events: list[dict[str, Any]] = []
    base_ts = requirement.created_at or datetime.now(timezone.utc)

    def push(agent: str, event_type: str, message: str, offset: int = 0):
        events.append(
            {
                "id": len(events) + 1,
                "agent": agent,
                "event_type": event_type,
                "message": message,
                "created_at": base_ts.isoformat() if hasattr(base_ts, "isoformat") else _now_iso(),
                "payload": {},
            }
        )

    push("ReqAgent", "started", "开始解析需求")
    if requirement.status != "pending":
        push("ReqAgent", "completed", "需求解析完成")

    if env.get("test_url"):
        push("BrowserAgent", "progress", f"打开测试地址 {env['test_url']}（agent-browser）")
        if env.get("login_state") == "pre_authenticated":
            push("BrowserAgent", "completed", "复用预登录会话成功")

    if artifacts["cases"]:
        push("CaseAgent", "completed", f"生成 {artifacts['cases']} 条测试用例")

    if artifacts["ui_scripts"] or artifacts["api_scripts"]:
        push("CodeAgent", "completed", f"生成 {artifacts['ui_scripts'] + artifacts['api_scripts']} 个脚本")

    if artifacts["review_findings"]:
        push("CodeReviewAgent", "completed", f"发现 {artifacts['review_findings']} 条高风险变更")

    if artifacts["defects"]:
        push("BugAgent", "completed", f"确认 {artifacts['defects']} 条缺陷候选")

    return events


def _load_events(requirement_id: int) -> list[dict[str, Any]]:
    rows = (
        AgentEvent.query.filter_by(requirement_id=requirement_id)
        .order_by(AgentEvent.id.asc())
        .limit(200)
        .all()
    )
    if rows:
        return [row.to_dict() for row in rows]
    requirement = db.session.get(Requirement, requirement_id)
    if not requirement:
        return []
    artifacts = _artifact_counts(requirement_id)
    return _synthetic_events(requirement, artifacts)


def _interventions(events: list[dict[str, Any]], environment: dict[str, Any]) -> list[dict[str, Any]]:
    items = [e for e in events if e.get("event_type") == "waiting_user"]
    if environment.get("probe_status") == "failed":
        items.append(
            {
                "type": "test_environment",
                "message": "测试地址不可访问或登录态失效，请确认后重试",
                "test_url": environment.get("test_url"),
            }
        )
    return items


def build_requirement_workbench(requirement: Requirement) -> dict[str, Any]:
    artifacts = _artifact_counts(requirement.id)
    environment = _merge_environment(requirement)
    events = _load_events(requirement.id)
    agents = _build_agents(requirement, artifacts)

    progress = requirement.execution_progress or {}
    review = progress.get("review") if isinstance(progress, dict) else {}
    review_task = None
    if review and review.get("task_id"):
        review_task = db.session.get(CodeReviewTask, review["task_id"])

    return {
        "requirement": requirement.to_dict(),
        "environment": environment,
        "review": {
            "repo_url": review_task.repo_url if review_task else None,
            "branch": review_task.branch if review_task else None,
            "days": review_task.days if review_task else None,
            "status": review_task.status if review_task else None,
        },
        "artifacts": artifacts,
        "agents": agents,
        "events": events,
        "interventions": _interventions(events, environment),
        "overall_progress": {
            "status": requirement.status,
            "updated_at": requirement.updated_at.isoformat() if requirement.updated_at else None,
        },
    }


def list_workbench() -> dict[str, Any]:
    requirements = Requirement.query.order_by(Requirement.updated_at.desc()).limit(50).all()
    items = [build_requirement_workbench(req) for req in requirements]
    return {
        "summary": {"total_requirements": len(items)},
        "items": items,
    }


def get_workbench(requirement_id: int) -> dict[str, Any]:
    requirement = db.session.get(Requirement, requirement_id)
    if not requirement:
        from service.errors import NotFoundError

        raise NotFoundError(f"Requirement {requirement_id} not found")
    return build_requirement_workbench(requirement)
