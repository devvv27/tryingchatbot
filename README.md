# Knowledge Assistant Prototype

This repository contains a working prototype for the AI/ML intern technical assessment.

## What is implemented
- Multi-source ingestion: PDF, DOCX, XLSX, URL
- Knowledge Hub cap of 40 documents
- Sidebar-based select/unselect resource scoping
- Grounded QA over selected resources only
- Single SQLite database for metadata, embeddings, and session/chat state
- In-process cosine similarity retrieval over SQLite-stored embeddings
- Direct-quote citation output with location metadata:
  - PDF: page
  - Excel: tab/row
  - Word/Web: section
- Web chat interface + document management sidebar
- Architecture and design deliverables in `docs/`

## Run locally (no virtual environment)
1. Install dependencies globally:
   pip install -r requirements.txt
2. Start the app:
   uvicorn app.main:app --reload
3. Open browser:
   http://127.0.0.1:8000

## API endpoints
- `POST /api/documents/upload`
- `POST /api/documents/url`
- `GET /api/documents`
- `POST /api/documents/{document_id}/select`
- `POST /api/query`
- `GET /api/sessions/{session_id}/messages`

## Optional LLM mode
Responses are generated through local Ollama using a strict grounded prompt and citation format.
Set `OLLAMA_MODEL` if you want to switch between installed models such as `llama3`, `llama3.1`, or `llama3.2`.
The default endpoint is `http://localhost:11434`.
