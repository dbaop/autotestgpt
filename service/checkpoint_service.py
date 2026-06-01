"""
Checkpoint service — save and restore agent conversation state.

When an agent calls ask_user, the orchestrator saves the current LLM
conversation messages and phase, then pauses. When the user responds,
the checkpoint is loaded and the agent resumes where it left off.
"""

import logging
from typing import Any, Dict, List, Optional

from models import db, AgentEvent, Requirement

logger = logging.getLogger(__name__)


def save_checkpoint(
    requirement_id: int,
    phase: str,
    agent_type: str,
    conversation_messages: List[Dict[str, str]],
    metadata: Optional[Dict[str, Any]] = None,
) -> AgentEvent:
    """Save an agent checkpoint so the conversation can resume from this point."""
    requirement = db.session.get(Requirement, requirement_id)
    if requirement:
        requirement.current_phase = phase
        requirement.conversation_messages = conversation_messages

    event = AgentEvent(
        requirement_id=requirement_id,
        agent=agent_type,
        event_type="checkpoint",
        message=f"Checkpoint at phase {phase}",
        payload={
            "phase": phase,
            "agent_type": agent_type,
            "conversation_messages": conversation_messages,
            "metadata": metadata or {},
        },
    )
    db.session.add(event)
    db.session.commit()
    logger.info("Checkpoint saved: req=%d, phase=%s, messages=%d",
                 requirement_id, phase, len(conversation_messages))
    return event


def load_checkpoint(requirement_id: int) -> Optional[Dict[str, Any]]:
    """Load the latest checkpoint for a requirement.

    Returns:
        Checkpoint payload dict, or None if no checkpoint exists.
    """
    requirement = db.session.get(Requirement, requirement_id)
    if not requirement:
        return None

    event = (
        AgentEvent.query
        .filter_by(requirement_id=requirement_id, event_type="checkpoint")
        .order_by(AgentEvent.id.desc())
        .first()
    )
    if not event:
        return None

    return {
        "phase": event.payload.get("phase", "idle"),
        "agent_type": event.payload.get("agent_type", ""),
        "conversation_messages": event.payload.get("conversation_messages", []),
        "metadata": event.payload.get("metadata", {}),
        "event_id": event.id,
    }


def clear_checkpoints(requirement_id: int):
    """Remove all checkpoints for a requirement (e.g., when flow completes)."""
    db.session.execute(
        db.delete(AgentEvent).where(
            AgentEvent.requirement_id == requirement_id,
            AgentEvent.event_type == "checkpoint",
        )
    )
    db.session.commit()


def has_waiting_question(requirement_id: int) -> bool:
    """Check if there's a pending ask_user question for this requirement."""
    event = (
        AgentEvent.query
        .filter_by(requirement_id=requirement_id, event_type="waiting_user")
        .order_by(AgentEvent.id.desc())
        .first()
    )
    return event is not None
