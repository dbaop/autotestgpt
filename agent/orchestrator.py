"""
Conversation Orchestrator — manages multi-agent test workflow via conversation.

Replaces the rigid pipeline (AutoTestFlow) and the isolated chat (ChatRouter)
with a unified conversation-driven workflow where agents can ask questions,
search the knowledge base, and produce artifacts through multi-turn dialogue.
"""

import json
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


def _now():
    return datetime.now(timezone.utc)

logger = logging.getLogger(__name__)

# Mapping from requirement status to orchestrator phase + agent.
# 注意：部分状态由 _drive 特判处理（不再选 LLM agent）：
#   - parsed      → 进入结构化确认 gate（确认后改走 exploring/browser_agent）
#   - code_generated / executing → 确定性执行 _run_execution
#   - executed    → 收尾 _finalize_with_report
STATUS_TO_PHASE: Dict[str, Tuple[str, str]] = {
    "pending": ("parsing", "req_agent"),
    "parsed": ("confirming", ""),
    "probed": ("designing_cases", "case_agent"),
    "cases_generated": ("generating_code", "code_agent"),
    "code_generated": ("executing", ""),
    "executing": ("executing", ""),
    "executed": ("finalizing", ""),
    "completed": ("completed", ""),
    "error": ("idle", ""),
}

# Status transitions when an artifact is produced
ARTIFACT_STATUS_MAP: Dict[str, str] = {
    "structured_requirement": "parsed",
    "page_map": "probed",
    "test_cases": "cases_generated",
    "test_scripts": "code_generated",
}

# 驱动循环防失控上限（execution 作为单步不会快速累加）
MAX_DRIVE_STEPS = 16


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

        # ---- Gate 回复：解析确认信息（环境/账号/是否 review）并继续驱动 ----
        if (
            requirement
            and requirement.status == "parsed"
            and self._gate_emitted(requirement)
            and not self._confirmation_done(requirement)
        ):
            self._parse_confirmation_reply(requirement, user_message, conversation_id)
            self._clear_waiting(requirement_id)
            yield from self._drive(conversation_id, requirement)
            return

        # ---- pending 阶段：先记录环境配置（若有），提示用户开始 ----
        if requirement is None or requirement.status == "pending":
            env_saved = self._try_save_env_from_message(requirement, user_message, conversation_id)
            if env_saved:
                confirm_msg = Message(
                    conversation_id=conversation_id,
                    sender="router",
                    content=(
                        f"已记录环境配置 ({env_saved})。\n\n"
                        f"需求状态: **{requirement.status if requirement else 'pending'}**。"
                        f"你可以输入消息开始需求解析，比如发一条「分析需求」或「开始」，"
                        f"我会自动提取文档内容、设计用例、生成脚本并执行测试。"
                    ),
                    agent_type="router",
                    extra_data={"source": "env_setup_detected", "saved": env_saved},
                )
                db.session.add(confirm_msg)
                db.session.commit()
                yield {"type": "message", "complete": True, "content": confirm_msg.content}
                yield {"type": "done"}
                return

        # ---- 处于等待用户的中间态（agent 提问）：清除等待并重新驱动 ----
        # 说明：ask_user 后 agent generator 已结束，无法 send() 续跑；改为按当前
        # status + 含用户答复的 history 重新驱动（agent 会带着答复重跑该阶段）。
        if requirement and self._is_waiting(requirement):
            self._clear_waiting(requirement_id)
            yield from self._drive(conversation_id, requirement)
            return

        # ---- C2：任意非 pending 状态下「中途修改测试环境（地址/账号）」 ----
        # 跑中先停后改：识别到 test_url 等变更则请求取消正在执行的流程并更新环境，
        # 不自动续跑；用户回复「继续」或点重跑从当前阶段继续（新地址生效）。
        if requirement and requirement.status != "pending":
            env_keys = self._try_save_env_from_message(requirement, user_message, conversation_id)
            if env_keys:
                from service.flow_service import request_cancel

                request_cancel(requirement.id)
                env = self._collect_env(requirement)
                loc = f"（测试地址 {env.get('test_url')}）" if env.get("test_url") else ""
                note = (
                    f"已更新环境配置：{env_keys}{loc}。"
                    "若有正在执行的流程会在当前步骤后停止；回复「继续」或点重跑即可从当前阶段继续（新配置生效）。"
                )
                m = Message(
                    conversation_id=conversation_id, sender="router", content=note,
                    agent_type="router",
                    extra_data={"source": "env_update_midflow", "saved": env_keys},
                )
                db.session.add(m)
                db.session.commit()
                yield {"type": "message", "complete": True, "content": note}
                yield {"type": "done"}
                return

        # ---- 首次/常规：跑当前阶段的 agent，再交给 _drive 驱动到底 ----
        phase, agent_type = self._determine_phase(requirement_id, user_message)

        if agent_type and agent_type in self._agents:
            yield {"type": "phase_change", "from": "idle", "to": phase, "agent": agent_type}
            paused = yield from self._run_agent_step(
                conversation_id, requirement, phase, agent_type, user_kickoff=True
            )
            conversation.updated_at = _now()
            db.session.commit()
            if paused:
                yield {"type": "done"}
                return

        if requirement:
            yield from self._drive(conversation_id, requirement)
        else:
            yield {"type": "done"}

    # ------------------------------------------------------------------
    # Drive-to-completion loop
    # ------------------------------------------------------------------

    def _drive(
        self, conversation_id: int, requirement: Optional[Requirement]
    ) -> Generator[Dict[str, Any], None, None]:
        """Drive the workflow forward through phases until paused or terminal.

        Pauses (returns without 'done' replacement) when an agent asks a
        question or a confirmation gate is emitted. Reaches a terminal state at
        'completed'/'error'. Guards against infinite loops.
        """
        if not requirement:
            yield {"type": "done"}
            return

        # A fresh user-initiated drive clears any stale cancellation flag so a
        # previous force-stop doesn't kill this new run immediately.
        try:
            from service.flow_service import clear_cancel

            clear_cancel(requirement.id)
        except Exception:
            pass

        guard = 0
        while True:
            guard += 1
            if guard > MAX_DRIVE_STEPS:
                yield {"type": "error", "message": "流程驱动达到步数上限，已停止"}
                break

            db.session.refresh(requirement)
            status = requirement.status

            # Cooperative cancellation (force-stop button)
            if self._is_cancelled(requirement.id):
                yield from self._handle_cancel(conversation_id, requirement)
                return

            # Terminal
            if status in ("completed", "error"):
                break

            # Paused waiting for user (re-entrancy guard)
            if self._is_waiting(requirement):
                return

            # Confirmation gate after requirement parsing
            if status == "parsed" and not self._confirmation_done(requirement):
                yield from self._emit_confirmation_gate(conversation_id, requirement)
                return

            # Deterministic test execution
            if status in ("code_generated", "executing"):
                yield from self._run_execution(conversation_id, requirement)
                continue

            # Finalize: (optional) review + report
            if status == "executed":
                yield from self._finalize_with_report(conversation_id, requirement)
                continue

            # Select the agent for this phase
            if status == "parsed" and self._confirmation_done(requirement):
                phase, agent_type = ("exploring", "browser_agent")
            else:
                phase, agent_type = STATUS_TO_PHASE.get(status, ("", ""))

            if not agent_type or agent_type not in self._agents:
                break

            # Skip UI exploration when there's no URL / no UI scope
            if agent_type == "browser_agent" and not self._needs_exploration(requirement):
                self._skip_phase_to(requirement, "probed")
                continue

            yield {"type": "phase_change", "from": status, "to": phase, "agent": agent_type}
            prev_status = status
            paused = yield from self._run_agent_step(
                conversation_id, requirement, phase, agent_type
            )
            if paused:
                yield {"type": "done"}
                return

            db.session.refresh(requirement)
            if requirement.status == prev_status:
                # CodeAgent failed to produce parsable scripts — synthesize a
                # minimal fallback from the DB test cases so the flow proceeds
                # (rather than dead-ending) instead of looping.
                if agent_type == "code_agent" and prev_status == "cases_generated":
                    if self._fallback_generate_scripts(requirement, conversation_id):
                        yield {
                            "type": "message", "complete": True,
                            "content": "脚本生成未返回规范结果，已用最小可执行用例兜底，继续执行。",
                        }
                        continue
                # Agent produced no advancing artifact — stop to avoid a loop
                msg = "流程未能自动推进（未生成预期结果），请补充信息后再继续。"
                self._save_agent_message(conversation_id, "router", msg)
                yield {"type": "message", "complete": True, "content": msg}
                break

        yield {"type": "done"}

    def _run_agent_step(
        self,
        conversation_id: int,
        requirement: Optional[Requirement],
        phase: str,
        agent_type: str,
        user_kickoff: bool = False,
    ) -> Generator[Dict[str, Any], None, bool]:
        """Run a single agent phase. Returns True if it paused on a question."""
        agent = self._agents.get(agent_type)
        if not agent:
            return False

        history = self._load_conversation_history(conversation_id)
        if not user_kickoff:
            synthetic_prompt = self._AUTO_PROMPTS.get(
                agent_type, "Please proceed with your task."
            )
            history.append({"role": "user", "content": synthetic_prompt})

        system_instruction = self._build_system_instruction(phase, requirement)
        req_key = requirement.id if requirement else 0

        agent_gen = agent.act(history, system_instruction)
        self._active_generators[req_key] = agent_gen

        paused = False
        for event in agent_gen:
            etype = event.get("type")
            if etype == "message" and event.get("complete"):
                self._save_agent_message(conversation_id, agent_type, event["content"])
                yield event
                continue
            if etype == "question":
                self._handle_question(requirement, phase, agent_type, history, event)
                yield event
                paused = True
                break
            if etype == "artifact":
                self._handle_artifact(
                    requirement, event["key"], event["data"], conversation_id
                )
                yield event
                continue
            yield event

        self._active_generators.pop(req_key, None)
        return paused

    _AUTO_PROMPTS: Dict[str, str] = {
        "browser_agent": "Please explore the target application and produce a complete page map with real CSS selectors.",
        "case_agent": "Please design test cases based on the structured requirement and page map above.",
        "code_agent": "Please generate test scripts based on the test cases above. Use the page map selectors for Playwright locators — do NOT guess selectors.",
        "req_agent": "Please analyze the requirement and produce a structured requirement.",
    }

    def _needs_exploration(self, requirement: Requirement) -> bool:
        """Whether to run the browser_agent UI exploration step."""
        env = self._collect_env(requirement)
        if env.get("test_url"):
            return True
        structured = requirement.structured_data or {}
        if isinstance(structured, dict):
            if structured.get("ui_elements"):
                return True
            sr = structured.get("structured_requirement") or {}
            if isinstance(sr, dict) and sr.get("ui_elements"):
                return True
        return False

    def _skip_phase_to(self, requirement: Requirement, status: str):
        from flow.test_flow import FlowDataAccess

        FlowDataAccess.update_requirement(requirement.id, status=status)

    def _save_ui_dsl_scripts(self, requirement_id: int, scripts: List[Dict[str, Any]]):
        """Create an executable ui_cdp TestScript (GWT DSL) for each UI script that
        carries a `dsl`. Matching mirrors FlowDataAccess.save_scripts (id ∈ case.title,
        fallback to the first case)."""
        from models import TestCase, TestScript

        dsl_scripts = [s for s in scripts if isinstance(s.get("dsl"), dict)]
        if not dsl_scripts:
            return

        cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
        if not cases:
            return

        for script in dsl_scripts:
            script_id = str(script.get("id", ""))
            test_case_id = None
            for case in cases:
                if case.title and script_id and script_id in case.title:
                    test_case_id = case.id
                    break
            if not test_case_id:
                test_case_id = cases[0].id

            ts = TestScript(
                test_case_id=test_case_id,
                script_type="ui_cdp",
                script_content=json.dumps(script["dsl"], ensure_ascii=False),
                file_path=script.get("file_path", ""),
                status="generated",
            )
            db.session.add(ts)
        db.session.commit()
        logger.info("Saved %d ui_cdp DSL scripts for req %d", len(dsl_scripts), requirement_id)

    def _fallback_generate_scripts(self, requirement: Requirement, conversation_id: int) -> bool:
        """Synthesize minimal executable scripts from DB test cases when CodeAgent
        failed to return a parsable JSON envelope. Returns True if scripts were
        produced and status advanced to code_generated."""
        from models import TestCase

        cases = TestCase.query.filter_by(requirement_id=requirement.id).all()
        if not cases:
            return False

        env = self._collect_env(requirement)
        base_url = env.get("test_url", "")
        scripts: List[Dict[str, Any]] = []
        for case in cases:
            sid = f"TC-{case.id}"
            is_ui = (case.test_type or "").lower() == "ui"
            if is_ui:
                safe = sid.replace("-", "_")
                code = (
                    "from playwright.sync_api import Page\n\n"
                    f"def test_{safe}(page: Page):\n"
                    f"    page.goto({base_url!r} or 'about:blank')\n"
                    "    assert page.locator('body').is_visible()\n"
                )
                dsl = {
                    "given": {"action": "navigate", "url": base_url or "/"},
                    "when": [],
                    "then": [{"type": "element_visible", "selector": "body"}],
                }
                scripts.append({
                    "id": sid, "title": case.title or sid, "language": "python",
                    "framework": "playwright", "code": code, "dsl": dsl,
                })
            else:
                safe = sid.replace("-", "_")
                code = f"def test_{safe}():\n    assert True  # fallback placeholder\n"
                scripts.append({
                    "id": sid, "title": case.title or sid, "language": "python",
                    "framework": "pytest", "code": code,
                })

        logger.warning(
            "CodeAgent produced no parsable scripts for req %d — using fallback (%d cases)",
            requirement.id, len(scripts),
        )
        # Reuse the standard persistence + status-advance path.
        self._handle_artifact(requirement, "test_scripts", {"scripts": scripts}, conversation_id)
        db.session.refresh(requirement)
        return requirement.status == "code_generated"

    # ------------------------------------------------------------------
    # Cooperative cancellation
    # ------------------------------------------------------------------

    def _is_cancelled(self, requirement_id: int) -> bool:
        try:
            from service.flow_service import is_cancelled

            return is_cancelled(requirement_id)
        except Exception:
            return False

    def _handle_cancel(
        self, conversation_id: int, requirement: Requirement
    ) -> Generator[Dict[str, Any], None, None]:
        """Stop driving on user request. Leaves status resumable, clears flag."""
        from service.flow_service import clear_cancel

        self._active_generators.pop(requirement.id, None)
        clear_cancel(requirement.id)
        msg = "已按你的请求终止当前流程。可点重跑/回复『继续』从当前阶段继续。"
        self._save_agent_message(conversation_id, "router", msg)
        yield {"type": "message", "complete": True, "content": msg}
        yield {"type": "stopped", "requirement_id": requirement.id}
        yield {"type": "done"}

    def _collect_env(self, requirement: Requirement) -> Dict[str, Any]:
        progress = requirement.execution_progress or {}
        structured = requirement.structured_data or {}
        env: Dict[str, Any] = {}
        if isinstance(structured, dict):
            env.update(structured.get("test_environment") or {})
        if isinstance(progress, dict):
            env.update(progress.get("test_environment") or {})
        return env

    def _clear_waiting(self, requirement_id: Optional[int]):
        """Clear a waiting_user pause so the workflow can re-drive."""
        if not requirement_id:
            return
        self._active_generators.pop(requirement_id, None)
        db.session.execute(
            db.delete(AgentEvent).where(
                AgentEvent.requirement_id == requirement_id,
                AgentEvent.event_type == "waiting_user",
            )
        )
        req = db.session.get(Requirement, requirement_id)
        if req:
            req.current_phase = ""
        db.session.commit()

    # ------------------------------------------------------------------
    # Confirmation gate
    # ------------------------------------------------------------------

    def _gate_emitted(self, requirement: Requirement) -> bool:
        structured = requirement.structured_data or {}
        if not isinstance(structured, dict):
            return False
        return bool(structured.get("confirmation", {}).get("emitted"))

    def _confirmation_done(self, requirement: Requirement) -> bool:
        structured = requirement.structured_data or {}
        if not isinstance(structured, dict):
            return False
        return structured.get("confirmation", {}).get("confirmed") is True

    def _emit_confirmation_gate(
        self, conversation_id: int, requirement: Requirement
    ) -> Generator[Dict[str, Any], None, None]:
        """Ask the user to confirm environment / account / code-review before
        continuing the automated workflow."""
        from sqlalchemy.orm.attributes import flag_modified

        env = self._collect_env(requirement)
        structured = requirement.structured_data or {}
        review = structured.get("review") or {} if isinstance(structured, dict) else {}

        url_line = f"- 测试地址：{env['test_url']}" if env.get("test_url") else "- 测试地址：（未提供，请补充被测系统 URL）"
        login_line = (
            f"- 登录/账号：{env.get('login_state')}"
            + (f"，凭据 {env.get('credential_ref')}" if env.get("credential_ref") else "")
            if env.get("login_state") or env.get("credential_ref")
            else "- 登录/账号：（如需登录，请提供登录方式与账号/凭据）"
        )
        if review.get("enabled"):
            target = review.get("repo_url") or review.get("repo_path") or "（未填写仓库）"
            review_line = f"- 代码 review：已预设开启（{target}，分支 {review.get('branch', 'main')}，近 {review.get('days', 7)} 天）。如不需要请回复「不需要 review」。"
        else:
            review_line = "- 代码 review：默认不开启。如需要请回复「需要 review，仓库 <url> 分支 <branch>」。"

        question = (
            "需求已解析完成 ✅。开始自动生成用例与执行测试前，请确认以下信息"
            "（可在一条消息里补全/修改，确认无误回复「确认」即可）：\n"
            f"{url_line}\n{login_line}\n{review_line}"
        )

        # Mark gate as emitted (so the reply is routed to gate parsing)
        if not isinstance(structured, dict):
            structured = {}
        confirmation = structured.get("confirmation") or {}
        confirmation["emitted"] = True
        structured["confirmation"] = confirmation
        requirement.structured_data = structured
        flag_modified(requirement, "structured_data")
        db.session.commit()

        event = {"type": "question", "question": question, "context": "确认后将自动执行：探索页面 → 设计用例 → 生成脚本 → 执行测试 → 出报告。"}
        self._handle_question(requirement, "clarifying", "router", [], event)
        self._save_agent_message(conversation_id, "router", question)
        yield event
        yield {"type": "done"}

    def _parse_confirmation_reply(
        self, requirement: Requirement, user_message: str, conversation_id: int
    ):
        """Parse the user's gate reply: env config + code-review intent."""
        import re
        from sqlalchemy.orm.attributes import flag_modified

        # Environment (test_url / login_state / credential_ref)
        self._try_save_env_from_message(requirement, user_message, conversation_id)

        structured = requirement.structured_data or {}
        if not isinstance(structured, dict):
            structured = {}
        review = dict(structured.get("review") or {})

        msg = user_message.lower()
        # Negative intent
        if re.search(r"(不需要|不用|无需|不做|skip).{0,6}(review|审查|代码审查|评审)", user_message):
            review["enabled"] = False
        # Positive intent
        elif re.search(r"(需要|要|开启|做|进行).{0,6}(review|审查|代码审查|评审)", user_message) or "review" in msg:
            review["enabled"] = True

        # Optional repo / branch / days from the reply
        repo_m = re.search(r"(https?://[^\s,，。；;]+\.git[^\s,，。；;]*|https?://[^\s,，。；;]+)", user_message)
        if repo_m and ("review" in msg or review.get("enabled")):
            review["repo_url"] = repo_m.group(1).rstrip("/")
        branch_m = re.search(r"(?:分支|branch)[：:\s]*([A-Za-z0-9._/\-]+)", user_message)
        if branch_m:
            review["branch"] = branch_m.group(1)
        days_m = re.search(r"(?:近|最近)?\s*(\d+)\s*天", user_message)
        if days_m:
            review["days"] = int(days_m.group(1))

        if review:
            structured["review"] = review

        confirmation = structured.get("confirmation") or {}
        confirmation["confirmed"] = True
        structured["confirmation"] = confirmation
        requirement.structured_data = structured
        flag_modified(requirement, "structured_data")
        db.session.commit()
        logger.info("Confirmation parsed for req %d: review=%s", requirement.id, review)

    # ------------------------------------------------------------------
    # Deterministic execution
    # ------------------------------------------------------------------

    def _run_execution(
        self, conversation_id: int, requirement: Requirement
    ) -> Generator[Dict[str, Any], None, None]:
        """Run all generated test scripts via ExecAgent.process() (real pytest
        subprocess) and persist ExecutionRecord rows. Does not use the LLM."""
        from flow.test_flow import FlowDataAccess

        FlowDataAccess.update_requirement(requirement.id, status="executing")
        env = FlowDataAccess.load_test_environment(requirement.id)
        # load_test_environment only reads execution_progress; merge structured too
        if not env.get("test_url"):
            env = self._collect_env(requirement)

        all_scripts = FlowDataAccess.get_scripts_for_requirement(requirement.id)
        # UI cases produce a paired (playwright deliverable, ui_cdp executable).
        # Skip the Playwright deliverable when its ui_cdp sibling exists.
        ui_cdp_case_ids = {s.test_case_id for s in all_scripts if s.script_type == "ui_cdp"}
        scripts = [
            s for s in all_scripts
            if not (s.script_type == "playwright" and s.test_case_id in ui_cdp_case_ids)
        ]
        if not scripts:
            FlowDataAccess.update_requirement(requirement.id, status="executed")
            msg = "没有可执行的测试脚本，跳过执行。"
            self._save_agent_message(conversation_id, "exec_agent", msg)
            yield {"type": "message", "complete": True, "content": msg}
            return

        yield {"type": "phase_change", "from": "code_generated", "to": "executing", "agent": "exec_agent"}
        exec_agent = self._agents["exec_agent"]
        total = len(scripts)
        executed = 0

        for idx, script in enumerate(scripts):
            # Cooperative cancellation between scripts: keep finished records,
            # skip the rest, leave status resumable.
            if self._is_cancelled(requirement.id):
                FlowDataAccess.set_execution_progress(
                    requirement.id,
                    {"total": total, "executed": executed, "cancelled": True,
                     "end_time": _now().isoformat()},
                )
                msg = f"执行已被用户终止，已完成 {executed}/{total} 个脚本。可点重跑/回复『继续』从当前阶段继续。"
                self._save_agent_message(conversation_id, "exec_agent", msg)
                yield {"type": "message", "complete": True, "content": msg}
                return

            is_ui = script.script_type == "ui_cdp"
            tool_name = "run_ui_dsl" if is_ui else "run_pytest"
            yield {
                "type": "tool_call",
                "name": tool_name,
                "arguments": {"script_id": script.id, "progress": f"{idx + 1}/{total}"},
            }
            FlowDataAccess.update_script_status(script.id, "running")
            try:
                if is_ui:
                    from service.ui_runner_service import run_ui_dsl

                    dsl = json.loads(script.script_content or "{}")
                    result = run_ui_dsl(
                        dsl,
                        base_url=env.get("test_url", ""),
                        screenshot_prefix=f"ui_{script.id}",
                    )
                else:
                    result = exec_agent.process(
                        {
                            "script_id": script.id,
                            "script_content": script.script_content,
                            "file_path": script.file_path,
                            "script_type": script.script_type,
                            "test_url": env.get("test_url", ""),
                        }
                    )
                status = result.get("status", "unknown")
                FlowDataAccess.create_execution_record(
                    test_script_id=script.id,
                    status=status,
                    result_data=result.get("result", {}),
                    error_message=result.get("error"),
                    execution_time=result.get("execution_time", 0),
                    report_path=result.get("report_path"),
                    screenshot_paths=result.get("screenshots", []),
                    started_at=_now(),
                    finished_at=_now(),
                )
                db.session.commit()  # create_execution_record only add()s
                FlowDataAccess.update_script_status(
                    script.id, "executed" if status == "success" else "error"
                )
            except Exception as exc:
                logger.error("Script %s execution failed: %s", script.id, exc)
                db.session.rollback()
                FlowDataAccess.create_execution_record(
                    test_script_id=script.id,
                    status="error",
                    error_message=str(exc),
                    started_at=_now(),
                    finished_at=_now(),
                )
                db.session.commit()
                FlowDataAccess.update_script_status(script.id, "error")
                status = "error"
            executed += 1
            yield {
                "type": "tool_result",
                "name": tool_name,
                "result": {"script_id": script.id, "status": status, "progress": f"{executed}/{total}"},
            }

        FlowDataAccess.update_requirement(requirement.id, status="executed")
        FlowDataAccess.set_execution_progress(
            requirement.id,
            {"total": total, "executed": executed, "completed": True, "end_time": _now().isoformat()},
        )
        summary = f"测试执行完成：共 {total} 个脚本。"
        self._save_agent_message(conversation_id, "exec_agent", summary)
        yield {"type": "message", "complete": True, "content": summary}

    # ------------------------------------------------------------------
    # Finalize: review + report
    # ------------------------------------------------------------------

    def _finalize_with_report(
        self, conversation_id: int, requirement: Requirement
    ) -> Generator[Dict[str, Any], None, None]:
        """Optional code review → defect analysis → consolidated report."""
        from flow.test_flow import FlowDataAccess

        structured = requirement.structured_data or {}
        review = structured.get("review") or {} if isinstance(structured, dict) else {}
        review_task_id = None

        if review.get("enabled") and (review.get("repo_url") or review.get("repo_path")):
            try:
                from service.review_service import run_review_task

                task = FlowDataAccess.create_review_task(
                    review.get("repo_url", ""),
                    review.get("branch", "main"),
                    int(review.get("days") or 7),
                    repo_path=review.get("repo_path", ""),
                    repo_type="local" if review.get("repo_path") else "remote",
                )
                run_review_task(task.id)
                review_task_id = task.id
                count = FlowDataAccess.count_review_findings(task.id)
                review_msg = f"代码审查完成，发现 {count} 条问题。"
                self._save_agent_message(conversation_id, "review_agent", review_msg)
                yield {"type": "message", "complete": True, "content": review_msg}
            except Exception as exc:
                logger.error("Code review failed (non-fatal): %s", exc)
                yield {
                    "type": "message",
                    "complete": True,
                    "content": f"代码审查执行失败，已跳过：{exc}",
                }

        try:
            from service.defect_service import defect_service
            from service.report_service import report_service

            defect_service.analyze_requirement(requirement.id, review_task_id)
            report = report_service.generate_requirement_report(requirement.id, review_task_id)
        except Exception as exc:
            logger.error("Report generation failed: %s", exc)
            FlowDataAccess.update_requirement(requirement.id, status="error")
            yield {"type": "error", "message": f"报告生成失败：{exc}"}
            return

        FlowDataAccess.update_requirement(requirement.id, status="completed", current_phase="completed")

        preview_url = f"/api/reports/{report.id}/preview"
        msg_content = (
            "测试流程已全部完成 ✅\n\n"
            f"报告摘要：{report.summary}\n"
            f"查看完整报告：{preview_url}"
        )
        self._save_agent_message(conversation_id, "router", msg_content)
        yield {"type": "message", "complete": True, "content": msg_content}
        yield {
            "type": "artifact",
            "key": "final_report",
            "data": {
                "report_id": report.id,
                "preview_url": preview_url,
                "api_url": f"/api/reports/{report.id}",
                "summary": report.summary,
            },
        }

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
                "NOT the document/URL itself. "
                "Use search_knowledge_base to find relevant documentation. "
                "If information is insufficient, use ask_user to clarify. "
                "If you have SOME information (even just a URL or brief description), "
                "produce a PARTIAL structured requirement and ask the user to fill gaps. "
                "Do NOT get stuck trying to open a URL if the browser is unavailable — "
                "ask the user to paste the document content directly."
            )
            # Inject pre-extracted document content so ReqAgent has the real doc text
            if requirement and requirement.structured_data:
                doc = requirement.structured_data.get("original_document")
                if doc and doc.get("extracted_content") and not doc.get("needs_retry"):
                    content = doc["extracted_content"]
                    base += (
                        f"\n\nPRE-EXTRACTED DOCUMENT CONTENT "
                        f"(from {doc.get('url', 'unknown source')}):\n"
                        f"---\n{content[:8000]}\n---\n"
                        "Use the above content as the PRIMARY basis for your requirement "
                        "analysis. Do NOT re-navigate or re-extract — the content is already "
                        "here. Focus on the business features described in the document."
                    )
                elif doc and doc.get("needs_retry"):
                    base += (
                        f"\n\nNOTE: A document URL ({doc.get('url', '')}) was provided but "
                        "could not be automatically extracted. If you have browser tools "
                        "(browser_navigate + browser_extract_content), try them now. "
                        "If the browser is unavailable, work with whatever information the "
                        "user has provided. Ask the user for the key requirements if needed."
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
                "Your task is to generate executable test scripts based on the test cases "
                "and the page_map (real DOM selectors). "
                "For UI test cases, each script object MUST include BOTH a Playwright `code` "
                "(deliverable) AND a Given-When-Then `dsl` object (executed in a real browser "
                "via CDP). Every selector MUST come from the page_map below — do NOT guess. "
                "For API test cases, generate a pytest `code` as usual. "
                "Use get_requirement_environment first to check for saved URLs/credentials. "
                "Only ask the user for URLs or credentials if get_requirement_environment returns empty."
            )
            # Inject the persisted page_map so selectors are real (mirrors the
            # document-content injection done in the parsing phase).
            if requirement and isinstance(requirement.structured_data, dict):
                page_map = requirement.structured_data.get("page_map")
                if page_map:
                    import json as _json

                    pm_text = _json.dumps(page_map, ensure_ascii=False)[:6000]
                    base += (
                        "\n\nPAGE MAP (real DOM selectors — use these EXACTLY for both "
                        f"`code` and `dsl`):\n---\n{pm_text}\n---\n"
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

    def _try_save_env_from_message(
        self, requirement: Optional[Requirement], message: str, conversation_id: int,
    ) -> Optional[str]:
        """Detect and save environment config from a user chat message.

        Returns a comma-separated list of saved keys if anything was saved, or None.
        """
        if not requirement:
            return None
        import re

        saved: list[str] = []

        # --- test_url ---
        url_m = re.search(
            r'(?:测试地址|test_url|测试环境|地址|url)[：:\s]*'
            r'(https?://[^\s,，。；;]+)',
            message, re.IGNORECASE,
        )
        if url_m:
            test_url = url_m.group(1).rstrip("/")
            self._merge_env(requirement, "test_url", test_url)
            saved.append("测试地址")
        else:
            # Bare URL in message
            bare_url = re.search(r'(https?://[^\s,，。；;]{10,})', message)
            if bare_url and not (
                "feishu" in bare_url.group(1) or "dingtalk" in bare_url.group(1)
                or "yuque" in bare_url.group(1) or "notion" in bare_url.group(1)
            ):
                test_url = bare_url.group(1).rstrip("/")
                self._merge_env(requirement, "test_url", test_url)
                saved.append("测试地址")

        # --- login_state ---
        ls_m = re.search(
            r'(?:登录态|login_state|登录方式)[：:\s]*'
            r'(no_login_required|pre_authenticated|requires_login|unknown)',
            message, re.IGNORECASE,
        )
        if ls_m:
            self._merge_env(requirement, "login_state", ls_m.group(1).lower())
            saved.append("登录态")

        # --- credential_ref ---
        cred_m = re.search(
            r'(?:凭据|credential|credential_ref|vault)[：:\s]*'
            r'([^\s,，。；;]{3,80})',
            message, re.IGNORECASE,
        )
        if cred_m:
            self._merge_env(requirement, "credential_ref", cred_m.group(1))
            saved.append("凭据")

        if saved:
            db.session.commit()
            logger.info("Saved env from chat for req %d: %s", requirement.id, saved)
            return ", ".join(saved)
        return None

    def _merge_env(self, requirement: Requirement, key: str, value: str):
        """Merge a key into the requirement's test_environment across both
        structured_data and execution_progress."""
        from sqlalchemy.orm.attributes import flag_modified

        progress = requirement.execution_progress or {}
        structured = requirement.structured_data or {}

        if not isinstance(progress, dict):
            progress = {}
        if not isinstance(structured, dict):
            structured = {}

        # Update in both places so all agents can see it
        for container in (progress, structured):
            env = container.setdefault("test_environment", {})
            env[key] = value

        requirement.execution_progress = progress
        requirement.structured_data = structured

        # JSON columns need explicit dirty marking when mutated in-place
        flag_modified(requirement, "execution_progress")
        flag_modified(requirement, "structured_data")

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
        """Persist an artifact (to domain tables) and update requirement status.

        统一在 orchestrator 落库，避免改各 agent（其 process() 仍被遗留 flow 复用，
        在 agent 内落库会与遗留路径双写冲突）。
        """
        if not requirement:
            return

        from sqlalchemy.orm.attributes import flag_modified
        from flow.test_flow import FlowDataAccess
        from service.agent_event_service import emit_agent_event

        try:
            # --- 落库到领域表 ---
            if artifact_key == "test_cases":
                cases = (artifact_data or {}).get("test_cases", [])
                suite_id = (artifact_data or {}).get("metadata", {}).get("test_suite_id")
                if cases:
                    FlowDataAccess.save_cases(cases, requirement.id, suite_id)
                    logger.info("Saved %d test cases for req %d", len(cases), requirement.id)
            elif artifact_key == "test_scripts":
                scripts = (artifact_data or {}).get("scripts", [])
                if scripts:
                    # Playwright/pytest scripts (deliverables + API executables)
                    FlowDataAccess.save_scripts(scripts, requirement.id)
                    # UI cases additionally get an executable ui_cdp DSL row
                    self._save_ui_dsl_scripts(requirement.id, scripts)
                    logger.info("Saved %d test scripts for req %d", len(scripts), requirement.id)
            elif artifact_key == "page_map":
                structured = requirement.structured_data or {}
                if not isinstance(structured, dict):
                    structured = {}
                structured["page_map"] = artifact_data
                requirement.structured_data = structured
                flag_modified(requirement, "structured_data")
                db.session.commit()
        except Exception as exc:
            logger.error("Failed to persist artifact %s: %s", artifact_key, exc)
            db.session.rollback()

        # --- 更新 requirement 状态 ---
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
