from __future__ import annotations

import logging
import math
from typing import List, Optional

from config import Config

logger = logging.getLogger(__name__)


class EmbeddingService:
    def is_enabled(self) -> bool:
        return bool(getattr(Config, "EMBEDDING_ENABLED", False))

    def embed_text(self, text: str) -> Optional[List[float]]:
        normalized = (text or "").strip()
        if not normalized or not self.is_enabled():
            return None

        try:
            import litellm

            response = litellm.embedding(
                model=Config.EMBEDDING_MODEL,
                input=[normalized[:8000]],
            )
            embedding = response.data[0]["embedding"]
            return [float(value) for value in embedding]
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return None

    def cosine_similarity(self, left: List[float], right: List[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0

        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)


embedding_service = EmbeddingService()
