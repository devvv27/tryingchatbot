from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.citation_engine import build_context_for_llm, citation_item
from app.config import DB_PATH, MAX_DOCUMENTS, TOP_K, UPLOAD_DIR
from app.ingestion import parse_source
from app.llm import generate_answer
from app.models import Database
from app.retrieval import EmbeddingService, retrieve_relevant_chunks


class UrlIngestRequest(BaseModel):
    url: str


class SelectRequest(BaseModel):
    selected: bool


class QueryRequest(BaseModel):
    question: str = Field(min_length=3)
    selected_document_ids: list[str] | None = None
    session_id: str | None = None
    user_id: str = "internal-user"


app = FastAPI(title="Knowledge Assistant")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

db = Database(DB_PATH)
embedder = EmbeddingService()


@app.on_event("startup")
def startup() -> None:
    db.init_schema()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})


def _save_upload(upload: UploadFile) -> Path:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in {".pdf", ".docx", ".xlsx"}:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and XLSX files are supported")

    out_path = UPLOAD_DIR / f"{uuid4()}{ext}"
    with out_path.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return out_path


def _ext_to_type(ext: str) -> str:
    return {
        ".pdf": "pdf",
        ".docx": "docx",
        ".xlsx": "xlsx",
    }[ext]


def _store_chunks(document_id: str, doc_name: str, source_type: str, parsed_rows: list[dict[str, Any]]) -> int:
    if not parsed_rows:
        return 0

    texts = [r["text"] for r in parsed_rows]
    vectors = embedder.embed(texts)

    rows_for_db: list[dict[str, Any]] = []
    for i, row in enumerate(parsed_rows):
        rows_for_db.append(
            {
                "id": str(uuid4()),
                "document_id": document_id,
                "chunk_index": i,
                "text": row["text"],
                "quote_text": row["quote_text"],
                "location_type": row["location_type"],
                "location_value": row["location_value"],
                "metadata": {
                    **row["metadata"],
                    "document_name": doc_name,
                    "source_type": source_type,
                },
                "embedding": vectors[i].tolist(),
            }
        )
    db.insert_chunks(rows_for_db)
    return len(rows_for_db)


@app.get("/api/documents")
def list_documents() -> dict[str, Any]:
    docs = db.list_documents()
    return {
        "documents": [
            {
                "id": d.id,
                "name": d.name,
                "source_type": d.source_type,
                "source_path": d.source_path,
                "source_url": d.source_url,
                "is_selected": d.is_selected,
                "created_at": d.created_at,
            }
            for d in docs
        ]
    }


@app.post("/api/documents/upload")
def ingest_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    if db.count_documents() >= MAX_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"Document limit reached ({MAX_DOCUMENTS})")

    saved_path = _save_upload(file)
    source_type = _ext_to_type(saved_path.suffix.lower())
    doc_id = str(uuid4())
    doc_name = file.filename or saved_path.name

    db.insert_document(doc_id, doc_name, source_type, str(saved_path), None)
    parsed_rows = parse_source(source_type=source_type, source_path=saved_path)
    chunk_count = _store_chunks(doc_id, doc_name, source_type, parsed_rows)

    return {
        "document_id": doc_id,
        "name": doc_name,
        "source_type": source_type,
        "chunks_indexed": chunk_count,
    }


@app.post("/api/documents/url")
def ingest_url(payload: UrlIngestRequest) -> dict[str, Any]:
    if db.count_documents() >= MAX_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"Document limit reached ({MAX_DOCUMENTS})")

    doc_id = str(uuid4())
    doc_name = payload.url
    source_type = "url"

    db.insert_document(doc_id, doc_name, source_type, None, payload.url)
    parsed_rows = parse_source(source_type=source_type, source_url=payload.url)
    chunk_count = _store_chunks(doc_id, doc_name, source_type, parsed_rows)

    return {
        "document_id": doc_id,
        "name": doc_name,
        "source_type": source_type,
        "chunks_indexed": chunk_count,
    }


@app.post("/api/documents/{document_id}/select")
def set_select(document_id: str, payload: SelectRequest) -> dict[str, Any]:
    db.set_document_selected(document_id, payload.selected)
    return {"document_id": document_id, "is_selected": payload.selected}


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str) -> dict[str, Any]:
    deleted = db.delete_document(document_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Document not found")

    source_path = deleted.get("source_path")
    if source_path:
        try:
            file_path = Path(source_path)
            if file_path.exists():
                file_path.unlink()
        except OSError:
            # Non-fatal cleanup failure; DB state is already consistent.
            pass

    return {"deleted": True, "document_id": deleted["id"], "name": deleted["name"]}


@app.post("/api/query")
def query(payload: QueryRequest) -> dict[str, Any]:
    selected_document_ids = payload.selected_document_ids
    if selected_document_ids is None:
        selected_document_ids = db.get_selected_document_ids()

    if len(selected_document_ids) == 0:
        return {
            "answer": "I could not find the answer in the selected resources.\n\nCitations: None",
            "citations": [],
            "used_chunk_count": 0,
        }

    candidates = db.get_candidate_chunks(selected_document_ids=selected_document_ids)
    relevant = retrieve_relevant_chunks(
        query=payload.question,
        candidates=candidates,
        embedder=embedder,
        top_k=TOP_K,
    )

    # Confidence guardrail: keep strict grounding but avoid false negatives for short factual queries.
    if not relevant or relevant[0].get("score", 0.0) < 0.12:
        answer = "I could not find the answer in the selected resources.\n\nCitations: None"
        citations: list[dict[str, str]] = []
    else:
        context = build_context_for_llm(relevant)
        answer = generate_answer(payload.question, context, relevant)
        citations = [citation_item(chunk) for chunk in relevant]

    session_id = payload.session_id or str(uuid4())
    db.get_or_create_session(session_id=session_id, user_id=payload.user_id)
    db.add_message(str(uuid4()), session_id, "user", payload.question)
    db.add_message(str(uuid4()), session_id, "assistant", answer)

    return {
        "session_id": session_id,
        "answer": answer,
        "citations": citations,
        "used_chunk_count": len(relevant),
    }


@app.get("/api/sessions/{session_id}/messages")
def session_messages(session_id: str) -> dict[str, Any]:
    return {"messages": db.list_messages(session_id)}
