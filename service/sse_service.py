"""
Server-Sent Events (SSE) service for real-time agent streaming.

Provides per-conversation event queues and a Flask streaming response.
Events are pushed into queues by the orchestrator and consumed by the
frontend via EventSource connections.
"""

import json
import logging
import queue
import threading
from typing import Dict

from flask import Response, stream_with_context

logger = logging.getLogger(__name__)

# Per-connection event queues keyed by "conv_{conversation_id}_{queue_id}"
_sse_queues: Dict[str, queue.Queue] = {}
_queues_lock = threading.Lock()


def create_sse_stream(conversation_id: int) -> Response:
    """Create a Flask SSE streaming response for a conversation."""

    stream_key = f"conv_{conversation_id}"
    q: queue.Queue = queue.Queue()
    connection_key = f"{stream_key}_{id(q)}"

    with _queues_lock:
        _sse_queues[connection_key] = q

    def generate():
        try:
            # Initial connected event
            yield _sse_line({"type": "connected", "conversation_id": conversation_id})

            while True:
                try:
                    event = q.get(timeout=25)
                    yield _sse_line(event)
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    yield _sse_line({"type": "heartbeat"})
        except GeneratorExit:
            pass
        finally:
            with _queues_lock:
                _sse_queues.pop(connection_key, None)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


def push_sse_event(conversation_id: int, event: Dict) -> None:
    """Push an event to all SSE connections for a conversation.

    Args:
        conversation_id: The conversation to push to.
        event: Event dict to serialize as JSON.
    """
    stream_key = f"conv_{conversation_id}"
    with _queues_lock:
        for key, q in list(_sse_queues.items()):
            if key.startswith(stream_key):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass  # drop event if queue is full (slow client)


def broadcast_phase_change(conversation_id: int, from_phase: str, to_phase: str,
                           agent: str = "") -> None:
    """Helper to broadcast a phase transition."""
    push_sse_event(conversation_id, {
        "type": "phase_change",
        "from": from_phase,
        "to": to_phase,
        "agent": agent,
    })


def broadcast_error(conversation_id: int, message: str, agent: str = "") -> None:
    """Helper to broadcast an error event."""
    push_sse_event(conversation_id, {
        "type": "error",
        "agent": agent,
        "message": message,
    })


def _sse_line(data: Dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
