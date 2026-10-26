from src.retrieval.hybrid_search import (
    HybridSearchEngine,
    rank_with_bm25,
    reciprocal_rank_fusion,
)
from src.retrieval.vector_store import QdrantVectorStore


def hit(point_id, text, source="demo.txt"):
    return {
        "id": point_id,
        "text": text,
        "source": source,
        "doc_id": point_id,
        "allowed_roles": ["engineering"],
        "clearance_level": 1,
        "score": 0.5,
    }


def test_rrf_promotes_a_result_present_in_both_rankings():
    dense = [hit("a", "alpha"), hit("b", "beta"), hit("c", "gamma")]
    lexical = [hit("b", "beta"), hit("c", "gamma"), hit("d", "delta")]
    results = reciprocal_rank_fusion([dense, lexical], top_k=4)
    assert results[0]["id"] == "b"
    assert results[1]["id"] == "c"
    assert len(results) == 4


def test_bm25_ranks_query_terms_above_unrelated_documents():
    documents = [
        hit("unrelated", "gardening tips and soil moisture"),
        hit("matching", "quarterly revenue report and revenue forecast"),
    ]
    results = rank_with_bm25("quarterly revenue report", documents, top_k=2)
    assert results
    assert results[0]["id"] == "matching"


def test_hybrid_engine_calls_both_authorized_retrievers():
    class FakeVectorStore:
        def __init__(self):
            self.dense_called = False
            self.lexical_called = False

        def search_dense_with_rbac(self, query, user_roles, user_clearance, top_k):
            self.dense_called = True
            assert user_roles == ["engineering"]
            assert user_clearance == 2
            return [hit("shared", "security policy"), hit("dense-only", "other")]

        def list_authorized_with_rbac(self, user_roles, user_clearance):
            self.lexical_called = True
            assert user_roles == ["engineering"]
            assert user_clearance == 2
            return [
                hit("shared", "security policy and access control"),
                hit("lexical-only", "security policy access control"),
            ]

    store = FakeVectorStore()
    engine = HybridSearchEngine(vector_store=store)
    results = engine.retrieve_context(
        query="security policy access control",
        user_roles=["engineering"],
        user_clearance=2,
        top_k=3,
    )
    assert store.dense_called
    assert store.lexical_called
    assert results[0]["id"] == "shared"
    assert len(results) == 3


def test_empty_roles_fail_closed_without_retrieval():
    class ExplodingVectorStore:
        def search_dense_with_rbac(self, **kwargs):
            raise AssertionError("Dense retrieval should not run without roles.")

        def list_authorized_with_rbac(self, **kwargs):
            raise AssertionError("Lexical retrieval should not run without roles.")

    engine = HybridSearchEngine(vector_store=ExplodingVectorStore())
    assert engine.retrieve_context(
        query="anything", user_roles=[], user_clearance=5, top_k=3
    ) == []


def test_empty_fusion_inputs_return_no_results():
    assert reciprocal_rank_fusion([[], []], top_k=3) == []


def test_rbac_filter_requires_role_and_clearance():
    store = QdrantVectorStore()
    query_filter = store._build_rbac_filter(
        ["Engineering", "engineering", " HR "], user_clearance=3
    )
    assert len(query_filter.must) == 2
    assert query_filter.must[0].key == "allowed_roles"
    assert set(query_filter.must[0].match.any) == {"engineering", "hr"}
    assert query_filter.must[1].key == "clearance_level"
    assert query_filter.must[1].range.lte == 3



def test_dense_search_uses_filtered_query_points_api():
    from types import SimpleNamespace

    class Encoder:
        def encode(self, query, convert_to_tensor=False):
            assert query == "security policy"
            return [0.1, 0.2, 0.3]

    class FakeClient:
        def __init__(self):
            self.kwargs = None

        def query_points(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(points=[
                SimpleNamespace(
                    id="p1",
                    score=0.91,
                    payload={
                        "text": "Security policy",
                        "source": "security.txt",
                        "doc_id": "doc-security",
                        "allowed_roles": ["engineering"],
                        "clearance_level": 2,
                    },
                )
            ])

    store = QdrantVectorStore()
    fake_client = FakeClient()
    store._client = fake_client
    store._encoder = Encoder()

    results = store.search_dense_with_rbac(
        query="security policy",
        user_roles=["engineering"],
        user_clearance=2,
        top_k=5,
    )

    assert fake_client.kwargs["limit"] == 5
    assert fake_client.kwargs["with_payload"] is True
    assert len(fake_client.kwargs["query_filter"].must) == 2
    assert results[0]["id"] == "p1"
    assert results[0]["score"] == 0.91
