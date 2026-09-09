"""RAG: chunk a resume's text, embed it, and store/retrieve it in a Chroma
collection scoped to the JD it was uploaded against - one collection per JD,
chunks tagged with resume_id so multiple resumes coexist in the same
collection without stepping on each other.

Retrieval is skill-driven: Phase 7's scoring prompt asks for the chunks most
relevant to each of the JD's must-have skills, rather than feeding the whole
resume into the prompt, to keep long resumes within the token budget.
"""

import logging

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.core.config import get_settings
from backend.llm.factory import get_embeddings

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100
_DEFAULT_K_PER_SKILL = 4


def _collection_name(jd_id: int) -> str:
    return f"jd_{jd_id}"


def get_collection(jd_id: int) -> Chroma:
    """The Chroma collection scoped to one JD, auto-created on first use."""
    settings = get_settings()
    settings.ensure_data_dirs()
    return Chroma(
        collection_name=_collection_name(jd_id),
        embedding_function=get_embeddings(),
        persist_directory=str(settings.CHROMA_DIR),
    )


def chunk_text(text: str) -> list[str]:
    """Split resume text into overlapping chunks for embedding."""
    if not text or not text.strip():
        return []
    splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)
    return splitter.split_text(text)


def index_resume(jd_id: int, resume_id: int, text: str) -> int:
    """(Re-)embed one resume's text into the JD's collection.

    Any chunks already indexed for this resume (e.g. from a previous
    processing attempt) are deleted first, so reprocessing doesn't
    accumulate stale duplicates. Returns the number of chunks indexed.
    """
    collection = get_collection(jd_id)
    _delete_resume_chunks(collection, resume_id)

    chunks = chunk_text(text)
    if not chunks:
        logger.warning("No chunks to index for resume_id=%s (empty text)", resume_id)
        return 0

    ids = [f"{resume_id}-{i}" for i in range(len(chunks))]
    metadatas = [{"resume_id": resume_id, "chunk_index": i} for i in range(len(chunks))]
    collection.add_texts(texts=chunks, metadatas=metadatas, ids=ids)
    return len(chunks)


def _delete_resume_chunks(collection: Chroma, resume_id: int) -> None:
    try:
        collection.delete(where={"resume_id": resume_id})
    except Exception:
        logger.debug("No existing chunks to delete for resume_id=%s", resume_id, exc_info=True)


def retrieve_relevant_chunks(
    jd_id: int, resume_id: int, query: str, k: int = _DEFAULT_K_PER_SKILL
) -> list[str]:
    """Top-k chunks of ONE resume most relevant to `query` (typically a
    skill name), scoped to the JD's collection.
    """
    collection = get_collection(jd_id)
    docs = collection.similarity_search(query, k=k, filter={"resume_id": resume_id})
    return [doc.page_content for doc in docs]


def retrieve_relevant_chunks_for_skills(
    jd_id: int, resume_id: int, skills: list[str], k_per_skill: int = _DEFAULT_K_PER_SKILL
) -> dict[str, list[str]]:
    """One retrieval per must-have skill - what Phase 7's scoring prompt
    consumes directly, so it only ever sees resume text relevant to a given
    skill rather than the whole resume.
    """
    return {skill: retrieve_relevant_chunks(jd_id, resume_id, skill, k=k_per_skill) for skill in skills}
