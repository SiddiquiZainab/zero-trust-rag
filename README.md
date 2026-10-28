# Zero-Trust RAG

**A security-focused reference implementation of enterprise RAG with server-enforced document access control, hybrid retrieval, and local model inference.**

The project explores a practical question: how do you retrieve useful internal knowledge without letting a user see documents their role or clearance does not permit?

This is a learning and portfolio project, not a certified security product. The demo authentication store is intentionally simple; use a production identity provider, persistent user store, secrets manager, network controls, and a security review before adapting this design to a real environment.

## What it demonstrates

- **Policy-filtered retrieval:** role intersection and clearance checks are sent to Qdrant before document payloads are returned.
- **Hybrid ranking:** dense vector similarity and BM25 lexical ranking are merged with Reciprocal Rank Fusion (RRF).
- **Server-side identity context:** the API derives roles and clearance from a verified token and configured user record, not from fields in a user query.
- **Local inference path:** Qdrant, embeddings, and Ollama can run within the Docker setup.
- **Fail-closed empty context:** when retrieval returns no authorized context, the API returns a fixed insufficient-information response without calling the LLM.
- **Inspectable evidence:** responses include the names of retrieved source documents.
- **Automated checks:** deterministic unit tests cover rank fusion, lexical ranking, and no-role behavior.

## Architecture

~~~mermaid
flowchart TD
    U[User / Streamlit UI] -->|Credentials| A[FastAPI Authentication]
    A -->|Signed JWT| U
    U -->|JWT + Question| API[FastAPI Query API]
    API --> C[Server-side User Context]
    C --> D[Qdrant Dense Search]
    C --> E[Qdrant Scroll of Authorized Payloads]
    D -->|Role + clearance filter| F[Dense Candidates]
    E -->|Role + clearance filter| G[Authorized Corpus]
    G --> H[BM25 Ranking]
    F --> I[Reciprocal Rank Fusion]
    H --> I
    I -->|Authorized context only| J{Any results?}
    J -->|No| K[Fixed insufficient-context response]
    J -->|Yes| L[Ollama LLM]
    L --> M[Answer + retrieved source names]
~~~

**Important implementation trade-off:** the reference BM25 path scrolls the authorized Qdrant payloads and ranks them in the API process. This is easy to inspect and useful for a small demo corpus, but it is not designed for large-scale corpora. For production-sized data, use a dedicated lexical index or native sparse-vector retrieval and benchmark the full query path.

## Stack

| Component | Purpose |
|---|---|
| Python / FastAPI | API and request validation |
| JWT | Demo authentication token |
| Qdrant | Dense vector store and pre-filtered payload retrieval |
| Sentence Transformers | Text embeddings |
| BM25 + RRF | Lexical ranking and fusion with dense results |
| Ollama | Local language-model inference |
| Streamlit | Browser-based demo UI |
| Docker Compose | Local service orchestration |
| pytest / GitHub Actions | Deterministic unit tests and CI |

## Quick start with Docker

### 1. Requirements

- Docker Desktop or Docker Engine with Compose v2
- Git
- Recommended: 8 GB+ RAM if you plan to run a local LLM

### 2. Clone and configure

~~~bash
git clone https://github.com/SiddiquiZainab/zero-trust-rag.git
cd zero-trust-rag
cp .env.example .env
~~~

Generate a unique JWT signing key:

~~~bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
~~~

Edit .env. Replace every replace_with value with your own unique value. Use different passwords for the three demo users, and never commit .env. The API intentionally exits at startup if required secrets are missing or still look like placeholders.

Required variables:

| Variable | Purpose |
|---|---|
| JWT_SECRET_KEY | Random JWT signing secret, at least 32 characters |
| DEMO_ALICE_PASSWORD | Password for the engineering demo account |
| DEMO_HR_PASSWORD | Password for the HR demo account |
| DEMO_ADMIN_PASSWORD | Password for the document-upload demo account |

These are local demonstration identities, not a production user-management system.

### 3. Start services

Run from the repository root:

~~~bash
docker compose --env-file .env -f docker/docker-compose.yml up --build -d
docker compose --env-file .env -f docker/docker-compose.yml ps
docker compose --env-file .env -f docker/docker-compose.yml logs -f rag_api
~~~

The API, UI, Qdrant, and Ollama ports are bound to localhost by the Compose configuration. Do not expose the services to an untrusted network without appropriate authentication, TLS, and network controls.

### 4. Pull the model and index the sample corpus

~~~bash
docker exec zero_trust_ollama ollama pull llama3
docker exec zero_trust_fastapi python -m src.ingestion.pipeline
~~~

The embedding model is downloaded by Sentence Transformers on first use. Model downloads require network access during initial setup unless you pre-stage the model.

### 5. Open the demo

- Streamlit UI: http://localhost:8501
- FastAPI docs: http://localhost:8000/docs
- API health: http://localhost:8000/health
- Qdrant dashboard: http://localhost:6333/dashboard

Sign in with username alice_eng, bob_hr, or admin_user and the unique password you configured for that account in .env. Passwords are not embedded in the repository or UI.

## Run the deterministic unit tests

These tests do not start Qdrant, download an embedding model, or require Ollama:

~~~bash
python -m pip install -r requirements-test.txt
python -m pytest -q tests/test_hybrid_retrieval_unit.py
~~~

The same focused test file runs in GitHub Actions. The older tests in tests/test_rbac_leak.py and tests/test_hybrid_search.py exercise a live RAG stack and require sample data, Qdrant, the embedding model, and an accessible LLM. They are integration-style checks, not part of the lightweight CI job.

## Access-control model

Each stored chunk carries metadata such as:

~~~json
{
  "doc_id": "doc-sec-001",
  "source": "security_policy.txt",
  "allowed_roles": ["security", "engineering"],
  "clearance_level": 2,
  "text": "Example chunk content"
}
~~~

For each retrieval request, the query filter requires both:

1. At least one match between the document's allowed_roles and the authenticated user's roles.
2. The document's clearance_level to be less than or equal to the user's clearance.

The same filter is applied to dense search and to the payloads considered by BM25. An empty role list returns no results. Authorization must remain enforced by the API and data layer; UI visibility is not a security boundary.

## API example

First, request a token with your configured password:

~~~bash
curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=alice_eng" \
  --data-urlencode "password=YOUR_CONFIGURED_PASSWORD"
~~~

Then query with the returned access token:

~~~bash
curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the security policy for data handling?"}'
~~~

The query endpoint accepts only the question. Role and clearance data are taken from the verified token subject and the server-side demo user map.

## Repository layout

~~~text
src/
  auth/          # JWT decoding and role/clearance dependency
  engine/        # RAG chain and Ollama wrapper
  ingestion/     # Chunking, metadata, and indexing pipeline
  retrieval/     # Qdrant filtering, dense ranking, BM25, and RRF
tests/           # Unit and integration-style checks
ui/              # Streamlit demo
docker/          # Dockerfiles and Compose stack
.github/workflows/ci.yml
~~~

## Security notes and limitations

- This repository is a **reference implementation**, not a security certification or a production-ready identity platform.
- Demo passwords are loaded from environment variables but stored in a simple in-memory map; production authentication should use an identity provider and a proper credential store.
- Use TLS, managed secrets, audit logging, rate limits, dependency scanning, data retention controls, and a formal threat model before real deployment.
- Document content is untrusted input. Prompt instructions reduce some risks but are not a complete prompt-injection defense.
- Hybrid retrieval has not been published with a benchmark score. Build a labeled query set and report recall@k, MRR/nDCG, latency, and access-policy tests before making performance claims.
- Qdrant filtering is part of the data access design, but deployment/network permissions and all ingestion paths must also be tested as part of an end-to-end security review.
- Only upload non-sensitive test documents to the public demo.

## Roadmap

- Add a labeled retrieval evaluation dataset and report metrics for dense-only, BM25-only, and RRF.
- Add integration tests using a disposable Qdrant instance and a stub LLM.
- Replace the demo user map with an identity-provider integration.
- Add structured audit events and request correlation IDs.
- Evaluate a dedicated lexical index or Qdrant sparse vectors for larger corpora.

## License

See LICENSE.

## Author

**Zainab Siddiqui** — AI/ML Engineer focused on secure RAG, agentic workflows, and reliable LLM applications.

- GitHub: [@SiddiquiZainab](https://github.com/SiddiquiZainab)
