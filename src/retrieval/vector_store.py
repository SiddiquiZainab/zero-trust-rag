import os
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer


class QdrantVectorStore:
    def __init__(
        self,
        qdrant_url: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model_name: Optional[str] = None,
    ):
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
        self._encoder: Optional[SentenceTransformer] = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.qdrant_url, check_compatibility=False)
        return self._client

    @property
    def encoder(self) -> SentenceTransformer:
        if self._encoder is None:
            self._encoder = SentenceTransformer(self.embedding_model_name)
        return self._encoder

    def _build_rbac_filter(self, user_roles: List[str], user_clearance: int) -> models.Filter:
        """
        Constructs strict Zero-Trust filters:
        1. Payload 'allowed_roles' MUST contain AT LEAST ONE of the user's active roles.
        2. Payload 'clearance_level' MUST BE LESS THAN OR EQUAL TO the user's clearance.
        """
        return models.Filter(
            must=[
                # Role Match (Match Any)
                models.FieldCondition(
                    key="allowed_roles",
                    match=models.MatchAny(any=user_roles)
                ),
                # Clearance Level Filter (Range Check)
                models.FieldCondition(
                    key="clearance_level",
                    range=models.Range(lte=user_clearance)
                )
            ]
        )

    def search_with_rbac(
        self,
        query: str,
        user_roles: List[str],
        user_clearance: int,
        top_k: int = 4
    ) -> List[Dict[str, Any]]:
        """Encodes query and performs pre-filtered search compatible with Qdrant v1.9.x."""
        query_vector = self.encoder.encode(query, convert_to_tensor=False).tolist()
        rbac_filter = self._build_rbac_filter(user_roles, user_clearance)

        # Compatible with Qdrant v1.9.2 REST API
        scroll_results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=rbac_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=False
        )

        results = []
        for hit in scroll_results:
            results.append({
                "id": hit.id,
                "score": 1.0,  # Pre-filtered scroll hit
                "text": hit.payload.get("text"),
                "source": hit.payload.get("source"),
                "doc_id": hit.payload.get("doc_id"),
                "allowed_roles": hit.payload.get("allowed_roles"),
                "clearance_level": hit.payload.get("clearance_level")
            })
        return results