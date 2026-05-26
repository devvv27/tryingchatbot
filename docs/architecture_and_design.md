# Technical Assessment Deliverable

## A. Architectural Diagram
The diagram is provided in [architecture.mmd](./architecture.mmd).

## B. Design Document

### 1. Data Processing and Retrieval (RAG)

#### How Excel and Web resources are handled
- Excel ingestion processes each row as a retrieval unit and records location as `Tab: <sheet>, Row: <n>`.
- Web ingestion extracts heading and paragraph/list content and preserves logical sections as `Section: <heading>`.
- This keeps structured context fidelity, so generated answers can cite exact navigation fields.

#### Chunking strategy and citation mapping
- Parser output is normalized into text chunks using a sliding window (`chunk_size=900`, `overlap=120`) for long bodies.
- Each chunk stores:
  - `quote_text` (direct quote source for citation output)
  - `location_type` (`page`, `tab_row`, `section`)
  - `location_value` (human-readable navigation)
  - metadata JSON for deterministic source mapping
- PDF maps to page number.
- Excel maps to sheet and row.
- Word and Web map to section title.

#### Select and unselect implementation for low latency
- `documents` table in SQLite includes `is_selected` with index `idx_docs_selected`.
- At query time, the API resolves selected document IDs from either UI payload or SQLite selected state.
- Retrieval query joins `chunks` with `documents` and filters by selected IDs before scoring.
- Candidate rows are reduced first at SQL level, then cosine similarity runs only on the filtered set.

### 2. System Components

#### Database and storage recommendation
- Current prototype: a single SQLite database for documents, chunks, embeddings, and sessions/messages.
- Production recommendation:
  - PostgreSQL for metadata and access control.
  - Dedicated vector store (PgVector, Qdrant, or Milvus) for high-cardinality retrieval.
  - Object storage for source files (S3-compatible or on-prem blob/NAS).

#### Authentication and session management
- Prototype includes session persistence (`sessions`, `messages` tables).
- For internal production:
  - SSO via OIDC/SAML (Azure AD/Okta).
  - RBAC on knowledge spaces and documents.
  - Per-user session and audit logging for compliance.
  - Access tokens validated at API gateway and propagated as user identity claims.

### 3. AI Strategy

#### Recommended LLMs and routing
- Tiered strategy:
  - Retrieval and embedding: `all-MiniLM-L6-v2` for low-cost semantic recall.
  - Generation: local Ollama-hosted `llama3.1` for grounded response assembly.
  - Future router: promote only difficult queries to a larger locally hosted model if needed.
- This balances quality and cost.

#### Prompt/system instruction strategy for strict citations
- System prompt enforces:
  - use only provided context
  - return NOT_FOUND if evidence is missing
  - cite direct quotes and location in strict format
- Citation engine then returns structured citation fields for UI rendering and downstream validation.

#### Handling missing answers
- If no relevant chunks or weak relevance score, API returns grounded not-found response.
- The assistant explicitly states answer was not found in selected resources.
- No hallucinated content path is allowed.

### 4. Cost and Scaling

#### How token waste is minimized
- Candidate filtering by selected resources reduces context size before prompt construction.
- Top-K retrieval truncates prompt context to the most relevant chunks.
- Embeddings are computed at ingest time and reused across queries.
- The local Ollama model is called only after retrieval narrows the prompt to grounded evidence.

#### Scaling from 40 to 4,000 documents
- Move from SQLite to PostgreSQL + vector extension/service.
- Background workers for asynchronous ingestion and embedding jobs.
- Sharded or partitioned vector indexes by tenant/project.
- Cache query embeddings and top retrieval sets for repeated intents.
- Add monitoring for retrieval latency, miss rate, and citation correctness.

## Prototype Coverage vs Requirement
- Supports ingestion of PDF, DOCX, XLSX, and URL.
- Supports max 40 documents.
- Supports select and unselect from sidebar UI.
- Grounds answers on selected resources only.
- Returns direct quotes with location metadata.
- Provides web-based custom chat interface with sidebar document management.
- Uses SQLite as a single database for metadata, embeddings, and session state.
- Includes architecture + design deliverables.
