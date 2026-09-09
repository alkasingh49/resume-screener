"""RAG tests: real chunking (RecursiveCharacterTextSplitter) and a real
local Chroma collection, with a small deterministic fake embedding model
standing in for the real embeddings API (no network/API key needed). The
fake is keyword-count-based rather than random, so similarity search still
behaves meaningfully - "querying 'Python' ranks the Python chunk first" is
a real assertion, not a coin flip.
"""

import pytest
from langchain_core.embeddings import Embeddings

from backend.services import vectorstore

_VOCAB = ["python", "java", "sql", "docker", "kubernetes", "react", "aws", "cooking", "painting"]


class KeywordEmbeddings(Embeddings):
    """One dimension per keyword in a small fixed vocabulary, valued by how
    many times that keyword appears (case-insensitive), plus a constant bias
    dimension so an all-zero text still gets a valid (non-degenerate)
    vector.
    """

    def _vec(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(word)) for word in _VOCAB] + [1.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@pytest.fixture(autouse=True)
def _db_and_fake_embeddings(isolated_db, monkeypatch):
    """isolated_db already redirects CHROMA_DIR at a temp dir; also swap in
    the keyword fake so no real embeddings API is called.
    """
    monkeypatch.setattr(vectorstore, "get_embeddings", lambda: KeywordEmbeddings())


def test_chunk_text_splits_long_text():
    long_text = "Sentence. " * 500
    chunks = vectorstore.chunk_text(long_text)
    assert len(chunks) > 1
    assert all(len(c) <= vectorstore._CHUNK_SIZE + 50 for c in chunks)  # splitter can overshoot slightly


def test_chunk_text_short_text_is_one_chunk():
    assert vectorstore.chunk_text("Just a short resume snippet.") == ["Just a short resume snippet."]


def test_chunk_text_empty_returns_no_chunks():
    assert vectorstore.chunk_text("") == []
    assert vectorstore.chunk_text("   ") == []


def test_index_and_retrieve_ranks_relevant_chunk_first():
    text = (
        "Experience section. Built backend services in Python using FastAPI and wrote SQL queries "
        "against Postgres for five years.\n\n"
        "Hobbies section. Enjoys cooking Italian food and oil painting on weekends."
    )
    count = vectorstore.index_resume(jd_id=1, resume_id=101, text=text)
    assert count >= 1

    results = vectorstore.retrieve_relevant_chunks(jd_id=1, resume_id=101, query="Python", k=1)
    assert len(results) == 1
    assert "python" in results[0].lower()


def test_retrieval_is_scoped_to_the_given_resume_id():
    vectorstore.index_resume(jd_id=1, resume_id=201, text="Candidate A: expert in Python and Docker.")
    vectorstore.index_resume(jd_id=1, resume_id=202, text="Candidate B: expert in Java and Kubernetes.")

    results_a = vectorstore.retrieve_relevant_chunks(jd_id=1, resume_id=201, query="skills", k=5)
    results_b = vectorstore.retrieve_relevant_chunks(jd_id=1, resume_id=202, query="skills", k=5)

    assert any("Python" in r for r in results_a)
    assert not any("Python" in r for r in results_b)
    assert any("Java" in r for r in results_b)


def test_retrieval_is_scoped_to_the_given_jd_id():
    vectorstore.index_resume(jd_id=10, resume_id=301, text="Candidate: expert in Python.")
    vectorstore.index_resume(jd_id=20, resume_id=301, text="Same candidate, different JD collection: expert in Java.")

    results_jd10 = vectorstore.retrieve_relevant_chunks(jd_id=10, resume_id=301, query="skills", k=5)
    results_jd20 = vectorstore.retrieve_relevant_chunks(jd_id=20, resume_id=301, query="skills", k=5)

    assert any("Python" in r for r in results_jd10)
    assert any("Java" in r for r in results_jd20)
    assert not any("Java" in r for r in results_jd10)


def test_reindexing_a_resume_replaces_old_chunks_not_duplicates():
    vectorstore.index_resume(jd_id=1, resume_id=401, text="Old version: skilled in Python.")
    vectorstore.index_resume(jd_id=1, resume_id=401, text="New version: skilled in Java only.")

    results = vectorstore.retrieve_relevant_chunks(jd_id=1, resume_id=401, query="skills", k=10)
    assert not any("Python" in r for r in results)
    assert any("Java" in r for r in results)


def test_indexing_empty_text_returns_zero_and_does_not_error():
    assert vectorstore.index_resume(jd_id=1, resume_id=501, text="") == 0


def test_retrieve_relevant_chunks_for_skills_returns_one_list_per_skill():
    text = "Backend engineer skilled in Python, SQL, and Docker for containerization."
    vectorstore.index_resume(jd_id=1, resume_id=601, text=text)

    results = vectorstore.retrieve_relevant_chunks_for_skills(
        jd_id=1, resume_id=601, skills=["Python", "Docker"], k_per_skill=1
    )
    assert set(results.keys()) == {"Python", "Docker"}
    assert all(len(chunks) == 1 for chunks in results.values())
