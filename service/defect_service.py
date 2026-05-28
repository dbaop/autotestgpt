from __future__ import annotations

from typing import Any, Dict, List, Optional

from models import (
    db,
    CodeReviewFinding,
    CodeReviewTask,
    DefectCandidate,
    ExecutionRecord,
    Requirement,
    TestCase,
    TestScript,
)


class DefectService:
    def analyze_requirement(self, requirement_id: int, review_task_id: Optional[int] = None) -> Dict[str, Any]:
        requirement = db.session.get(Requirement, requirement_id)
        if not requirement:
            raise ValueError(f"Requirement {requirement_id} not found")

        review_task = db.session.get(CodeReviewTask, review_task_id) if review_task_id else None

        DefectCandidate.query.filter_by(
            requirement_id=requirement_id,
            review_task_id=review_task_id,
        ).delete(synchronize_session=False)
        db.session.commit()

        items: List[DefectCandidate] = []
        items.extend(self._create_review_candidates(requirement, review_task))
        items.extend(self._create_execution_candidates(requirement, review_task))
        db.session.commit()

        return {
            "requirement_id": requirement_id,
            "review_task_id": review_task_id,
            "defect_count": len(items),
            "items": [item.to_dict() for item in items],
        }

    def _create_review_candidates(
        self,
        requirement: Requirement,
        review_task: Optional[CodeReviewTask],
    ) -> List[DefectCandidate]:
        if not review_task:
            return []

        candidates: List[DefectCandidate] = []
        for finding in review_task.findings:
            candidate = DefectCandidate(
                requirement_id=requirement.id,
                review_task_id=review_task.id,
                source_type="code_review",
                severity=finding.severity or "medium",
                title=f"Code review risk: {finding.title}",
                summary=finding.detail,
                evidence={
                    "commit_sha": finding.commit_sha,
                    "file_path": finding.file_path,
                    "finding_id": finding.id,
                },
            )
            db.session.add(candidate)
            candidates.append(candidate)
        return candidates

    def _create_execution_candidates(
        self,
        requirement: Requirement,
        review_task: Optional[CodeReviewTask],
    ) -> List[DefectCandidate]:
        candidates: List[DefectCandidate] = []
        cases = TestCase.query.filter_by(requirement_id=requirement.id).all()
        case_ids = [case.id for case in cases]
        if not case_ids:
            return candidates

        scripts = TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).all()
        script_map = {script.id: script for script in scripts}
        script_ids = list(script_map.keys())
        if not script_ids:
            return candidates

        records = (
            ExecutionRecord.query.filter(ExecutionRecord.test_script_id.in_(script_ids))
            .order_by(ExecutionRecord.id.desc())
            .all()
        )

        case_map = {case.id: case for case in cases}
        for record in records:
            normalized_status = (record.status or "").lower()
            if normalized_status not in {"fail", "failed", "error"}:
                continue

            script = script_map.get(record.test_script_id)
            case = case_map.get(script.test_case_id) if script else None
            if not case:
                continue

            candidate = DefectCandidate(
                requirement_id=requirement.id,
                review_task_id=review_task.id if review_task else None,
                test_case_id=case.id,
                execution_record_id=record.id,
                source_type="execution",
                severity="high",
                title=f"Execution failure: {case.title}",
                summary=record.error_message or "Execution failed",
                evidence={
                    "execution_record_id": record.id,
                    "script_id": script.id if script else None,
                    "result_data": record.result_data,
                },
            )
            db.session.add(candidate)
            candidates.append(candidate)

        return candidates


defect_service = DefectService()
