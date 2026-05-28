from __future__ import annotations

from typing import Any, Dict, List

from models import DefectCandidate, FixSuggestion, Requirement, db


class AutoFixService:
    def generate_suggestions(self, requirement_id: int) -> Dict[str, Any]:
        requirement = db.session.get(Requirement, requirement_id)
        if not requirement:
            raise ValueError(f"Requirement {requirement_id} not found")

        defects = (
            DefectCandidate.query.filter_by(requirement_id=requirement_id)
            .order_by(DefectCandidate.created_at.asc())
            .all()
        )

        FixSuggestion.query.filter_by(requirement_id=requirement_id).delete(synchronize_session=False)
        db.session.commit()

        created: List[FixSuggestion] = []
        for defect in defects:
            suggestion = FixSuggestion(
                requirement_id=requirement_id,
                defect_candidate_id=defect.id,
                mode="suggestion_only",
                title=f"Suggested fix: {defect.title}",
                root_cause=self._infer_root_cause(defect),
                suggested_action=self._suggest_action(defect),
                target_files=self._extract_target_files(defect),
                patch_preview=self._build_patch_preview(defect),
                confidence=self._estimate_confidence(defect),
            )
            db.session.add(suggestion)
            created.append(suggestion)

        db.session.commit()
        return {
            "requirement_id": requirement_id,
            "suggestion_count": len(created),
            "items": [item.to_dict() for item in created],
        }

    def _infer_root_cause(self, defect: DefectCandidate) -> str:
        if defect.source_type == "code_review":
            return defect.summary or "Code review identified missing defensive logic."
        if defect.source_type == "execution":
            return defect.summary or "Execution failed due to runtime mismatch or missing wait/assertion."
        return defect.summary or "The current implementation does not satisfy the requirement."

    def _suggest_action(self, defect: DefectCandidate) -> str:
        title = (defect.title or "").lower()
        summary = (defect.summary or "").lower()

        if "retry" in title or "retry" in summary:
            return "Add retry limit validation and persist the failure counter before accepting the verification code."
        if "timeout" in summary or "selector" in summary:
            return "Stabilize the UI flow by waiting for the final page state or selector before asserting success."
        if defect.source_type == "execution":
            return "Adjust the test expectation or application behavior so the failed execution path matches the requirement."
        return "Add the missing guard logic and update related tests to cover the failing scenario."

    def _extract_target_files(self, defect: DefectCandidate) -> List[str]:
        evidence = defect.evidence or {}
        file_path = evidence.get("file_path")
        if file_path:
            return [file_path]

        if defect.source_type == "execution":
            return ["tests/or/ui-flow-related-script.py"]
        return []

    def _build_patch_preview(self, defect: DefectCandidate) -> str:
        targets = self._extract_target_files(defect)
        target = targets[0] if targets else "relevant/file.py"
        action = self._suggest_action(defect)

        return "\n".join(
            [
                f"# Suggested patch target: {target}",
                "# Mode: suggestion_only",
                "# Intent:",
                action,
            ]
        )

    def _estimate_confidence(self, defect: DefectCandidate) -> float:
        if defect.source_type == "code_review" and defect.evidence and defect.evidence.get("file_path"):
            return 0.84
        if defect.source_type == "execution":
            return 0.72
        return 0.6


autofix_service = AutoFixService()
