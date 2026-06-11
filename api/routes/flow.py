"""
Flow routes.
"""

from flask import jsonify, request

from service.errors import AppError
from service.flow_service import (
    confirm_case_review,
    get_flow_status,
    re_execute_requirement,
    request_cancel,
    resume_flow,
    retry_script,
    start_flow,
)


def start_test_flow():
    try:
        payload = start_flow(request.get_json() or {})
        return jsonify(payload), 202
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code


def get_test_flow_status(req_id: int):
    try:
        payload = get_flow_status(req_id)
        return jsonify(payload)
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code


def resume_test_flow(req_id: int):
    try:
        payload, status_code = resume_flow(req_id)
        return jsonify(payload), status_code
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code


def retry_test_script(script_id: int):
    try:
        return jsonify(retry_script(script_id))
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code


def cancel_test_flow(req_id: int):
    """Request cooperative cancellation of a running flow."""
    request_cancel(req_id)
    return jsonify({
        "message": "Cancellation requested",
        "requirement_id": req_id,
        "status": "cancelling",
    }), 202


def confirm_cases_test_flow(req_id: int):
    """Mark case review as confirmed and resume the flow."""
    try:
        payload = confirm_case_review(req_id)
        return jsonify(payload), 202
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code


def re_execute_test_flow(req_id: int):
    """Re-execute all scripts for a requirement (regression test)."""
    import logging
    _log = logging.getLogger(__name__)
    try:
        payload = re_execute_requirement(req_id)
        return jsonify(payload), 202
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        _log.exception("re_execute_test_flow failed for req %d", req_id)
        return jsonify({"error": str(type(e).__name__), "message": str(e)}), 500
