from typing import List, Dict, Any
from src.retrieval.hybrid_search import HybridSearchEngine
from src.engine.llm import OllamaLLM

class RAGChain:
    SYSTEM_PROMPT = """You are a Zero-Trust enterprise AI assistant.
Your task is to answer the user's question accurately using ONLY the provided contexts below.

RULES:
1. Ground your answer strictly on the provided context chunks.
2. If the context does NOT contain enough information to answer the question, state: "I do not have access to sufficient information to answer this question."
3. Never state or leak information from outside the provided context.
4. Keep the response factual, concise, and professional."""

    def __init__(self, search_engine: HybridSearchEngine = None, llm: OllamaLLM = None):
        self.search_engine = search_engine or HybridSearchEngine()
        self.llm = llm or OllamaLLM()

    def run(
        self,
        query: str,
        user_roles: List[str],
        user_clearance: int
    ) -> Dict[str, Any]:
        """
        Executes end-to-end RAG with Zero-Trust access control:
        1. Pre-filter retrieval based on user_roles and clearance.
        2. Format prompt with context guardrails.
        3. Generate LLM answer.
        """
        # 1. Retrieve filtered context chunks
        retrieved_docs = self.search_engine.retrieve_context(
            query=query,
            user_roles=user_roles,
            user_clearance=user_clearance,
            top_k=4
        )

        # 2. Format context for prompt
        formatted_context = self.search_engine.format_context_for_llm(retrieved_docs)

        # 3. Construct user prompt with context injection
        full_prompt = f"CONTEXT:\n{formatted_context}\n\nUSER QUESTION: {query}"

        # 4. Generate answer via LLM wrapper
        raw_response = self.llm.generate(
            prompt=full_prompt,
            system_prompt=self.SYSTEM_PROMPT
        )

        return {
            "query": query,
            "answer": raw_response,
            "accessed_documents": [doc["source"] for doc in retrieved_docs],
            "context_chunks_count": len(retrieved_docs)
        }

if __name__ == "__main__":
    # --- Integration Test for RAG Chain ---
    rag_chain = RAGChain()

    query = "What is the policy regarding Q3 bonus payouts?"

    print("==================================================")
    print("TEST 1: Low Clearance User (engineering, clearance 1)")
    print("==================================================")
    res_low = rag_chain.run(
        query=query,
        user_roles=["engineering"],
        user_clearance=1
    )
    print(f"Answer:\n{res_low['answer']}\n")
    print(f"Accessed Files: {res_low['accessed_documents']}\n")

    print("==================================================")
    print("TEST 2: High Clearance User (hr, clearance 4)")
    print("==================================================")
    res_high = rag_chain.run(
        query=query,
        user_roles=["hr"],
        user_clearance=4
    )
    print(f"Answer:\n{res_high['answer']}\n")
    print(f"Accessed Files: {res_high['accessed_documents']}\n")