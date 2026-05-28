"""
Code review task routes.
"""

from __future__ import annotations

from flask import jsonify, request

from models import db, CodeReviewTask, CodeReviewFinding
from service.errors import AppError, ValidationError
from service.review_service import run_review_task, run_review_task_async



def create_review_task():
    try:
        body = request.get_json() or {}
        repo_url = (body.get("repo_url") or "").strip()
        branch = (body.get("branch") or "main").strip()
        days = int(body.get("days") or 7)
        if not repo_url:
            raise ValidationError("repo_url is required")
        if days <= 0:
            raise ValidationError("days must be > 0")

        task = CodeReviewTask(repo_url=repo_url, branch=branch, days=days, status="pending")
        db.session.add(task)
        db.session.commit()

        run_mode = (body.get("mode") or "async").lower()
        result = run_review_task(task.id) if run_mode == "sync" else run_review_task_async(task.id)
        status_code = 201 if run_mode == "sync" else 202
        return jsonify({"task": task.to_dict(), "run_result": result}), status_code
    except AppError as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "REVIEW_TASK_FAILED", "message": str(e)}), 500



def list_review_tasks():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = CodeReviewTask.query.order_by(CodeReviewTask.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return jsonify(
        {
            "items": [item.to_dict() for item in pagination.items],
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
            "pages": pagination.pages,
        }
    )



def get_review_task(task_id: int):
    task = db.get_or_404(CodeReviewTask, task_id)
    findings = (
        CodeReviewFinding.query.filter_by(task_id=task_id)
        .order_by(CodeReviewFinding.created_at.desc())
        .all()
    )

    data = task.to_dict()
    data["findings"] = [f.to_dict() for f in findings]
    return jsonify(data)
