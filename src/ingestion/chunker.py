import os
import uuid
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_URL = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "enterprise_rbac_docs")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5")
VECTOR_DIMENSION = 384

_encoder = None
_qdrant = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
        _encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _encoder


def _get_qdrant():
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=QDRANT_URL, check_compatibility=False)
    return _qdrant


def setup_qdrant_collection():
    """Ensure the Qdrant collection exists with the expected vector configuration."""
    qdrant = _get_qdrant()
    if not qdrant.collection_exists(COLLECTION_NAME):
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_DIMENSION,
                distance=models.Distance.COSINE,
            ),
        )
        print(f"Created collection: {COLLECTION_NAME}")
    else:
        print(f"Collection {COLLECTION_NAME} already exists.")


def ingest_document(
    text: str,
    doc_id: str,
    allowed_roles: List[str],
    clearance_level: int,
    source_name: str,
):
    """Chunk, embed and replace a document's indexed chunks with its current policy."""
    if not text.strip():
        raise ValueError("Cannot index an empty document.")
    if not allowed_roles:
        raise ValueError("At least one allowed role is required.")
    # Clearance 0 is valid for public documents in data/manifest.json.
    if not 0 <= clearance_level <= 5:
        raise ValueError("clearance_level must be between 0 and 5.")

    encoder = _get_encoder()
    qdrant = _get_qdrant()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=50,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_text(text)
    if not chunks:
        raise ValueError("The document produced no indexable chunks.")
    print(f"Split document '{source_name}' into {len(chunks)} chunks.")

    embeddings = encoder.encode(chunks, convert_to_tensor=False)
    points = []
    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        points.append(
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding.tolist() if hasattr(embedding, "tolist") else list(embedding),
                payload={
                    "doc_id": doc_id,
                    "chunk_index": index,
                    "text": chunk,
                    "source": source_name,
                    "allowed_roles": allowed_roles,
                    "clearance_level": clearance_level,
                },
            )
        )

    # Important for re-uploads: remove prior chunks with this stable doc_id before
    # inserting the new policy. Otherwise old chunks can retain stale permissions.
    qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id),
                    )
                ]
            )
        ),
        wait=True,
    )
    qdrant.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)
    print(f"Successfully ingested {len(points)} vectors for '{source_name}'.\n")


if __name__ == "__main__":
    setup_qdrant_collection()
    sample_hr_doc = """
    CONFIDENTIAL: Q3 Bonus Restructuring.
    Starting Q3, management bonuses will be tied to team retention metrics.
    HR personnel are required to finalize the payout matrix by November 1st.
    """
    sample_eng_doc = """
    Architecture Decision Record (ADR) 44:
    We are migrating our internal microservices to use gRPC over REST.
    All backend engineers must update their endpoints by the end of the sprint.
    """
    ingest_document(
        text=sample_hr_doc,
        doc_id="doc-hr-001",
        allowed_roles=["hr", "management"],
        clearance_level=4,
        source_name="q3_bonus_policy.txt",
    )
    ingest_document(
        text=sample_eng_doc,
        doc_id="doc-eng-044",
        allowed_roles=["engineering", "management"],
        clearance_level=2,
        source_name="adr_44_grpc.txt",
    )
