from typing import List, Dict, Any
from src.retrieval.vector_store import QdrantVectorStore

class HybridSearchEngine:
    def __init__(self, vector_store: QdrantVectorStore = None):
        self.vector_store = vector_store or QdrantVectorStore()

    def retrieve_context(
        self,
        query: str,
        user_roles: List[str],
        user_clearance: int,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Executes secure search with RBAC enforcement and formats retrieved hits
        into usable prompt context.
        """
        hits = self.vector_store.search_with_rbac(
            query=query,
            user_roles=user_roles,
            user_clearance=user_clearance,
            top_k=top_k
        )
        return hits

    def format_context_for_llm(self, search_results: List[Dict[str, Any]]) -> str:
        """Formats filtered search payloads into clean context text for the model prompt."""
        if not search_results:
            return "NO ACCESSIBLE CONTEXT FOUND."

        formatted_chunks = []
        for idx, item in enumerate(search_results, 1):
            formatted_chunks.append(
                f"[Source {idx}: {item['source']} (Doc ID: {item['doc_id']})]\n{item['text']}"
            )
        return "\n\n".join(formatted_chunks)

if __name__ == "__main__":
    # --- Quick Verification Test ---
    engine = HybridSearchEngine()

    print("--- Test 1: Low Clearance User (Role: 'engineering', Clearance: 1) ---")
    results = engine.retrieve_context(
        query="What are the security standards and bonus policy?",
        user_roles=["engineering"],
        user_clearance=1
    )
    print(f"Retrieved {len(results)} chunks.")
    for r in results:
        print(f" - Access Granted to: {r['source']} (Clearance {r['clearance_level']})")

    print("\n--- Test 2: High Clearance User (Role: 'security', Clearance: 4) ---")
    results_high = engine.retrieve_context(
        query="What are the security standards and bonus policy?",
        user_roles=["security", "management"],
        user_clearance=4
    )
    print(f"Retrieved {len(results_high)} chunks.")
    for r in results_high:
        print(f" - Access Granted to: {r['source']} (Clearance {r['clearance_level']})")