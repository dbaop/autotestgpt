import json
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

from models import db, KnowledgeBase, KnowledgeEntry, Requirement, TestCase
from service.embedding_service import embedding_service

AUTO_HISTORY_KB_NAME = "AutoTestGPT 历史资产"

_HISTORICAL_REQUIREMENT_STATUSES = {
    "parsed",
    "cases_generated",
    "code_generated",
    "executing",
    "executed",
    "completed",
}


class KnowledgeService:
    def create_knowledge_base(self, name: str, description: str = "") -> KnowledgeBase:
        knowledge_base = KnowledgeBase(name=name.strip(), description=(description or "").strip())
        db.session.add(knowledge_base)
        db.session.commit()
        return knowledge_base

    def add_entry(
        self,
        knowledge_base_id: int,
        title: str,
        content: str,
        tags: Optional[Iterable[str]] = None,
        source_type: str = "manual",
        source_ref: Optional[str] = None,
    ) -> KnowledgeEntry:
        entry = KnowledgeEntry(
            knowledge_base_id=knowledge_base_id,
            title=title.strip(),
            content=content.strip(),
            tags=self._normalize_tags(tags),
            source_type=source_type,
            source_ref=source_ref,
        )
        self._attach_embedding(entry)
        db.session.add(entry)
        db.session.commit()
        return entry

    def import_document_entry(
        self,
        knowledge_base_id: int,
        title: str,
        content: str,
        tags: Optional[Iterable[str]] = None,
        source_ref: Optional[str] = None,
    ) -> KnowledgeEntry:
        return self.add_entry(
            knowledge_base_id=knowledge_base_id,
            title=title,
            content=content,
            tags=tags,
            source_type="document",
            source_ref=source_ref,
        )

    def list_knowledge_bases(self) -> List[KnowledgeBase]:
        return KnowledgeBase.query.order_by(KnowledgeBase.updated_at.desc()).all()

    def list_entries(self, knowledge_base_id: int) -> List[KnowledgeEntry]:
        return (
            KnowledgeEntry.query.filter_by(knowledge_base_id=knowledge_base_id)
            .order_by(KnowledgeEntry.updated_at.desc())
            .all()
        )

    def search_entries(
        self,
        query: str,
        knowledge_base_ids: Optional[List[int]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return []

        entry_query = KnowledgeEntry.query
        if knowledge_base_ids:
            entry_query = entry_query.filter(KnowledgeEntry.knowledge_base_id.in_(knowledge_base_ids))

        scored_items: List[Dict[str, Any]] = []
        query_terms = self._tokenize(normalized_query)
        query_embedding = (
            embedding_service.embed_text(normalized_query)
            if embedding_service.is_enabled()
            else None
        )

        for entry in entry_query.all():
            keyword_score = self._score_entry(query_terms, entry)
            vector_score = self._score_entry_vector(normalized_query, query_embedding, entry)
            score, score_method = self._combine_scores(keyword_score, vector_score)
            if score <= 0:
                continue
            scored_items.append(
                {
                    "id": entry.id,
                    "knowledge_base_id": entry.knowledge_base_id,
                    "title": entry.title,
                    "content": entry.content,
                    "tags": entry.tags or [],
                    "score": round(score, 4),
                    "score_method": score_method,
                    "source_type": "knowledge_entry",
                }
            )

        scored_items.sort(key=lambda item: (-item["score"], item["id"]))
        return scored_items[: max(limit, 1)]

    def search_all_sources(
        self,
        query: str,
        knowledge_base_ids: Optional[List[int]] = None,
        exclude_requirement_id: Optional[int] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return {
                "items": [],
                "knowledge_entries": [],
                "historical_requirements": [],
                "historical_test_cases": [],
            }

        structured_req = {"title": normalized_query, "description": normalized_query}
        per_source_limit = max(limit, 1)
        knowledge_entries = self.search_entries(
            normalized_query,
            knowledge_base_ids=knowledge_base_ids,
            limit=per_source_limit,
        )
        historical_requirements = self.search_historical_requirements(
            structured_req,
            exclude_requirement_id=exclude_requirement_id,
            limit=per_source_limit,
        )
        historical_test_cases = self.search_historical_test_cases(
            structured_req,
            exclude_requirement_id=exclude_requirement_id,
            limit=per_source_limit,
        )

        merged: List[Dict[str, Any]] = []
        merged.extend(knowledge_entries)
        merged.extend(historical_requirements)
        merged.extend(historical_test_cases)
        merged.sort(key=lambda item: (-item.get("score", 0), item.get("id", 0)))

        return {
            "items": merged[: max(limit, 1)],
            "knowledge_entries": knowledge_entries,
            "historical_requirements": historical_requirements,
            "historical_test_cases": historical_test_cases,
        }

    def get_or_create_auto_history_kb(self) -> KnowledgeBase:
        knowledge_base = KnowledgeBase.query.filter_by(name=AUTO_HISTORY_KB_NAME).first()
        if knowledge_base:
            return knowledge_base
        return self.create_knowledge_base(
            AUTO_HISTORY_KB_NAME,
            "Auto-indexed requirements and test cases",
        )

    def index_requirement(self, requirement_id: int) -> Dict[str, Any]:
        requirement = db.session.get(Requirement, requirement_id)
        if not requirement:
            raise ValueError(f"Requirement {requirement_id} not found")

        target_kb_ids: List[int] = [self.get_or_create_auto_history_kb().id]
        if requirement.knowledge_base_id and requirement.knowledge_base_id not in target_kb_ids:
            target_kb_ids.insert(0, requirement.knowledge_base_id)

        cases = TestCase.query.filter_by(requirement_id=requirement.id).all()
        entry_count = 1 + len(cases)

        for knowledge_base_id in target_kb_ids:
            req_ref = f"requirement:{requirement.id}"
            self._upsert_entry(
                knowledge_base_id=knowledge_base_id,
                title=f"[REQ#{requirement.id}] {requirement.title}",
                content=self._build_requirement_index_content(requirement, cases),
                tags=self._build_requirement_index_tags(requirement, cases),
                source_type="requirement",
                source_ref=req_ref,
            )

            for case in cases:
                case_ref = f"requirement:{requirement.id}:case:{case.id}"
                self._upsert_entry(
                    knowledge_base_id=knowledge_base_id,
                    title=f"[TC#{case.id}] {case.title}",
                    content=self._build_test_case_index_content(requirement, case),
                    tags=self._build_test_case_index_tags(requirement, case),
                    source_type="test_case",
                    source_ref=case_ref,
                )

        return {
            "requirement_id": requirement.id,
            "knowledge_base_ids": target_kb_ids,
            "entry_count": entry_count,
            "test_case_count": len(cases),
        }

    def search_historical_requirements(
        self,
        structured_req: Dict[str, Any],
        exclude_requirement_id: Optional[int] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        query = self._build_requirement_query(structured_req)
        if not query:
            return []

        query_terms = self._tokenize(query)
        scored_items: List[Dict[str, Any]] = []

        req_query = Requirement.query.filter(Requirement.status.in_(_HISTORICAL_REQUIREMENT_STATUSES))
        if exclude_requirement_id is not None:
            req_query = req_query.filter(Requirement.id != exclude_requirement_id)

        for requirement in req_query.all():
            haystack = self._requirement_search_text(requirement)
            score = self._score_text(query_terms, requirement.title or "", haystack)
            if score <= 0:
                continue
            scored_items.append(
                {
                    "id": requirement.id,
                    "requirement_id": requirement.id,
                    "title": requirement.title,
                    "description": requirement.description,
                    "status": requirement.status,
                    "summary": self._summarize_requirement(requirement),
                    "source_type": "historical_requirement",
                    "score": round(score, 4),
                }
            )

        scored_items.sort(key=lambda item: (-item["score"], -item["id"]))
        return scored_items[: max(limit, 1)]

    def search_historical_test_cases(
        self,
        structured_req: Dict[str, Any],
        exclude_requirement_id: Optional[int] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        query = self._build_requirement_query(structured_req)
        if not query:
            return []

        query_terms = self._tokenize(query)
        scored_items: List[Dict[str, Any]] = []

        case_query = TestCase.query.join(Requirement, TestCase.requirement_id == Requirement.id).filter(
            Requirement.status.in_(_HISTORICAL_REQUIREMENT_STATUSES)
        )
        if exclude_requirement_id is not None:
            case_query = case_query.filter(TestCase.requirement_id != exclude_requirement_id)

        for case in case_query.all():
            requirement = case.requirement
            haystack = self._test_case_search_text(case, requirement)
            score = self._score_text(query_terms, case.title or "", haystack)
            if score <= 0:
                continue
            scored_items.append(
                {
                    "id": case.id,
                    "test_case_id": case.id,
                    "requirement_id": case.requirement_id,
                    "requirement_title": requirement.title if requirement else "",
                    "title": case.title,
                    "description": case.description,
                    "test_type": case.test_type,
                    "priority": case.priority,
                    "methodology": case.methodology,
                    "steps_summary": self._summarize_test_case_steps(case),
                    "source_type": "historical_test_case",
                    "score": round(score, 4),
                }
            )

        scored_items.sort(key=lambda item: (-item["score"], -item["id"]))
        return scored_items[: max(limit, 1)]

    def build_case_context(
        self,
        structured_req: Dict[str, Any],
        knowledge_base_ids: Optional[List[int]] = None,
        exclude_requirement_id: Optional[int] = None,
        limit: int = 3,
    ) -> Dict[str, Any]:
        query = self._build_requirement_query(structured_req)
        knowledge_entries = self.search_entries(query, knowledge_base_ids=knowledge_base_ids, limit=limit)
        historical_requirements = self.search_historical_requirements(
            structured_req,
            exclude_requirement_id=exclude_requirement_id,
            limit=limit,
        )
        historical_test_cases = self.search_historical_test_cases(
            structured_req,
            exclude_requirement_id=exclude_requirement_id,
            limit=limit,
        )

        prompt_parts: List[str] = []
        if knowledge_entries:
            prompt_parts.append("Reference knowledge entries:")
            for index, item in enumerate(knowledge_entries, start=1):
                tags = ", ".join(item["tags"])
                prompt_parts.append(f"{index}. {item['title']}")
                prompt_parts.append(f"   Content: {item['content']}")
                if tags:
                    prompt_parts.append(f"   Tags: {tags}")

        if historical_requirements:
            prompt_parts.append("\nHistorical similar requirements:")
            for index, item in enumerate(historical_requirements, start=1):
                prompt_parts.append(f"{index}. [REQ#{item['requirement_id']}] {item['title']}")
                if item.get("summary"):
                    prompt_parts.append(f"   Summary: {item['summary']}")

        if historical_test_cases:
            prompt_parts.append("\nHistorical similar test cases:")
            for index, item in enumerate(historical_test_cases, start=1):
                prompt_parts.append(
                    f"{index}. [TC#{item['test_case_id']} / REQ#{item['requirement_id']}] {item['title']}"
                )
                if item.get("description"):
                    prompt_parts.append(f"   Description: {item['description']}")
                if item.get("steps_summary"):
                    prompt_parts.append(f"   Steps: {item['steps_summary']}")

        return {
            "items": knowledge_entries,
            "knowledge_entries": knowledge_entries,
            "historical_requirements": historical_requirements,
            "historical_test_cases": historical_test_cases,
            "prompt_text": "\n".join(prompt_parts),
        }

    def build_requirement_parse_context(
        self,
        demand: str,
        knowledge_base_ids: Optional[List[int]] = None,
        exclude_requirement_id: Optional[int] = None,
        limit: int = 3,
    ) -> Dict[str, Any]:
        normalized = (demand or "").strip()
        if not normalized:
            return {
                "items": [],
                "knowledge_entries": [],
                "historical_requirements": [],
                "historical_test_cases": [],
                "prompt_text": "",
            }

        structured_req = {"title": normalized[:200], "description": normalized}
        return self.build_case_context(
            structured_req,
            knowledge_base_ids=knowledge_base_ids,
            exclude_requirement_id=exclude_requirement_id,
            limit=limit,
        )

    def _build_requirement_query(self, structured_req: Dict[str, Any]) -> str:
        parts: List[str] = [
            structured_req.get("title", ""),
            structured_req.get("description", ""),
        ]

        for module in structured_req.get("business_modules", []):
            parts.append(module.get("name", ""))
            parts.append(module.get("description", ""))

        for interface in structured_req.get("interfaces", []):
            parts.append(interface.get("endpoint", ""))
            parts.append(interface.get("description", ""))

        for point in structured_req.get("test_points", []):
            parts.append(point.get("description", ""))

        return " ".join(part for part in parts if part).strip()

    def _score_entry(self, query_terms: List[str], entry: KnowledgeEntry) -> float:
        haystack_terms = self._tokenize(" ".join([entry.title, entry.content, " ".join(entry.tags or [])]))
        return self._score_terms(query_terms, haystack_terms, title_text=entry.title)

    def _score_text(self, query_terms: List[str], title: str, content: str) -> float:
        haystack_terms = self._tokenize(" ".join([title, content]))
        return self._score_terms(query_terms, haystack_terms, title_text=title)

    def _score_terms(self, query_terms: List[str], haystack_terms: List[str], title_text: str = "") -> float:
        if not haystack_terms:
            return 0.0

        haystack_counts = Counter(haystack_terms)
        exact_matches = sum(1 for term in query_terms if term in haystack_counts)
        weighted_matches = sum(haystack_counts.get(term, 0) for term in query_terms)
        title_bonus = sum(1 for term in query_terms if term in self._tokenize(title_text)) * 0.5
        fallback_overlap = len(set(query_terms) & set(haystack_terms))

        return exact_matches + (weighted_matches * 0.2) + title_bonus + (fallback_overlap * 0.1)

    def _requirement_search_text(self, requirement: Requirement) -> str:
        parts = [requirement.description or ""]
        structured = requirement.structured_data or {}
        if isinstance(structured, dict):
            parts.extend(
                [
                    structured.get("title", ""),
                    structured.get("description", ""),
                ]
            )
            for module in structured.get("business_modules", []):
                parts.extend([module.get("name", ""), module.get("description", "")])
            for interface in structured.get("interfaces", []):
                parts.extend([interface.get("endpoint", ""), interface.get("description", "")])
            for point in structured.get("test_points", []):
                parts.append(point.get("description", ""))
        return " ".join(part for part in parts if part)

    def _summarize_requirement(self, requirement: Requirement) -> str:
        parts = [requirement.description or ""]
        structured = requirement.structured_data or {}
        if isinstance(structured, dict):
            modules = structured.get("business_modules") or []
            if modules:
                module_names = ", ".join(module.get("name", "") for module in modules if module.get("name"))
                if module_names:
                    parts.append(f"Modules: {module_names}")
            interfaces = structured.get("interfaces") or []
            if interfaces:
                endpoints = ", ".join(
                    f"{interface.get('method', 'GET')} {interface.get('endpoint', '')}".strip()
                    for interface in interfaces
                    if interface.get("endpoint")
                )
                if endpoints:
                    parts.append(f"Interfaces: {endpoints}")
        summary = " | ".join(part.strip() for part in parts if part and part.strip())
        return summary[:500]

    def _test_case_search_text(self, case: TestCase, requirement: Optional[Requirement]) -> str:
        parts = [case.description or "", case.test_type or "", case.methodology or ""]
        if requirement:
            parts.extend([requirement.title or "", requirement.description or ""])
        if case.steps:
            parts.append(json.dumps(case.steps, ensure_ascii=False))
        if case.expected_results:
            parts.append(json.dumps(case.expected_results, ensure_ascii=False))
        return " ".join(part for part in parts if part)

    def _summarize_test_case_steps(self, case: TestCase) -> str:
        steps = case.steps or []
        if not isinstance(steps, list):
            return str(steps)[:300]

        fragments: List[str] = []
        for step in steps[:3]:
            if not isinstance(step, dict):
                continue
            action = step.get("action") or step.get("step")
            expected = step.get("expected")
            if action and expected:
                fragments.append(f"{action} -> {expected}")
            elif action:
                fragments.append(str(action))
        if not fragments and case.expected_results:
            fragments.extend(str(item) for item in case.expected_results[:3])
        return "; ".join(fragments)[:500]

    def _tokenize(self, text: str) -> List[str]:
        normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", (text or "").lower())
        pieces = [piece.strip() for piece in normalized.split() if piece.strip()]
        terms: List[str] = []

        for piece in pieces:
            if len(piece) >= 2:
                terms.append(piece)
            if re.search(r"[\u4e00-\u9fff]", piece):
                terms.extend(self._cjk_bigrams(piece))

        return terms

    def _cjk_bigrams(self, text: str) -> List[str]:
        chars = [char for char in text if re.search(r"[\u4e00-\u9fff]", char)]
        if len(chars) < 2:
            return chars
        return ["".join(chars[index:index + 2]) for index in range(len(chars) - 1)]

    def _normalize_tags(self, tags: Optional[Iterable[str]]) -> List[str]:
        if not tags:
            return []
        normalized = []
        for tag in tags:
            if tag is None:
                continue
            value = str(tag).strip()
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    def _entry_embedding_text(self, entry: KnowledgeEntry) -> str:
        return " ".join(
            part
            for part in [entry.title or "", entry.content or "", " ".join(entry.tags or [])]
            if part
        )

    def _attach_embedding(self, entry: KnowledgeEntry) -> None:
        if not embedding_service.is_enabled():
            return
        embedding = embedding_service.embed_text(self._entry_embedding_text(entry))
        if embedding:
            entry.embedding = embedding

    def _score_entry_vector(
        self,
        query: str,
        query_embedding: Optional[List[float]],
        entry: KnowledgeEntry,
    ) -> float:
        if not query_embedding:
            return 0.0

        entry_embedding = entry.embedding
        if not entry_embedding:
            entry_embedding = embedding_service.embed_text(self._entry_embedding_text(entry))
            if entry_embedding:
                entry.embedding = entry_embedding

        if not entry_embedding:
            return 0.0

        similarity = embedding_service.cosine_similarity(query_embedding, entry_embedding)
        return max(similarity, 0.0) * 10

    def _combine_scores(self, keyword_score: float, vector_score: float) -> tuple[float, str]:
        if vector_score <= 0:
            return keyword_score, "keyword"
        if keyword_score <= 0:
            return vector_score, "vector"
        return (keyword_score * 0.3) + (vector_score * 0.7), "hybrid"

    def _upsert_entry(
        self,
        knowledge_base_id: int,
        title: str,
        content: str,
        tags: Optional[Iterable[str]],
        source_type: str,
        source_ref: str,
    ) -> KnowledgeEntry:
        existing = KnowledgeEntry.query.filter_by(
            knowledge_base_id=knowledge_base_id,
            source_ref=source_ref,
        ).first()
        normalized_tags = self._normalize_tags(tags)

        if existing:
            existing.title = title.strip()
            existing.content = content.strip()
            existing.tags = normalized_tags
            existing.source_type = source_type
            self._attach_embedding(existing)
            db.session.commit()
            return existing

        return self.add_entry(
            knowledge_base_id=knowledge_base_id,
            title=title,
            content=content,
            tags=normalized_tags,
            source_type=source_type,
            source_ref=source_ref,
        )

    def _build_requirement_index_content(self, requirement: Requirement, cases: List[TestCase]) -> str:
        lines = [
            f"Title: {requirement.title}",
            f"Description: {requirement.description}",
            f"Status: {requirement.status}",
        ]
        summary = self._summarize_requirement(requirement)
        if summary:
            lines.append(f"Summary: {summary}")
        if cases:
            lines.append("Test cases:")
            for case in cases[:20]:
                lines.append(f"- [{case.test_type or 'unknown'}] {case.title}: {case.description or ''}")
        return "\n".join(line for line in lines if line).strip()

    def _build_requirement_index_tags(self, requirement: Requirement, cases: List[TestCase]) -> List[str]:
        tags = ["requirement", requirement.status or "unknown"]
        for case in cases[:10]:
            if case.test_type and case.test_type not in tags:
                tags.append(case.test_type)
        return tags[:12]

    def _build_test_case_index_content(self, requirement: Requirement, case: TestCase) -> str:
        lines = [
            f"Requirement: [{requirement.id}] {requirement.title}",
            f"Title: {case.title}",
            f"Description: {case.description or ''}",
            f"Type: {case.test_type or ''}",
            f"Priority: {case.priority or ''}",
            f"Methodology: {case.methodology or ''}",
        ]
        steps_summary = self._summarize_test_case_steps(case)
        if steps_summary:
            lines.append(f"Steps: {steps_summary}")
        if case.expected_results:
            lines.append(f"Expected: {json.dumps(case.expected_results, ensure_ascii=False)}")
        return "\n".join(line for line in lines if line).strip()

    def _build_test_case_index_tags(self, requirement: Requirement, case: TestCase) -> List[str]:
        tags = ["test_case", f"req-{requirement.id}"]
        if case.test_type:
            tags.append(case.test_type)
        if case.methodology:
            tags.append(case.methodology)
        if case.priority:
            tags.append(case.priority)
        return tags[:12]


knowledge_service = KnowledgeService()
