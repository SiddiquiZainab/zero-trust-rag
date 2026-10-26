import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from rank_bm25 import BM25Okapi

from src.retrieval.vector_store import QdrantVectorStore


def tokenize(text: str) -> List[str]:
    """Small tokenizer shared by BM25 ranking and unit tests."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[Mapping[str, Any]]], top_k: int = 4, rrf_k: int = 60
) -> List[Dict[str, Any]]:
    """Merge ranked lists with Reciprocal Rank Fusion."""
    if top_k < 1:
        return []
    fused: Dict[str, Dict[str, Any]] = {}
    for ranking in rankings:
        seen_in_ranking = set()
        for rank, hit in enumerate(ranking, start=1):
            fallback_key = "|".join(
                str(hit.get(field, "")) for field in ("source", "doc_id", "text")
            )
            key = str(hit.get("id") or fallback_key)
            if key in seen_in_ranking:
                continue
            seen_in_ranking.add(key)
            if key not in fused:
                fused[key] = dict(hit)
                fused[key]["score"] = 0.0
            fused[key]["score"] += 1.0 / (rrf_k + rank)
    return sorted(fused.values(), key=lambda item: item["score"], reverse=True)[:top_k]


def rank_with_bm25(
    query: str, authorized_documents: Sequence[Mapping[str, Any]], top_k: int
) -> List[Dict[str, Any]]:
    """Rank only the already-authorized document set with BM25."""
    terms = tokenize(query)
    if not terms or not authorized_documents or top_k < 1:
        return []
    tokenized_corpus = [tokenize(str(doc.get("text", ""))) for doc in authorized_documents]
    if not any(tokenized_corpus):
        return []
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(terms)
    ranked = []
    for index, score in enumerate(scores):
        numeric_score = float(score)
        if numeric_score <= 0:
            continue
        document = dict(authorized_documents[index])
        document["bm25_score"] = numeric_score
        document["score"] = numeric_score
        ranked.append(document)
    return sorted(ranked, key=lambda item: item["bm25_score"], reverse=True)[:top_k]


class HybridSearchEngine:
    """Combine policy-filtered dense retrieval and BM25 using RRF."""

    def __init__(self, vector_store: QdrantVectorStore = None):
        self.vector_store = vector_store or QdrantVectorStore()

    def retrieve_context(
        self, query: str, user_roles: List[str], user_clearance: int, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        if not query or not query.strip() or not user_roles or top_k < 1:
            return []
        candidate_k = max(20, top_k * 4)
        dense_hits = self.vector_store.search_dense_with_rbac(
            query=query, user_roles=user_roles, user_clearance=user_clearance,
            top_k=candidate_k,
        )
        # The same authorization predicate is applied before BM25 sees payloads.
        authorized_documents = self.vector_store.list_authorized_with_rbac(
            user_roles=user_roles, user_clearance=user_clearance
        )
        lexical_hits = rank_with_bm25(query, authorized_documents, candidate_k)
        return reciprocal_rank_fusion([dense_hits, lexical_hits], top_k=top_k)

    @staticmethod
    def format_context_for_llm(search_results: List[Dict[str, Any]]) -> str:
        """Format authorized chunks with source labels for answer grounding."""
        if not search_results:
            return "NO ACCESSIBLE CONTEXT FOUND."
        formatted_chunks = []
        for idx, item in enumerate(search_results, 1):
            source = item.get("source") or "unknown source"
            doc_id = item.get("doc_id") or "unknown"
            text = item.get("text") or ""
            formatted_chunks.append(f"[Source {idx}: {source} (Doc ID: {doc_id})]\n{text}")
        return "\n\n".join(formatted_chunks)
