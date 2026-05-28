import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

from models import db, KnowledgeBase, KnowledgeEntry


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

        for entry in entry_query.all():
            score = self._score_entry(query_terms, entry)
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
                }
            )

        scored_items.sort(key=lambda item: (-item["score"], item["id"]))
        return scored_items[: max(limit, 1)]

    def build_case_context(
        self,
        structured_req: Dict[str, Any],
        knowledge_base_ids: Optional[List[int]] = None,
        limit: int = 3,
    ) -> Dict[str, Any]:
        query = self._build_requirement_query(structured_req)
        hits = self.search_entries(query, knowledge_base_ids=knowledge_base_ids, limit=limit)
        if not hits:
            return {"items": [], "prompt_text": ""}

        lines = ["Reference knowledge entries:"]
        for index, item in enumerate(hits, start=1):
            tags = ", ".join(item["tags"])
            lines.append(f"{index}. {item['title']}")
            lines.append(f"   Content: {item['content']}")
            if tags:
                lines.append(f"   Tags: {tags}")

        return {"items": hits, "prompt_text": "\n".join(lines)}

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
        if not haystack_terms:
            return 0.0

        haystack_counts = Counter(haystack_terms)
        exact_matches = sum(1 for term in query_terms if term in haystack_counts)
        weighted_matches = sum(haystack_counts.get(term, 0) for term in query_terms)
        title_bonus = sum(1 for term in query_terms if term in self._tokenize(entry.title)) * 0.5
        fallback_overlap = len(set(query_terms) & set(haystack_terms))

        return exact_matches + (weighted_matches * 0.2) + title_bonus + (fallback_overlap * 0.1)

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


knowledge_service = KnowledgeService()
