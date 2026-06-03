"""
Conversation Orchestrator — manages multi-agent test workflow via conversation.

Replaces the rigid pipeline (AutoTestFlow) and the isolated chat (ChatRouter)
with a unified conversation-driven workflow where agents can ask questions,
search the knowledge base, and produce artifacts through multi-turn dialogue.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

from config import Config
from models import db, Conversation, Message, Requirement, AgentEvent

from .req_agent import ReqAgent
from .browser_agent import BrowserAgent
from .case_agent import CaseAgent
from .code_agent import CodeAgent
from .exec_agent import ExecAgent
from .review_agent import ReviewAgent

logger = logging.getLogger(__name__)

# Mapping from requirement status to orchestrator phase + agent
STATUS_TO_PHASE: Dict[str, Tuple[str, str]] = {
    "pending": ("parsing", "req_agent"),
    "parsed": ("exploring", "browser_agent"),
    "probed": ("designing_cases", "case_agent"),
    "cases_generated": ("generating_code", "code_agent"),
    "code_generated": ("executing", "exec_agent"),
    "executing": ("executing", "exec_agent"),
    "executed": ("completed", ""),
    "completed": ("completed", ""),
    "error": ("idle", ""),
}

# Status transitions when an artifact is produced
ARTIFACT_STATUS_MAP: Dict[str, str] = {
    "structured_requirement": "parsed",
    "page_map": "probed",
    "test_cases": "cases_generated",
    "test_scripts": "code_generated",
    "review_findings": "executed",
}


class ConversationOrchestrator:
    """Orchestrate the test workflow through conversation.

    The orchestrator:
      - Determines the current phase from the Requirement's status
      - Selects the appropriate agent for the phase
      - Gives the agent conversation context + tools
      - Streams agent events via SSE
      - Pauses when the agent asks the user a question
      - Auto-advances to the next phase when an artifact is produced
    """

    def __init__(self):
        self._agents: Dict[str, Any] = {
            "req_agent": ReqAgent(),
            "browser_agent": BrowserAgent(),
            "case_agent": CaseAgent(),
            "code_agent": CodeAgent(),
            "exec_agent": ExecAgent(),
            "review_agent": ReviewAgent(),
        }
        self._active_generators: Dict[int, Generator] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_message(
        self,
        conversation_id: int,
        user_message: str,
    ) -> Generator[Dict[str, Any], None, None]:
        """Process a user message in a conversation.

        This is a generator that yields SSE events.
        The caller (API route) pipes these events to the SSE stream.

        Yields:
            SSE event dicts: message, tool_call, tool_result, question,
            artifact, phase_change, error, done
        """
        conversation = db.session.get(Conversation, conversation_id)
        if not conversation:
            yield {"type": "error", "message": "Conversation not found"}
            return

        # Save user message
        user_msg = Message(
            conversation_id=conversation_id,
            sender="user",
            content=user_message,
            agent_type="user",
        )
        db.session.add(user_msg)
        db.session.commit()

        requirement_id = conversation.requirement_id
        requirement = db.session.get(Requirement, requirement_id) if requirement_id else None

        # Check if resuming from a waiting_user state
        if requirement and requirement_id in self._active_generators:
            # Resume the active agent with user's response
            yield from self._resume_agent(requirement_id, user_message)
            return

        # Determine phase and agent
        phase, agent_type = self._determine_phase(requirement_id, user_message)

        if agent_type and agent_type in self._agents:
            agent = self._agents[agent_type]
        else:
            agent = self._agents["req_agent"]

        # Build conversation context
        history = self._load_conversation_history(conversation_id)
        system_instruction = self._build_system_instruction(phase, requirement)

        # Run the agent
        yield {"type": "phase_change", "from": "idle", "to": phase, "agent": agent_type}

        agent_gen = agent.act(history, system_instruction)
        self._active_generators[requirement_id or 0] = agent_gen

        for event in agent_gen:
            # Save agent messages to DB
            if event.get("type") == "message" and event.get("complete"):
                self._save_agent_message(
                    conversation_id, agent_type, event["content"]
                )

            # Handle question → pause
            if event.get("type") == "question":
                self._handle_question(
                    requirement,
                    phase,
                    agent_type,
                    history,
                    event,
                )
                # Don't advance — wait for user response
                yield event
                yield {"type": "done"}
                return

            # Handle artifact → persist + advance
            if event.get("type") == "artifact":
                self._handle_artifact(
                    requirement,
                    event["key"],
                    event["data"],
                    conversation_id,
                )
                yield event

            yield event

        # Agent done — clean up
        self._active_generators.pop(requirement_id or 0, None)
        conversation.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        # Auto-advance if there's a next phase
        if requirement and not self._is_waiting(requirement):
            next_phase, next_agent = self._determine_next_phase(requirement)
            if next_agent and next_agent in self._agents:
                yield {"type": "phase_change", "from": phase, "to": next_phase, "agent": next_agent}
                # Recursively invoke next agent (but don't block for user)
                yield from self._auto_run_agent(
                    conversation_id, requirement, next_phase, next_agent
                )

        yield {"type": "done"}

    # ------------------------------------------------------------------
    # Phase and agent selection
    # ------------------------------------------------------------------

    def _determine_phase(self, requirement_id: Optional[int],
                         user_message: str) -> Tuple[str, str]:
        """Determine the current phase and which agent should handle the message."""
        if not requirement_id:
            return ("parsing", "req_agent")

        requirement = db.session.get(Requirement, requirement_id)
        if not requirement:
            return ("parsing", "req_agent")

        phase, agent_type = STATUS_TO_PHASE.get(
            requirement.status, ("parsing", "req_agent")
        )
        logger.info("Phase determined: status=%s → phase=%s, agent=%s",
                     requirement.status, phase, agent_type)
        return (phase, agent_type)

    def _determine_next_phase(self, requirement: Requirement) -> Tuple[str, str]:
        """After artifact save, determine the next phase and agent."""
        return STATUS_TO_PHASE.get(requirement.status, ("idle", ""))

    def _is_waiting(self, requirement: Requirement) -> bool:
        """Check if the requirement is waiting for user input."""
        if requirement.current_phase == "clarifying":
            return True
        return bool(
            AgentEvent.query.filter_by(
                requirement_id=requirement.id, event_type="waiting_user"
            ).first()
        )

    # ------------------------------------------------------------------
    # Conversation context
    # ------------------------------------------------------------------

    def _load_conversation_history(
        self, conversation_id: int
    ) -> List[Dict[str, str]]:
        """Load conversation messages as LLM-compatible role:content dicts."""
        messages = (
            Message.query
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at)
            .all()
        )
        history: List[Dict[str, str]] = []
        for msg in messages:
            role = "assistant" if msg.sender in (
                "req_agent", "browser_agent", "case_agent", "code_agent", "exec_agent",
                "review_agent", "router"
            ) else "user"
            history.append({"role": role, "content": msg.content})
        return history

    def _build_system_instruction(self, phase: str,
                                   requirement: Optional[Requirement]) -> str:
        """Build the system instruction for the current phase."""
        base = f"Current phase: {phase}. "

        if requirement:
            base += f"Requirement ID: {requirement.id}. Status: {requirement.status}. "
            if requirement.knowledge_base_id:
                base += f"Knowledge base ID: {requirement.knowledge_base_id}. "

            # 注入已保存的测试环境配置，确保 agent 知道 URL/登录态/凭据
            env_info = self._get_environment_info(requirement)
            if env_info:
                base += env_info

        if phase == "parsing":
            base += (
                "Your task is to understand the user's testing needs. "
                "IMPORTANT: You are analyzing the SYSTEM/FEATURES described in the user's input, "
                "NOT the document/URL itself. If the user provides a document link, extract its "
                "content and base your analysis on what the document DESCRIBES (the business system), "
                "not on 'document parsing'. "
                "Use search_knowledge_base to find relevant documentation. "
                "If information is insufficient, use ask_user to clarify. "
                "When you have enough information, produce a structured requirement."
            )
        elif phase == "exploring":
            base += (
                "Your task is to open the target application in the browser and explore its UI. "
                "Use browser_navigate to open the test URL. "
                "Use browser_snapshot to capture real DOM elements with their selectors. "
                "Click through key flows and document every interactive element. "
                "Produce a page_map artifact with accurate, real CSS selectors — do NOT guess. "
                "If the site redirects to a login page, document the login form elements."
            )
        elif phase == "designing_cases":
            base += (
                "Your task is to design detailed test cases based on the user's requirements. "
                "Focus on the specific requirement content, not knowledge base patterns. "
                "Use search_knowledge_base only as supplementary reference. "
                "Use find_reusable_suites to check for existing suites. "
                "Ask the user if you need clarification on test scope or priorities."
            )
        elif phase == "generating_code":
            base += (
                "Your task is to generate executable test scripts (pytest/Playwright) "
                "based on the test cases and the page_map (real DOM selectors). "
                "Use get_requirement_environment first to check for saved URLs/credentials. "
                "Use search_knowledge_base only for supplementary API specs. "
                "Only ask the user for URLs or credentials if get_requirement_environment returns empty."
            )
        elif phase == "executing":
            base += (
                "Your task is to execute tests and report results. "
                "Use get_requirement_environment first to check for saved config. "
                "Use read_workspace_file to examine generated scripts. "
                "Only ask the user for login credentials or environment config if get_requirement_environment returns empty."
            )
        elif phase == "reviewing":
            base += (
                "Your task is to review code changes for security and quality issues. "
                "Use search_knowledge_base for coding standards. "
                "Use read_workspace_file to examine the full source."
            )

        return base

    # ------------------------------------------------------------------
    # Environment helpers
    # ------------------------------------------------------------------

    def _get_environment_info(self, requirement: Requirement) -> str:
        """Extract saved environment config from the requirement for agent prompts."""
        progress = requirement.execution_progress or {}
        structured = requirement.structured_data or {}

        env = {}
        if isinstance(structured, dict):
            env.update(structured.get("test_environment") or {})
        if isinstance(progress, dict):
            env.update(progress.get("test_environment") or {})

        parts = []
        if env.get("test_url"):
            parts.append(f"Test URL: {env['test_url']}")
        if env.get("login_state"):
            parts.append(f"Login state: {env['login_state']}")
        if env.get("credential_ref"):
            parts.append(f"Credential: {env['credential_ref']}")
        if env.get("allow_explore") is not None:
            parts.append(f"Allow explore: {env['allow_explore']}")

        if parts:
            return "Environment config: " + "; ".join(parts) + ". "
        return ""

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def _auto_run_agent(
        self,
        conversation_id: int,
        requirement: Requirement,
        phase: str,
        agent_type: str,
    ) -> Generator[Dict[str, Any], None, None]:
        """Run the next agent automatically (without user prompt)."""
        agent = self._agents.get(agent_type)
        if not agent:
            return

        history = self._load_conversation_history(conversation_id)
        system_instruction = self._build_system_instruction(phase, requirement)

        # Add a synthetic prompt to kick off the next agent
        prompt_map = {
            "browser_agent": "Please explore the target application and produce a complete page map with real CSS selectors.",
            "case_agent": "Please design test cases based on the structured requirement and page map above.",
            "code_agent": "Please generate test scripts based on the test cases above. Use the page map selectors for Playwright locators — do NOT guess selectors.",
            "exec_agent": "Please execute the generated test scripts and report results.",
            "review_agent": "Please review the code changes.",
        }
        synthetic_prompt = prompt_map.get(agent_type, "Please proceed with your task.")
        history.append({"role": "user", "content": synthetic_prompt})

        agent_gen = agent.act(history, system_instruction)
        self._active_generators[requirement.id] = agent_gen

        for event in agent_gen:
            if event.get("type") == "message" and event.get("complete"):
                self._save_agent_message(conversation_id, agent_type, event["content"])

            if event.get("type") == "question":
                self._handle_question(requirement, phase, agent_type, history, event)
                yield event
                yield {"type": "done"}
                return

            if event.get("type") == "artifact":
                self._handle_artifact(requirement, event["key"], event["data"], conversation_id)
                yield event

            yield event

        self._active_generators.pop(requirement.id, None)
        yield {"type": "done"}

    def _resume_agent(
        self, requirement_id: int, user_response: str
    ) -> Generator[Dict[str, Any], None, None]:
        """Resume a paused agent with the user's response."""
        agent_gen = self._active_generators.get(requirement_id)
        if not agent_gen:
            yield {"type": "error", "message": "No active agent to resume"}
            return

        # Clear waiting_user event
        db.session.execute(
            db.delete(AgentEvent).where(
                AgentEvent.requirement_id == requirement_id,
                AgentEvent.event_type == "waiting_user",
            )
        )
        db.session.commit()

        requirement = db.session.get(Requirement, requirement_id)
        if requirement:
            requirement.current_phase = ""

        # Send the user's response into the generator
        try:
            agent_gen.send(user_response)
        except StopIteration:
            logger.info("Agent generator completed after resume")
            self._active_generators.pop(requirement_id, None)
            yield {"type": "done"}
            return

        # Continue consuming events from the resumed generator
        for event in agent_gen:
            if event.get("type") == "message" and event.get("complete"):
                self._save_agent_message(
                    self._get_conversation_id(requirement_id),
                    "",
                    event["content"],
                )

            if event.get("type") == "question":
                self._handle_question(requirement, "", "", [], event)
                yield event
                yield {"type": "done"}
                return

            if event.get("type") == "artifact":
                self._handle_artifact(
                    requirement,
                    event["key"],
                    event["data"],
                    self._get_conversation_id(requirement_id),
                )
                yield event

            yield event

        self._active_generators.pop(requirement_id, None)
        yield {"type": "done"}

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_question(
        self,
        requirement: Optional[Requirement],
        phase: str,
        agent_type: str,
        history: List[Dict],
        event: Dict,
    ):
        """Save checkpoint and emit waiting_user when agent asks a question."""
        if not requirement:
            logger.warning("Question from agent but no requirement to save checkpoint")
            return

        from service.checkpoint_service import save_checkpoint
        from service.agent_event_service import emit_agent_event

        requirement.current_phase = "clarifying"
        save_checkpoint(requirement.id, phase, agent_type, history)

        emit_agent_event(
            requirement.id,
            agent_type,
            "waiting_user",
            f"等待用户回复: {event.get('question', '')}",
            {"question": event.get("question"), "context": event.get("context")},
        )

    def _handle_artifact(
        self,
        requirement: Optional[Requirement],
        artifact_key: str,
        artifact_data: Dict,
        conversation_id: int,
    ):
        """Persist an artifact and update requirement status."""
        if not requirement:
            return

        from service.agent_event_service import emit_agent_event

        # Update requirement status
        new_status = ARTIFACT_STATUS_MAP.get(artifact_key)
        if new_status:
            requirement.status = new_status
            db.session.commit()
            emit_agent_event(
                requirement.id,
                "",
                "artifact",
                f"Produced artifact: {artifact_key}",
                {"artifact_key": artifact_key, "status": new_status},
            )

    def _save_agent_message(
        self, conversation_id: int, agent_type: str, content: str
    ):
        """Persist an agent message to the database."""
        if not conversation_id:
            return
        try:
            msg = Message(
                conversation_id=conversation_id,
                sender=agent_type or "router",
                content=content,
                agent_type=agent_type or "router",
            )
            db.session.add(msg)
            db.session.commit()
        except Exception as exc:
            logger.error("Failed to save agent message: %s", exc)
            db.session.rollback()

    def _get_conversation_id(self, requirement_id: int) -> Optional[int]:
        """Get the conversation ID for a requirement."""
        conversation = Conversation.query.filter_by(
            requirement_id=requirement_id
        ).first()
        return conversation.id if conversation else None


# Singleton
_orchestrator: Optional[ConversationOrchestrator] = None


def get_orchestrator() -> ConversationOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ConversationOrchestrator()
    return _orchestrator


def process_user_message_flow(
    conversation_id: int, user_message: str
) -> Generator[Dict[str, Any], None, None]:
    """Entry point for API routes — returns a generator of SSE events."""
    orchestrator = get_orchestrator()
    yield from orchestrator.handle_message(conversation_id, user_message)
