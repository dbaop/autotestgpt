"""
Requirement application service.
"""

from datetime import datetime, timezone

from models import (
    AgentEvent,
    Conversation,
    DefectCandidate,
    ExecutionRecord,
    FinalReport,
    FixSuggestion,
    Requirement,
    TestCase,
    TestScript,
    db,
)
from service.errors import NotFoundError, ValidationError


ALLOWED_REQUIREMENT_STATUS = {
    "pending",
    "parsed",
    "cases_generated",
    "code_generated",
    "executing",
    "executed",
    "completed",
    "error",
}


def _now():
    return datetime.now(timezone.utc)


def list_requirements(page: int, per_page: int, status: str | None):
    query = Requirement.query
    if status:
        query = query.filter_by(status=status)
    return query.order_by(Requirement.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)


def get_requirement_or_404(req_id: int) -> Requirement:
    requirement = db.session.get(Requirement, req_id)
    if not requirement:
        raise NotFoundError(f"Requirement {req_id} not found")
    return requirement


def _latest_executions_for_requirement(req_id: int):
    """Build the execution panel from durable ExecutionRecord rows (latest per
    script).

    The frontend used to read requirement.execution_progress.details, but that
    JSON blob is only written by a live run — older requirements (and any run
    before the orchestrator started persisting details) have no details, so the
    execution panel showed "暂无执行记录" and the per-script 重试 button never
    appeared even though execution history existed. ExecutionRecord is the
    durable source of truth, so derive the panel from it and a retry (which
    inserts a fresh ExecutionRecord) is reflected on the next reload.
    """
    cases = TestCase.query.filter_by(requirement_id=req_id).all()
    case_ids = [c.id for c in cases]
    if not case_ids:
        return []
    scripts = TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).all()
    script_map = {s.id: s for s in scripts}
    if not script_map:
        return []
    records = (
        ExecutionRecord.query
        .filter(ExecutionRecord.test_script_id.in_(list(script_map.keys())))
        .order_by(ExecutionRecord.id.asc())
        .all()
    )
    # Highest-id record wins → the latest attempt (incl. retries).
    latest: dict[int, ExecutionRecord] = {}
    for rec in records:
        latest[rec.test_script_id] = rec

    details = []
    for sid, rec in latest.items():
        script = script_map.get(sid)
        ts = rec.finished_at or rec.started_at
        details.append({
            "script_id": sid,
            "script_name": script.file_path if script else None,
            "case_id": script.test_case_id if script else None,
            "status": rec.status,
            "execution_time": rec.execution_time,
            "error": rec.error_message,
            "end_time": ts.isoformat() if ts else None,
        })
    details.sort(key=lambda d: d["script_id"])
    return details


def get_requirement_detail(req_id: int):
    requirement = get_requirement_or_404(req_id)
    test_cases = TestCase.query.filter_by(requirement_id=req_id).all()
    payload = requirement.to_dict()
    payload["test_cases"] = [tc.to_dict() for tc in test_cases]
    payload["structured_data"] = requirement.structured_data
    payload["knowledge_base_id"] = requirement.knowledge_base_id
    payload["executions"] = _latest_executions_for_requirement(req_id)
    return payload


def create_requirement(data: dict):
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    if not title or not description:
        raise ValidationError("title and description are required")

    requirement = Requirement(
        title=title,
        description=description,
        raw_text=data.get("raw_text", description),
        status="pending",
        structured_data=data.get("structured_data"),
        knowledge_base_id=data.get("knowledge_base_id"),
        project_id=data.get("project_id"),
    )
    db.session.add(requirement)
    db.session.commit()
    return requirement


def update_requirement(req_id: int, data: dict):
    requirement = get_requirement_or_404(req_id)

    if "title" in data:
        requirement.title = data["title"]
    if "description" in data:
        requirement.description = data["description"]
    if "status" in data:
        status = data["status"]
        if status not in ALLOWED_REQUIREMENT_STATUS:
            raise ValidationError(f"invalid status: {status}")
        if not requirement.can_transition_to(status):
            raise ValidationError(f"invalid status transition: {requirement.status} -> {status}")
        requirement.status = status
    if "structured_data" in data:
        requirement.structured_data = data["structured_data"]
    if "knowledge_base_id" in data:
        requirement.knowledge_base_id = data["knowledge_base_id"]

    requirement.updated_at = _now()
    db.session.commit()
    return requirement


def delete_requirement(req_id: int):
    requirement = get_requirement_or_404(req_id)

    # Delete dependent rows that aren't covered by ORM cascade.
    # Order matters: FixSuggestion depends on DefectCandidate, so delete it first.
    FixSuggestion.query.filter_by(requirement_id=req_id).delete()
    AgentEvent.query.filter_by(requirement_id=req_id).delete()
    FinalReport.query.filter_by(requirement_id=req_id).delete()
    DefectCandidate.query.filter_by(requirement_id=req_id).delete()
    # Conversation.requirement_id is nullable; we delete the conversation (and
    # its messages cascade) since it was auto-created for this requirement.
    Conversation.query.filter_by(requirement_id=req_id).delete()
    # TestCase cascades via Requirement.test_cases (cascade='all, delete-orphan'),
    # but we flush first to avoid any FK ordering surprises.
    db.session.flush()

    db.session.delete(requirement)
    db.session.commit()
