import os
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models


class QdrantVectorStore:
    """Qdrant access layer with authorization filters applied before retrieval."""

    def __init__(self, qdrant_url=None, collection_name=None, embedding_model_name=None):
        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        self.qdrant_url = qdrant_url or f"http://{self.qdrant_host}:{self.qdrant_port}"
        self.collection_name = collection_name or os.getenv(
            "QDRANT_COLLECTION_NAME", "enterprise_rbac_docs"
        )
        self.embedding_model_name = embedding_model_name or os.getenv(
            "EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"
        )
        self._client: Optional[QdrantClient] = None
        self._encoder = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.qdrant_url, check_compatibility=False)
        return self._client

    @property
    def encoder(self):
        # Lazy loading keeps policy/fusion unit tests independent of model downloads.
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(self.embedding_model_name)
        return self._encoder

    def _build_rbac_filter(self, user_roles: List[str], user_clearance: int) -> models.Filter:
        """Require role intersection and document clearance <= user clearance."""
        normalized_roles = sorted(
            {role.strip().lower() for role in user_roles if role and role.strip()}
        )
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="allowed_roles",
                    match=models.MatchAny(any=normalized_roles),
                ),
                models.FieldCondition(
                    key="clearance_level",
                    range=models.Range(lte=user_clearance),
                ),
            ]
        )

    @staticmethod
    def _format_point(point: Any) -> Dict[str, Any]:
        payload = point.payload or {}
        return {
            "id": point.id,
            "score": float(getattr(point, "score", 0.0) or 0.0),
            "text": payload.get("text", ""),
            "source": payload.get("source", "unknown"),
            "doc_id": payload.get("doc_id"),
            "allowed_roles": payload.get("allowed_roles", []),
            "clearance_level": payload.get("clearance_level"),
        }

    def search_dense_with_rbac(
        self, query: str, user_roles: List[str], user_clearance: int, top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """Run similarity-ranked dense search with Qdrant-side policy filtering."""
        if not user_roles or user_clearance < 1 or top_k < 1 or not query.strip():
            return []
        query_vector = self.encoder.encode(query, convert_to_tensor=False).tolist()
        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=self._build_rbac_filter(user_roles, user_clearance),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return [self._format_point(hit) for hit in hits]

    def list_authorized_with_rbac(
        self, user_roles: List[str], user_clearance: int
    ) -> List[Dict[str, Any]]:
        """
        Page through the authorized corpus for BM25 ranking.

        This reference implementation is intended for a small demo corpus. For
        large corpora, use a dedicated lexical index or native sparse retrieval
        rather than scanning every authorized payload for each question.
        """
        if not user_roles or user_clearance < 1:
            return []
        query_filter = self._build_rbac_filter(user_roles, user_clearance)
        points: List[Dict[str, Any]] = []
        offset = None
        while True:
            page, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points.extend(
                self._format_point(point)
                for point in page
                if (point.payload or {}).get("text")
            )
            if offset is None:
                break
        return points

    def search_with_rbac(
        self, query: str, user_roles: List[str], user_clearance: int, top_k: int = 4
    ) -> List[Dict[str, Any]]:
        """Backward-compatible alias for policy-filtered dense retrieval."""
        return self.search_dense_with_rbac(
            query=query, user_roles=user_roles, user_clearance=user_clearance, top_k=top_k
        )
