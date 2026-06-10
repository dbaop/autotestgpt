"""
Tool-capable agent base class.

Extends BaseAgent with a tool-calling loop. Agents can call tools during
their reasoning process, and the tool results are fed back to the LLM.
The act() method is a generator that yields events for SSE streaming.
"""

import json
import logging
import re
from typing import Any, Callable, Dict, Generator, List, Optional

from .base_agent import BaseAgent
from .tools import (
    execute_tool,
    format_tools_prompt,
    get_tools_for_agent,
)

logger = logging.getLogger(__name__)


class ToolCapableAgent(BaseAgent):
    """Agent with tool-calling capability.

    Extends BaseAgent with:
      - act() generator method for multi-step reasoning with tools
      - Tool registration via self.tools dict
      - Configurable max_tool_rounds to prevent infinite loops
      - Checkpoint support for pause/resume across ask_user
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_tool_rounds = 5
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Populate self._tools from AGENT_TOOLS registry based on agent_type."""
        if self.agent_type:
            self._tools = get_tools_for_agent(self.agent_type)

    def register_tool(self, name: str, func: Callable, description: str,
                      parameters: Dict[str, Any]):
        """Register a custom tool for this agent instance."""
        self._tools[name] = {
            "function": func,
            "description": description,
            "parameters": parameters,
        }

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # act() — generator-based agent loop
    # ------------------------------------------------------------------

    def act(
        self,
        conversation_messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Generator[Dict[str, Any], Optional[str], None]:
        """Run the agent's reasoning loop with tool access.

        Yields events:
          {"type": "message", "content": "...", "chunk": true}  — streaming token
          {"type": "message", "content": "...", "complete": true} — finalized message
          {"type": "tool_call", "name": "...", "arguments": {...}}
          {"type": "tool_result", "name": "...", "result": ...}
          {"type": "question", "question": "...", "context": "..."}
          {"type": "artifact", "key": "...", "data": {...}}
          {"type": "error", "message": "..."}
          {"type": "done"}

        When the agent calls ask_user, the generator yields {"type": "question", ...}
        and then yields {"type": "done"}.  The orchestrator saves the checkpoint
        and resumes by sending the user's response into the generator when they reply.

        Args:
            conversation_messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
            system_instruction: System prompt for this turn

        Yields:
            Event dicts as described above.
        """
        # Build full message list for LLM
        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(conversation_messages[-30:])  # limit context

        full_response = ""
        rounds = 0

        while rounds < self.max_tool_rounds:
            rounds += 1

            # Stream the LLM response
            raw_response = ""
            for chunk_text in self._call_llm_stream(messages):
                raw_response += chunk_text
                yield {"type": "message", "content": chunk_text, "chunk": True}

            yield {"type": "message", "content": raw_response, "complete": True}
            full_response += raw_response

            # Check for tool call in the response
            tool_call = self._parse_tool_call(raw_response)

            if tool_call is None:
                # No tool call — agent is done with this turn
                # Check if the response contains an artifact
                artifact = self._try_extract_artifact(full_response)
                if artifact:
                    yield {"type": "artifact", "key": artifact["key"], "data": artifact["data"]}
                yield {"type": "done"}
                return

            tool_name = tool_call["tool"]
            tool_args = tool_call.get("arguments", {})

            yield {"type": "tool_call", "name": tool_name, "arguments": tool_args}

            # Execute the tool
            try:
                result = execute_tool(tool_name, tool_args)
            except Exception as exc:
                logger.error("Tool %s failed: %s", tool_name, exc)
                yield {"type": "tool_result", "name": tool_name,
                       "result": {"error": str(exc)}}
                # Feed error back to LLM
                messages.append({"role": "assistant", "content": raw_response})
                messages.append({"role": "user", "content": f"[Tool result for {tool_name}]: Error: {exc}"})
                continue

            # Handle ask_user sentinel
            if isinstance(result, dict) and result.get("__tool_type__") == "ask_user":
                yield {
                    "type": "question",
                    "question": result["question"],
                    "context": result.get("context", ""),
                }
                yield {"type": "done"}
                return

            # Feed tool result back to LLM
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            yield {"type": "tool_result", "name": tool_name, "result": result}
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({
                "role": "user",
                "content": f"[Tool result for {tool_name}]:\n{result_str}",
            })
            full_response = ""  # reset for next round

        # Hit max rounds — yield what we have
        logger.warning("Agent %s hit max_tool_rounds (%d)", self.agent_type, self.max_tool_rounds)
        yield {"type": "done"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call_llm_stream(self, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        """Stream LLM response using the base class method."""
        yield from super().call_llm_stream(messages)

    def _parse_tool_call(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract a tool call JSON block from the LLM response."""
        # Pattern: {"tool": "name", "arguments": {...}}
        pattern = r'\{[^{}]*"tool"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})\s*\}'
        match = re.search(pattern, response, re.DOTALL)
        if match:
            tool_name = match.group(1)
            try:
                arguments = json.loads(match.group(2))
            except json.JSONDecodeError:
                arguments = {}
            return {"tool": tool_name, "arguments": arguments}

        # Also try ```json ... ``` wrapper
        fenced = re.search(r'```json\s*(\{.*?"tool".*?\})\s*```', response, re.DOTALL)
        if fenced:
            try:
                data = json.loads(fenced.group(1))
                if "tool" in data:
                    return data
            except json.JSONDecodeError:
                pass

        return None

    def _try_extract_artifact(self, response: str) -> Optional[Dict[str, Any]]:
        """Try to extract a structured artifact from the agent's final response.

        Each agent subclass can override this or use a convention.
        Default: look for a complete JSON object with known keys.
        """
        return None

    # ------------------------------------------------------------------
    # Keep process() for backward compatibility
    # ------------------------------------------------------------------

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Backward-compatible process() that wraps act().

        Collects the final result from the generator.
        Subclasses that override act() do NOT need to override process().
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement process() "
            f"or use the ToolCapableAgent.act() generator."
        )
