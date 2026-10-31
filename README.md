# Zero-Trust RAG

**A security-focused Retrieval-Augmented Generation (RAG) service with server-enforced document authorization, hybrid retrieval, and source attribution.**

Zero-Trust RAG is designed for internal knowledge assistants and private enterprise search workflows where users must only retrieve information permitted by their roles and clearance levels. Authorization is applied in the API and retrieval layer before document context is passed to the language model.

The application combines FastAPI, Qdrant, Sentence Transformers, BM25, Reciprocal Rank Fusion (RRF), and Ollama, with a Streamlit interface and a Docker Compose deployment profile.

## Core capabilities

- **Policy-filtered retrieval:** role intersection and clearance checks are applied in Qdrant before document payloads are returned.
- **Hybrid ranking:** dense vector similarity and BM25 lexical ranking are combined using Reciprocal Rank Fusion (RRF).
- **Server-side identity context:** the API validates a signed token and resolves roles and clearance from server-side account configuration, rather than accepting authorization attributes from a user query.
- **Local model inference:** Qdrant, embeddings, and Ollama can run within the Docker deployment.
- **Fail-closed empty context:** when retrieval returns no authorized context, the API returns a fixed insufficient-information response without calling the LLM.
- **Source attribution:** responses include the names of the retrieved source documents.
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

### Retrieval design and scaling

The current BM25 implementation scrolls authorized Qdrant payloads and ranks them in the API process. This keeps the policy filter in the retrieval path and is straightforward to inspect, but its corpus size and throughput are constrained by API memory and processing capacity. For larger collections, use a dedicated lexical index or native sparse-vector retrieval, then benchmark the complete query path under representative workloads.

## Technology stack

| Component | Purpose |
|---|---|
| Python / FastAPI | API, authentication endpoints, and request validation |
| JWT | Signed API access tokens |
| Qdrant | Dense vector storage and pre-filtered payload retrieval |
| Sentence Transformers | Text embeddings |
| BM25 + RRF | Lexical ranking and fusion with dense results |
| Ollama | Local language-model inference |
| Streamlit | Browser-based application interface |
| Docker Compose | Local service orchestration |
| pytest / GitHub Actions | Automated unit tests and CI |

## Run locally with Docker

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

Edit `.env`. Replace every `replace_with` value with a unique value. Use different passwords for the configured local accounts, and never commit `.env`. The API intentionally exits at startup if required secrets are missing or still look like placeholders.

Required variables:

| Variable | Purpose |
|---|---|
| JWT_SECRET_KEY | Random JWT signing secret, at least 32 characters |
| DEMO_ALICE_PASSWORD | Password for the engineering local account |
| DEMO_HR_PASSWORD | Password for the HR local account |
| DEMO_ADMIN_PASSWORD | Password for the document-upload administrator account |

The supplied local account configuration uses predefined identities and an in-memory user map. For an organization deployment, integrate an identity provider and a persistent source of user, role, and clearance attributes before connecting the service to protected information.

### 3. Start the services

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

### 5. Access the local services

- Streamlit interface: http://localhost:8501
- FastAPI documentation: http://localhost:8000/docs
- API health: http://localhost:8000/health
- Qdrant dashboard: http://localhost:6333/dashboard

Sign in with `alice_eng`, `bob_hr`, or `admin_user` and the unique password configured for that account in `.env`. Passwords are not embedded in the repository or UI.

## Run the unit tests

These tests do not start Qdrant, download an embedding model, or require Ollama:

~~~bash
python -m pip install -r requirements-test.txt
python -m pytest -q tests/test_hybrid_retrieval_unit.py
~~~

The same focused test file runs in GitHub Actions. The tests in `tests/test_rbac_leak.py` and `tests/test_hybrid_search.py` exercise a live RAG stack and require sample data, Qdrant, the embedding model, and an accessible LLM. They are integration-style checks, not part of the lightweight CI job.

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

1. At least one match between the document's `allowed_roles` and the authenticated user's roles.
2. The document's `clearance_level` to be less than or equal to the user's clearance.

The same filter is applied to dense search and to the payloads considered by BM25. An empty role list returns no results. Authorization must remain enforced by the API and data layer; UI visibility is not a security boundary.

## API example

Request a token with the password configured for the local account:

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

The query endpoint accepts only the question. Role and clearance data are taken from the verified token subject and the server-side user configuration.

## Repository layout

~~~text
src/
  auth/          # JWT decoding and role/clearance dependency
  engine/        # RAG chain and Ollama wrapper
  ingestion/     # Chunking, metadata, and indexing pipeline
  retrieval/     # Qdrant filtering, dense ranking, BM25, and RRF
tests/           # Unit and integration-style checks
ui/              # Streamlit application
docker/          # Dockerfiles and Compose stack
.github/workflows/ci.yml
~~~

## Security and deployment considerations

The retrieval path enforces role and clearance filters, but an organization deployment requires controls that are specific to its identity system, infrastructure, data classification, and threat model.

- **Identity and authorization:** the current account map is in memory. Integrate an enterprise identity provider and a persistent, authoritative source for user roles and clearance attributes. Define how role changes, account disablement, and token revocation are propagated.
- **Secrets and transport:** use a managed secrets service, TLS, restricted network access, and environment-specific configuration. Do not expose local service ports directly to untrusted networks.
- **Operations:** add structured audit events, request correlation IDs, rate limits, dependency and container scanning, monitoring, backups, and data-retention controls appropriate to the deployment.
- **Prompt injection and untrusted content:** document content is untrusted input. Prompt instructions can reduce some risks but are not a complete prompt-injection defense. Apply ingestion controls and evaluate attack scenarios against the full application.
- **Retrieval performance:** no benchmark results are published for the current hybrid retrieval path. Build a labeled query set and measure recall@k, MRR/nDCG, latency, throughput, and access-policy behavior before setting performance targets.
- **End-to-end access boundaries:** Qdrant filtering is one part of the access-control design. Validate service credentials, collection permissions, ingestion paths, network boundaries, and tenant isolation as part of a deployment security review.
- **Data handling:** use non-sensitive content in local environments until access, retention, and operational controls have been validated for the target environment.

## Operational extensions

The following are natural extensions when adapting the service to a specific organization:

- Add a labeled retrieval evaluation dataset and report metrics for dense-only, BM25-only, and RRF.
- Add integration tests using a disposable Qdrant instance and a stub LLM.
- Replace the local user map with an identity-provider integration.
- Add structured audit events and request correlation IDs.
- Evaluate a dedicated lexical index or Qdrant sparse vectors for larger corpora.

## License

See LICENSE.

## Author

**Zainab Siddiqui** — AI/ML Engineer focused on secure RAG, agentic workflows, and reliable LLM applications.

- GitHub: [@SiddiquiZainab](https://github.com/SiddiquiZainab)
