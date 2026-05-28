"""
Requirement application service.
"""

from datetime import datetime, timezone

from models import Requirement, TestCase, db
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


def get_requirement_detail(req_id: int):
    requirement = get_requirement_or_404(req_id)
    test_cases = TestCase.query.filter_by(requirement_id=req_id).all()
    payload = requirement.to_dict()
    payload["test_cases"] = [tc.to_dict() for tc in test_cases]
    payload["structured_data"] = requirement.structured_data
    payload["knowledge_base_id"] = requirement.knowledge_base_id
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
    db.session.delete(requirement)
    db.session.commit()
