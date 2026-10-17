from citedesk.answer.bm25 import Bm25Index
from citedesk.answer.fusion import reciprocal_rank_fusion
from citedesk.domain.ports import IndexItem
from citedesk.storage.dev_adapters import HashingEmbedder, InMemoryVectorIndex


def test_bm25_prefers_the_document_with_the_rare_matching_word() -> None:
    index = Bm25Index(
        {
            "a": "the policy covers vacation days and sick days",
            "b": "the policy covers expense reports",
            "c": "the policy covers parental leave",
        }
    )
    ranked = index.search("vacation policy", limit=3)
    assert ranked[0][0] == "a"


def test_bm25_leaves_out_documents_with_no_matching_word() -> None:
    index = Bm25Index({"a": "alpha beta", "b": "gamma delta"})
    assert [doc_id for doc_id, _ in index.search("alpha", limit=5)] == ["a"]


def test_bm25_on_an_empty_corpus_returns_nothing() -> None:
    assert Bm25Index({}).search("anything", limit=5) == []


def test_fusion_ranks_items_found_by_both_searches_first() -> None:
    fused = reciprocal_rank_fusion([["x", "a", "b"], ["y", "a", "c"]])
    assert fused[0][0] == "a"
    assert {item for item, _ in fused} == {"x", "a", "b", "y", "c"}


def test_vector_index_returns_the_most_similar_vector_and_supports_delete() -> None:
    embedder = HashingEmbedder()
    texts = {"1": "paid vacation days", "2": "laptop return courier"}
    index = InMemoryVectorIndex()
    index.upsert(
        [IndexItem(key, f"doc{key}", embedder.embed([text])[0]) for key, text in texts.items()]
    )
    query = embedder.embed(["how many vacation days"])[0]
    assert index.search(query, limit=2)[0][0] == "1"

    index.delete_document("doc1")
    assert all(chunk_id != "1" for chunk_id, _ in index.search(query, limit=2))
