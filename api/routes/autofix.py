from flask import jsonify, request

from service.errors import AppError, ValidationError
from service.autofix_service import autofix_service


def generate_fix_suggestions():
    try:
        data = request.get_json() or {}
        requirement_id = data.get("requirement_id")
        if not requirement_id:
            raise ValidationError("requirement_id is required")
        result = autofix_service.generate_suggestions(requirement_id)
        return jsonify(result)
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": "AUTOFIX_FAILED", "message": str(e)}), 500
