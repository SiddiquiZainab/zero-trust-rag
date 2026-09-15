import pytest
from src.retrieval.hybrid_search import HybridSearchEngine


@pytest.fixture(scope="module")
def search_engine():
    """Shared fixture for initializing the search engine."""
    return HybridSearchEngine()


def test_engineering_user_retrieval(search_engine):
    """Low clearance engineering user should only see tech/public docs."""
    results = search_engine.retrieve_context(
        query="What are the engineering guidelines, architecture, or codebase standards?",
        user_roles=["engineering"],
        user_clearance=1,
        top_k=5
    )

    assert len(results) > 0, "Engine should return relevant engineering contexts."
    for doc in results:
        # User clearance must meet or exceed document clearance requirement
        assert user_clearance_valid(doc["clearance_level"], 1)
        # User must possess at least one role specified in allowed_roles (or 'public')
        assert role_authorized(doc["allowed_roles"], ["engineering"])


def test_hr_user_high_clearance_retrieval(search_engine):
    """High clearance HR user should be able to access restricted HR documents."""
    results = search_engine.retrieve_context(
        query="What is the Q3 bonus payout policy?",
        user_roles=["hr"],
        user_clearance=4,
        top_k=5
    )

    assert len(results) > 0, "High clearance HR user should retrieve bonus documents."
    doc_sources = [doc["source"] for doc in results]
    assert any("q3_bonus_policy" in src for src in doc_sources), "HR user should see q3_bonus_policy document."


def role_authorized(doc_roles, user_roles):
    if "public" in doc_roles:
        return True
    return any(r in doc_roles for r in user_roles)


def user_clearance_valid(doc_clearance, user_clearance):
    return user_clearance >= doc_clearance