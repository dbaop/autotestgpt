from __future__ import annotations

import html
import json
from typing import Optional

from models import (
    CodeReviewTask,
    DefectCandidate,
    ExecutionRecord,
    FinalReport,
    Requirement,
    TestCase,
    TestScript,
    db,
)


class ReportService:
    def generate_requirement_report(self, requirement_id: int, review_task_id: Optional[int] = None) -> FinalReport:
        requirement = db.session.get(Requirement, requirement_id)
        if not requirement:
            raise ValueError(f"Requirement {requirement_id} not found")

        review_task = db.session.get(CodeReviewTask, review_task_id) if review_task_id else None
        cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
        defects = (
            DefectCandidate.query.filter_by(requirement_id=requirement_id, review_task_id=review_task_id)
            .order_by(DefectCandidate.created_at.desc())
            .all()
        )
        execution_bundle = self.build_execution_bundle(requirement_id)

        title = f"Requirement Analysis Report - {requirement.title}"
        html_content = self._build_html(requirement, review_task, cases, defects, execution_bundle)
        summary = f"{len(cases)} cases, {len(defects)} defects"

        existing = (
            FinalReport.query.filter_by(requirement_id=requirement_id, review_task_id=review_task_id, report_type="requirement_analysis")
            .order_by(FinalReport.id.desc())
            .first()
        )
        if existing:
            existing.title = title
            existing.html_content = html_content
            existing.summary = summary
            db.session.commit()
            return existing

        report = FinalReport(
            requirement_id=requirement_id,
            review_task_id=review_task_id,
            report_type="requirement_analysis",
            title=title,
            html_content=html_content,
            summary=summary,
        )
        db.session.add(report)
        db.session.commit()
        return report

    def build_execution_bundle(self, requirement_id: int):
        cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
        case_map = {case.id: case for case in cases}
        case_ids = list(case_map.keys())
        if not case_ids:
            return {"summary": self._empty_execution_summary(), "sections": {"api": [], "ui": [], "other": []}}

        scripts = TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).all()
        script_map = {script.id: script for script in scripts}
        script_ids = list(script_map.keys())
        if not script_ids:
            return {"summary": self._empty_execution_summary(), "sections": {"api": [], "ui": [], "other": []}}

        records = (
            ExecutionRecord.query.filter(ExecutionRecord.test_script_id.in_(script_ids))
            .order_by(ExecutionRecord.id.asc())
            .all()
        )
        sections = {"api": [], "ui": [], "other": []}
        summary = self._empty_execution_summary()

        for record in records:
            summary["total"] += 1
            normalized_status = (record.status or "").lower()
            if normalized_status in summary:
                summary[normalized_status] += 1
            else:
                summary["other"] += 1

            script = script_map.get(record.test_script_id)
            case = case_map.get(script.test_case_id) if script else None
            case_type = (case.test_type or "").lower() if case else ""
            section_name = "ui" if case_type == "ui" else "api" if case_type == "api" else "other"
            sections[section_name].append(
                {
                    "case_title": case.title if case else "",
                    "case_type": case.test_type if case else "",
                    "script_type": script.script_type if script else "",
                    "status": record.status,
                    "execution_time": record.execution_time,
                    "error_message": record.error_message,
                    "result_data": record.result_data or {},
                }
            )

        return {"summary": summary, "sections": sections}

    def _empty_execution_summary(self):
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "error": 0,
            "other": 0,
        }

    def _build_html(self, requirement: Requirement, review_task: Optional[CodeReviewTask], cases, defects, execution_bundle) -> str:
        review_summary = review_task.summary if review_task else "No code review task linked."
        escaped_title = html.escape(requirement.title or "Requirement")
        escaped_desc = html.escape(requirement.description or "")
        execution_summary = execution_bundle["summary"]
        execution_sections = execution_bundle["sections"]

        parts = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='utf-8'>",
            f"<title>{escaped_title}</title>",
            "<style>",
            "body { font-family: 'Segoe UI', Arial, sans-serif; margin: 24px; color: #1f2937; background: #f8fafc; }",
            ".card { background: #ffffff; border: 1px solid #dbe4ee; border-radius: 14px; padding: 20px; margin-bottom: 18px; }",
            "h1, h2 { margin: 0 0 12px 0; }",
            ".meta { color: #475569; }",
            ".chip { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; margin-right: 8px; }",
            ".high { background: #fee2e2; color: #991b1b; }",
            ".medium { background: #fef3c7; color: #92400e; }",
            ".low { background: #dcfce7; color: #166534; }",
            "table { width: 100%; border-collapse: collapse; }",
            "th, td { text-align: left; padding: 10px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }",
            "</style>",
            "</head>",
            "<body>",
            f"<div class='card'><h1>{escaped_title}</h1><p class='meta'>{escaped_desc}</p></div>",
            "<div class='card'>",
            "<h2>Summary</h2>",
            f"<p class='meta'>Requirement status: {html.escape(requirement.status or 'unknown')}</p>",
            f"<p class='meta'>Code review: {html.escape(review_summary or '')}</p>",
            f"<p class='meta'>Total cases: {len(cases)} | Defect candidates: {len(defects)}</p>",
            "</div>",
            "<div class='card'>",
            "<h2>Test Cases</h2>",
            "<table><thead><tr><th>Title</th><th>Type</th><th>Priority</th><th>Description</th></tr></thead><tbody>",
        ]

        for case in cases:
            parts.append(
                "<tr>"
                f"<td>{html.escape(case.title or '')}</td>"
                f"<td>{html.escape(case.test_type or '')}</td>"
                f"<td>{html.escape(case.priority or '')}</td>"
                f"<td>{html.escape(case.description or '')}</td>"
                "</tr>"
            )

        parts.extend(
            [
                "</tbody></table>",
                "</div>",
                "<div class='card'>",
                "<h2>Execution Summary</h2>",
                f"<p class='meta'>Total: {execution_summary['total']} | Success: {execution_summary['success']} | Failed: {execution_summary['failed']} | Error: {execution_summary['error']}</p>",
                "</div>",
                self._build_execution_section("API Execution Details", execution_sections["api"]),
                self._build_execution_section("UI Execution Details", execution_sections["ui"]),
                self._build_execution_section("Other Execution Details", execution_sections["other"]),
                "<div class='card'>",
                "<h2>Defect Candidates</h2>",
                "<table><thead><tr><th>Title</th><th>Severity</th><th>Source</th><th>Summary</th></tr></thead><tbody>",
            ]
        )

        for defect in defects:
            severity = (defect.severity or "medium").lower()
            parts.append(
                "<tr>"
                f"<td>{html.escape(defect.title or '')}</td>"
                f"<td><span class='chip {severity}'>{html.escape(defect.severity or '')}</span></td>"
                f"<td>{html.escape(defect.source_type or '')}</td>"
                f"<td>{html.escape(defect.summary or '')}</td>"
                "</tr>"
            )

        parts.extend(["</tbody></table>", "</div>", "</body>", "</html>"])
        return "".join(parts)

    def _build_execution_section(self, title: str, items):
        parts = [
            "<div class='card'>",
            f"<h2>{html.escape(title)}</h2>",
            "<table><thead><tr><th>Case</th><th>Script Type</th><th>Status</th><th>Execution Time</th><th>Details</th></tr></thead><tbody>",
        ]

        if not items:
            parts.append("<tr><td colspan='5'>No execution records</td></tr>")
        else:
            for item in items:
                detail_parts = []
                if item.get("error_message"):
                    detail_parts.append(item["error_message"])
                result_data = item.get("result_data") or {}
                if result_data:
                    detail_parts.append(json.dumps(result_data, ensure_ascii=False))

                details = " | ".join(detail_parts) if detail_parts else "-"
                execution_time = "-" if item.get("execution_time") is None else f"{item['execution_time']:.2f}s"

                parts.append(
                    "<tr>"
                    f"<td>{html.escape(item.get('case_title') or '')}</td>"
                    f"<td>{html.escape(item.get('script_type') or '')}</td>"
                    f"<td>{html.escape(item.get('status') or '')}</td>"
                    f"<td>{html.escape(execution_time)}</td>"
                    f"<td>{html.escape(details)}</td>"
                    "</tr>"
                )

        parts.extend(["</tbody></table>", "</div>"])
        return "".join(parts)


report_service = ReportService()
