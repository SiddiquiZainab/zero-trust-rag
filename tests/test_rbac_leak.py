import pytest
from src.engine.rag_chain import RAGChain


@pytest.fixture(scope="module")
def rag_chain():
    """Shared fixture for initializing the RAG Chain."""
    return RAGChain()


def test_zero_leakage_low_clearance_user(rag_chain):
    """
    SECURITY TEST: An engineering user with Clearance 1 asks about executive bonuses.
    Must guarantee ZERO document leakage and standard insufficient info response.
    """
    sensitive_query = "What is the exact percentage payout for the Q3 executive bonus?"

    response = rag_chain.run(
        query=sensitive_query,
        user_roles=["engineering"],
        user_clearance=1
    )

    # 1. Check Retrieval Level Leakage
    accessed_files = response.get("accessed_documents", [])
    for file_name in accessed_files:
        assert "q3_bonus_policy" not in file_name, f"LEAK DETECTED: Low clearance user accessed restricted file: {file_name}"

    # 2. Check LLM Generation Leakage
    answer_text = response.get("answer", "").lower()
    assert "i do not have access" in answer_text or "insufficient information" in answer_text, \
        "SECURITY FAILURE: Model did not explicitly decline or report missing context for unauthorized query."


def test_authorized_access_high_clearance_user(rag_chain):
    """
    VERIFICATION TEST: An HR user with Clearance 4 asks about executive bonuses.
    Must return accurate context and answer.
    """
    sensitive_query = "What is the policy regarding Q3 bonus payouts?"

    response = rag_chain.run(
        query=sensitive_query,
        user_roles=["hr"],
        user_clearance=4
    )

    accessed_files = response.get("accessed_documents", [])
    assert any("q3_bonus_policy" in f for f in
               accessed_files), "Authorized HR user failed to retrieve required restricted file."
    assert len(response.get("answer", "")) > 10, "Model failed to provide answer for authorized query."