"""
services/rag_ingestion.py — RAG Document Ingestion Pipeline

Processes extracted text (from PDFs, images, videos) and stores it in
Pinecone for retrieval by the Self-RAG pipeline.

Flow:
  1. Split text into overlapping chunks (RecursiveCharacterTextSplitter)
  2. Embed chunks using Ollama's nomic-embed-text model (local)
  3. Upsert embeddings + metadata into Pinecone
"""

from __future__ import annotations

import uuid
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

from config import PINECONE_API_KEY, PINECONE_INDEX_NAME, OLLAMA_BASE_URL

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIMENSION = 768  # nomic-embed-text output dimension
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# ---------------------------------------------------------------------------
# Lazy-initialized singletons
# ---------------------------------------------------------------------------

_embeddings: Optional[OllamaEmbeddings] = None
_vector_store: Optional[PineconeVectorStore] = None
_text_splitter: Optional[RecursiveCharacterTextSplitter] = None


def _get_text_splitter() -> RecursiveCharacterTextSplitter:
    """Returns a cached text splitter instance."""
    global _text_splitter
    if _text_splitter is None:
        _text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            length_function=len,
            is_separator_regex=False,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
    return _text_splitter


def _get_embeddings() -> OllamaEmbeddings:
    """Returns a cached Ollama embeddings instance."""
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings(
            model=EMBEDDING_MODEL,
            base_url=OLLAMA_BASE_URL,
        )
        print(f"[RAG Ingestion] Ollama embeddings initialized: {EMBEDDING_MODEL} @ {OLLAMA_BASE_URL}")
    return _embeddings


def _get_vector_store() -> PineconeVectorStore:
    """Returns a cached Pinecone vector store, creating the index if needed."""
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    if not PINECONE_API_KEY:
        raise RuntimeError(
            "PINECONE_API_KEY is not set. Cannot initialize the vector store. "
            "Please add it to your .env file."
        )

    pc = Pinecone(api_key=PINECONE_API_KEY)

    # Ensure the index exists
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing_indexes:
        print(f"[RAG Ingestion] Creating Pinecone index: {PINECONE_INDEX_NAME} (dim={EMBEDDING_DIMENSION})")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    else:
        print(f"[RAG Ingestion] Using existing Pinecone index: {PINECONE_INDEX_NAME}")

    _vector_store = PineconeVectorStore(
        index=pc.Index(PINECONE_INDEX_NAME),
        embedding=_get_embeddings(),
    )

    print(f"[RAG Ingestion] Vector store initialized on index: {PINECONE_INDEX_NAME}")
    return _vector_store


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_and_store_document(
    extracted_text: str,
    source_metadata: str,
) -> dict:
    """
    Splits extracted text into chunks, embeds them via Ollama nomic-embed-text,
    and upserts them into the Pinecone vector store with source metadata.

    Args:
        extracted_text: The full text extracted from a PDF, image, or video.
        source_metadata: A label for the source (e.g., filename, URL).

    Returns:
        A dict with ingestion stats:
        {
            "status": "success",
            "source": "lecture_notes.pdf",
            "chunks_created": 12,
            "index_name": "teacher-ai"
        }

    Raises:
        RuntimeError: If Pinecone API key is missing.
        ValueError: If extracted_text is empty.
    """
    if not extracted_text or not extracted_text.strip():
        raise ValueError("Cannot ingest empty text.")

    print(f"[RAG Ingestion] Processing document: {source_metadata}")
    print(f"[RAG Ingestion] Input text length: {len(extracted_text)} chars")

    # --- Task 1: Split text into chunks ---
    splitter = _get_text_splitter()
    chunks = splitter.split_text(extracted_text)
    print(f"[RAG Ingestion] Split into {len(chunks)} chunks (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")

    if not chunks:
        print("[RAG Ingestion] WARNING: Text splitter produced 0 chunks.")
        return {
            "status": "warning",
            "source": source_metadata,
            "chunks_created": 0,
            "index_name": PINECONE_INDEX_NAME,
        }

    # --- Task 2 + 3: Embed and upsert into Pinecone ---
    vector_store = _get_vector_store()

    # Build metadata for each chunk
    metadatas = [
        {
            "source": source_metadata,
            "chunk_index": i,
            "total_chunks": len(chunks),
        }
        for i in range(len(chunks))
    ]

    # Generate unique IDs for each chunk
    doc_id = str(uuid.uuid4())[:8]
    ids = [f"{doc_id}-chunk-{i}" for i in range(len(chunks))]

    # Upsert into Pinecone via LangChain
    vector_store.add_texts(
        texts=chunks,
        metadatas=metadatas,
        ids=ids,
    )

    print(f"[RAG Ingestion] ✅ Upserted {len(chunks)} chunks to Pinecone index: {PINECONE_INDEX_NAME}")
    print(f"[RAG Ingestion]    Source metadata: {source_metadata}")

    return {
        "status": "success",
        "source": source_metadata,
        "chunks_created": len(chunks),
        "index_name": PINECONE_INDEX_NAME,
    }
