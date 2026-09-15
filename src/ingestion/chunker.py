import uuid
from typing import List
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http import models

# --- Configuration ---
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "zero_trust_documents"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
VECTOR_DIMENSION = 384  # BGE-small outputs 384-dimensional vectors

# --- Initialize Clients ---
print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
qdrant = QdrantClient(url=QDRANT_URL)


def setup_qdrant_collection():
    """Ensure the Qdrant collection exists with the correct vector configuration."""
    if not qdrant.collection_exists(COLLECTION_NAME):
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_DIMENSION,
                distance=models.Distance.COSINE
            )
        )
        print(f"Created collection: {COLLECTION_NAME}")
    else:
        print(f"Collection {COLLECTION_NAME} already exists.")


def ingest_document(
        text: str,
        doc_id: str,
        allowed_roles: List[str],
        clearance_level: int,
        source_name: str
):
    """Chunks text, embeds it, and uploads to Qdrant with RBAC payloads."""

    # 1. Chunking
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=50,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = splitter.split_text(text)
    print(f"Split document '{source_name}' into {len(chunks)} chunks.")

    # 2. Embedding
    # SentenceTransformer handles batching automatically for lists of strings
    embeddings = encoder.encode(chunks, convert_to_tensor=False)

    # 3. Payload Construction & Upload
    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())

        # Attach mandatory access control attributes
        payload = {
            "doc_id": doc_id,
            "chunk_index": i,
            "text": chunk,
            "source": source_name,
            # RBAC Metadata
            "allowed_roles": allowed_roles,
            "clearance_level": clearance_level
        }

        points.append(
            models.PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload=payload
            )
        )

    # 4. Upsert to Qdrant
    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )
    print(f"Successfully ingested {len(points)} vectors for '{source_name}'.\n")


if __name__ == "__main__":
    setup_qdrant_collection()

    # --- Sample Execution ---
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

    # Ingest HR Document (Restricted to HR and Management, High Clearance)
    ingest_document(
        text=sample_hr_doc,
        doc_id="doc-hr-001",
        allowed_roles=["hr", "management"],
        clearance_level=4,
        source_name="q3_bonus_policy.txt"
    )

    # Ingest Engineering Document (Broader access, Lower Clearance)
    ingest_document(
        text=sample_eng_doc,
        doc_id="doc-eng-044",
        allowed_roles=["engineering", "management"],
        clearance_level=2,
        source_name="adr_44_grpc.txt"
    )