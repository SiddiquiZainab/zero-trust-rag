from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models

class QdrantVectorStore:
    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "zero_trust_documents",
        embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    ):
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self.client = QdrantClient(url=qdrant_url, check_compatibility=False)
        self.encoder = SentenceTransformer(embedding_model_name)

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