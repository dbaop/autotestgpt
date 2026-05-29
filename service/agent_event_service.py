"""
Agent event emission and persistence.
"""

from __future__ import annotations

from typing import Any

from models import AgentEvent, db


def emit_agent_event(
    requirement_id: int,
    agent: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> AgentEvent:
    event = AgentEvent(
        requirement_id=requirement_id,
        agent=agent,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    db.session.add(event)
    db.session.commit()
    return event


def list_events(requirement_id: int, since_id: int | None = None, limit: int = 200) -> list[AgentEvent]:
    query = AgentEvent.query.filter_by(requirement_id=requirement_id).order_by(AgentEvent.id.asc())
    if since_id:
        query = query.filter(AgentEvent.id > since_id)
    return query.limit(limit).all()
