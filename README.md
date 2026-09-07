# Zero-Trust RAG

A privacy-first Retrieval-Augmented Generation (RAG) system built on the principle of zero-trust: users only see documents they are explicitly authorized to access. All processing happens on-premises, from embedding to final answer generation.

## How It Works

The system enforces strict access control at every layer. No document is retrieved, processed, or returned unless the requesting user's roles intersect with the document's allowed roles.

### Architecture Flow

```
┌─────────────────┐
│   USER CLIENT   │
│                 │
│ • Authenticates │
│   via JWT/API   │
│   Key           │
│ • Sends query   │
│   + user_id +   │
│   roles         │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│   API GATEWAY / FASTAPI     │
│                             │
│ 1. Validate JWT / Extract   │
│    user roles               │
│ 2. Generate dense embedding │
│    (SentenceTransformers)   │
│ 3. Build BM25 sparse vector │
│    from query tokens         │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│   ON-PREM VECTOR STORE      │
│        (Qdrant)             │
│                             │
│ • Hybrid Search:            │
│   Reciprocal Rank Fusion    │
│   (RRF) of dense + BM25     │
│ • Strict Pre-Filtering:     │
│   Payload match on          │
│   `allowed_roles` INTERSECT │
│   `user_roles`              │
└────────┬────────────────────┘
         │
         │  [ Authorized Documents Only ]
         ▼
┌─────────────────────────────┐
│   LOCAL LLM RUNTIME         │
│   (Ollama / vLLM)           │
│                             │
│ • Fully local models        │
│   (e.g., Llama-3-8B)        │
│ • Context payload grounded  │
│   solely on retrieved       │
│   filtered chunks           │
└─────────────────────────────┘
```

### Zero-Trust Guarantees

- **No cross-tenant leakage**: Documents are filtered by role before any retrieval or generation occurs.
- **On-prem only**: Embeddings, search, and LLM inference all run inside your infrastructure.
- **Auditable**: Every request carries a user identity and role set, enabling full traceability.

## Key Components

| Component | Responsibility |
|-----------|----------------|
| `src/auth/rbac.py` | Role validation and context injection |
| `src/ingestion/chunker.py` | Document parsing and chunking policy |
| `src/ingestion/pipeline.py` | Metadata tagging and batch upload |
| `src/retrieval/vector_store.py` | Qdrant client and collection setup |
| `src/retrieval/hybrid_search.py` | Dense + BM25 fusion with payload filtering |
| `src/engine/llm.py` | Local Ollama/vLLM HTTP wrapper |
| `src/engine/rag_chain.py` | Complete execution pipeline |

## Getting Started

1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in your configuration.
3. Start the stack with Docker Compose:
   ```bash
   docker-compose up
   ```
4. The API will be available at `http://localhost:8000`.

## Security Testing

Run the test suite to verify zero-trust guarantees:

```bash
pytest tests/test_rbac_leak.py -v
pytest tests/test_hybrid_search.py -v
```

- `test_rbac_leak.py` ensures unauthorized data is never returned.
- `test_hybrid_search.py` benchmarks retrieval accuracy.

## License

MIT