"""
Flow routes.
"""

from flask import jsonify, request

from service.errors import AppError
from service.flow_service import get_flow_status, resume_flow, retry_script, start_flow


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
