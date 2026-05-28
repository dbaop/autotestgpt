from flask import Response, jsonify, request

from models import FinalReport, db
from service.defect_service import defect_service
from service.errors import AppError, ValidationError
from service.report_service import report_service


def create_requirement_report():
    try:
        data = request.get_json() or {}
        requirement_id = data.get("requirement_id")
        if not requirement_id:
            raise ValidationError("requirement_id is required")
        review_task_id = data.get("review_task_id")
        defect_service.analyze_requirement(requirement_id, review_task_id)
        report = report_service.generate_requirement_report(requirement_id, review_task_id)
        return jsonify({"message": "Report generated", "report": report.to_dict()}), 201
    except AppError as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": "REPORT_FAILED", "message": str(e)}), 500


def get_report(report_id: int):
    try:
        report = db.get_or_404(FinalReport, report_id)
        payload = report.to_dict()
        payload["html_content"] = report.html_content
        payload["execution_summary"] = report_service.build_execution_bundle(report.requirement_id)["summary"]
        return jsonify({"report": payload})
    except Exception as e:
        return jsonify({"error": "REPORT_LOAD_FAILED", "message": str(e)}), 500


def preview_report(report_id: int):
    report = db.get_or_404(FinalReport, report_id)
    return Response(report.html_content, mimetype="text/html")
