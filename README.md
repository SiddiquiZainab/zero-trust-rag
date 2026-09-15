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

## Prerequisites

- **Docker** and **Docker Compose** (v2.0+)
- **Git** for cloning the repository
- **4GB+ RAM** available for containers (8GB+ recommended for LLM)
- **Ports 6333, 6334, 8000, 11434** available on host

## Quick Start (Docker Compose)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd zero-trust-rag
```

### 2. Configure Environment Variables

Create a `.env` file in the project root with your configuration:

```bash
# JWT Secret (CHANGE IN PRODUCTION!)
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production

# Qdrant Vector Database
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Ollama LLM Service
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3

# Embedding Model
EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
```

### 3. Start the Stack

```bash
# Build and start all services
docker-compose -f docker/docker-compose.yml up --build -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Check service health
docker-compose -f docker/docker-compose.yml ps
```

### 4. Pull the LLM Model (First Run)

```bash
# Pull the default llama3 model into Ollama
docker exec zero_trust_ollama ollama pull llama3

# Or pull a different model
docker exec zero_trust_ollama ollama pull mistral
```

### 5. Ingest Documents

```bash
# Run the ingestion pipeline to populate the vector store
docker exec zero_trust_fastapi python -m src.ingestion.pipeline
```

### 6. Access the Services

| Service | URL | Description |
|---------|-----|-------------|
| **API** | http://localhost:8000 | FastAPI REST API |
| **API Docs** | http://localhost:8000/docs | Swagger UI |
| **Streamlit UI** | http://localhost:8501 | Web chat interface |
| **Qdrant Dashboard** | http://localhost:6333/dashboard | Vector DB management |
| **Ollama API** | http://localhost:11434 | LLM inference endpoint |

## Manual Development Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Start Required Services

```bash
# Start Qdrant (vector database)
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant:v1.9.2

# Start Ollama (LLM runtime)
docker run -d --name ollama -p 11434:11434 -v ollama_data:/root/.ollama ollama/ollama:latest
docker exec ollama ollama pull llama3
```

### 4. Configure Environment

```bash
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=llama3
export JWT_SECRET_KEY=your-secret-key
```

### 5. Ingest Documents

```bash
python -m src.ingestion.pipeline
```

### 6. Run the API Server

```bash
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 7. Run the Streamlit UI (Optional)

```bash
streamlit run ui/app.py
```

## API Usage

### Authentication

```bash
# Get access token
curl -X POST "http://localhost:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice_eng&password=password123"

# Response: {"access_token": "eyJ...", "token_type": "bearer"}
```

### Query the RAG Engine

```bash
# Use the token from authentication
curl -X POST "http://localhost:8000/query" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the security policy for data handling?"}'
```

### Health Check

```bash
curl http://localhost:8000/health
```

## Default Test Users

| Username | Password | Roles | Clearance |
|----------|----------|-------|-----------|
| `alice_eng` | `password123` | `["engineering"]` | 1 |
| `bob_hr` | `password123` | `["hr"]` | 4 |

## Project Structure

```
zero-trust-rag/
├── .dockerignore           # Docker ignore patterns
├── .gitignore              # Git ignore patterns
├── README.md               # This file
├── requirements.txt        # Python dependencies
├── data/                   # Document data & manifests
│   ├── manifest.json       # Document metadata & RBAC config
│   ├── security_policy.txt
│   └── ...
├── docker/                 # Docker configuration
│   ├── docker-compose.yml  # Multi-service orchestration
│   ├── Dockerfile.api      # FastAPI service image
│   └── Dockerfile.llm      # Ollama LLM service image
├── src/                    # Source code
│   ├── __init__.py
│   ├── config.py           # Centralized configuration (Pydantic Settings)
│   ├── main.py             # FastAPI application entry point
│   ├── auth/               # Authentication & RBAC
│   │   ├── __init__.py
│   │   └── rbac.py
│   ├── engine/             # RAG execution engine
│   │   ├── __init__.py
│   │   ├── llm.py          # Ollama LLM wrapper
│   │   └── rag_chain.py    # End-to-end RAG pipeline
│   ├── ingestion/          # Document ingestion pipeline
│   │   ├── __init__.py
│   │   ├── chunker.py      # Text chunking & embedding
│   │   └── pipeline.py     # Batch ingestion orchestrator
│   └── retrieval/          # Vector search & retrieval
│       ├── __init__.py
│       ├── hybrid_search.py # Dense + BM25 hybrid search
│       └── vector_store.py  # Qdrant client & RBAC filtering
├── tests/                  # Test suite
│   ├── test_hybrid_search.py
│   └── test_rbac_leak.py
└── ui/                     # Streamlit web interface
    ├── __init__.py
    └── app.py
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `super-secret-zero-trust-key-change-in-prod` | Secret for JWT signing |
| `QDRANT_HOST` | `localhost` | Qdrant server hostname |
| `QDRANT_PORT` | `6333` | Qdrant HTTP port |
| `QDRANT_COLLECTION_NAME` | `enterprise_rbac_docs` | Vector collection name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3` | LLM model name |
| `EMBEDDING_MODEL_NAME` | `BAAI/bge-small-en-v1.5` | Sentence transformer model |
| `LLM_TEMPERATURE` | `0.2` | LLM sampling temperature |
| `DEFAULT_TOP_K` | `4` | Default retrieval count |

### Document Ingestion Manifest

The `data/manifest.json` file controls document ingestion with RBAC metadata:

```json
[
  {
    "filename": "security_policy.txt",
    "doc_id": "doc-sec-001",
    "allowed_roles": ["security", "engineering", "management"],
    "clearance_level": 2
  },
  {
    "filename": "hr_policy.txt",
    "doc_id": "doc-hr-001",
    "allowed_roles": ["hr", "management"],
    "clearance_level": 4
  }
]
```

## Testing

### Run All Tests

```bash
# Using Docker
docker exec zero_trust_fastapi pytest tests/ -v

# Local development
pytest tests/ -v
```

### Test Categories

- **`test_rbac_leak.py`**: Verifies zero-trust guarantees - unauthorized users cannot access restricted documents
- **`test_hybrid_search.py`**: Benchmarks retrieval accuracy and relevance

## Troubleshooting

### Common Issues

**1. Ollama model not found**
```bash
docker exec zero_trust_ollama ollama pull llama3
```

**2. Qdrant connection refused**
```bash
# Check if Qdrant is healthy
docker logs zero_trust_qdrant
# Restart if needed
docker-compose -f docker/docker-compose.yml restart qdrant
```

**3. Port conflicts**
```bash
# Check what's using the ports
lsof -i :6333 -i :8000 -i :11434
# Stop conflicting services or change ports in docker-compose.yml
```

**4. Out of memory (OOM) errors**
- Increase Docker memory limit (Docker Desktop: Settings > Resources > Memory)
- Use a smaller model: `OLLAMA_MODEL=llama3.2:1b` or `phi3:mini`

**5. Embedding model download fails**
```bash
# Pre-download the model
docker exec zero_trust_fastapi python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
```

### Logs

```bash
# View all service logs
docker-compose -f docker/docker-compose.yml logs -f

# View specific service logs
docker-compose -f docker/docker-compose.yml logs -f rag_api
docker-compose -f docker/docker-compose.yml logs -f ollama
docker-compose -f docker/docker-compose.yml logs -f qdrant
```

## Security Considerations

1. **Change default JWT secret** in production: `JWT_SECRET_KEY`
2. **Use HTTPS** in production with reverse proxy (nginx, Traefik)
3. **Restrict network access** - services communicate on isolated Docker network
4. **Rotate secrets** regularly
5. **Audit logs** - monitor access patterns
6. **Principle of least privilege** - assign minimal roles/clearance

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Submit a pull request

## Support

For issues and questions, please open a GitHub issue.