import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class DocumentRecord:
    id: str
    name: str
    source_type: str
    source_path: str | None
    source_url: str | None
    is_selected: bool
    created_at: str


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_path TEXT,
                source_url TEXT,
                is_selected INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                quote_text TEXT NOT NULL,
                location_type TEXT NOT NULL,
                location_value TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_selected ON documents(is_selected)")
        conn.commit()
        conn.close()

    def count_documents(self) -> int:
        conn = self.connect()
        count = conn.execute("SELECT COUNT(*) as n FROM documents").fetchone()["n"]
        conn.close()
        return int(count)

    def insert_document(
        self,
        document_id: str,
        name: str,
        source_type: str,
        source_path: str | None,
        source_url: str | None,
    ) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO documents (id, name, source_type, source_path, source_url, is_selected, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                document_id,
                name,
                source_type,
                source_path,
                source_url,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    def insert_chunks(self, rows: list[dict[str, Any]]) -> None:
        conn = self.connect()
        conn.executemany(
            """
            INSERT INTO chunks (
                id, document_id, chunk_index, text, quote_text, location_type,
                location_value, metadata_json, embedding_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row["document_id"],
                    row["chunk_index"],
                    row["text"],
                    row["quote_text"],
                    row["location_type"],
                    row["location_value"],
                    json.dumps(row["metadata"]),
                    json.dumps(row["embedding"]),
                )
                for row in rows
            ],
        )
        conn.commit()
        conn.close()

    def list_documents(self) -> list[DocumentRecord]:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT id, name, source_type, source_path, source_url, is_selected, created_at
            FROM documents
            ORDER BY created_at DESC
            """
        ).fetchall()
        conn.close()
        return [
            DocumentRecord(
                id=row["id"],
                name=row["name"],
                source_type=row["source_type"],
                source_path=row["source_path"],
                source_url=row["source_url"],
                is_selected=bool(row["is_selected"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def set_document_selected(self, document_id: str, selected: bool) -> None:
        conn = self.connect()
        conn.execute(
            "UPDATE documents SET is_selected = ? WHERE id = ?",
            (1 if selected else 0, document_id),
        )
        conn.commit()
        conn.close()

    def delete_document(self, document_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            "SELECT id, name, source_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            conn.close()
            return None

        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        conn.commit()
        conn.close()
        return {"id": row["id"], "name": row["name"], "source_path": row["source_path"]}

    def get_selected_document_ids(self) -> list[str]:
        conn = self.connect()
        rows = conn.execute("SELECT id FROM documents WHERE is_selected = 1").fetchall()
        conn.close()
        return [row["id"] for row in rows]

    def get_candidate_chunks(
        self,
        selected_document_ids: list[str] | None,
        top_limit: int = 2000,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        params: list[Any] = []
        where_sql = "WHERE d.is_selected = 1"
        if selected_document_ids:
            placeholders = ",".join(["?"] * len(selected_document_ids))
            where_sql = f"WHERE d.id IN ({placeholders})"
            params.extend(selected_document_ids)

        rows = conn.execute(
            f"""
            SELECT
                c.id, c.document_id, c.text, c.quote_text,
                c.location_type, c.location_value, c.metadata_json, c.embedding_json,
                d.name AS document_name, d.source_type
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            {where_sql}
            LIMIT ?
            """,
            (*params, top_limit),
        ).fetchall()
        conn.close()

        result: list[dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}

            # Compute canonical location_value from metadata when possible to
            # avoid mismatches between stored location_value and metadata.
            loc_type = row["location_type"]
            loc_value = row["location_value"] or ""
            try:
                if loc_type == "page" or "page" in metadata:
                    page = metadata.get("page") or loc_value.replace("Page", "").strip()
                    loc_value = f"Page {page}"
                elif loc_type == "tab_row" or metadata.get("sheet"):
                    sheet = metadata.get("sheet")
                    r = metadata.get("row")
                    if sheet and r is not None:
                        loc_value = f"Tab: {sheet}, Row: {r}"
                elif loc_type == "section" or metadata.get("section"):
                    sec = metadata.get("section")
                    if sec:
                        loc_value = f"Section: {sec}"
            except Exception:
                # Fallback to stored location_value on any error
                loc_value = row["location_value"]

            result.append(
                {
                    "id": row["id"],
                    "document_id": row["document_id"],
                    "document_name": row["document_name"],
                    "source_type": row["source_type"],
                    "text": row["text"],
                    "quote_text": row["quote_text"],
                    "location_type": loc_type,
                    "location_value": loc_value,
                    "metadata": metadata,
                    "embedding": json.loads(row["embedding_json"]),
                }
            )
        return result

    def get_all_chunks(self) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT
                c.id, c.document_id, c.text, c.quote_text,
                c.location_type, c.location_value, c.metadata_json, c.embedding_json,
                d.name AS document_name, d.source_type
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            """
        ).fetchall()
        conn.close()

        result: list[dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            loc_type = row["location_type"]
            loc_value = row["location_value"] or ""
            try:
                if loc_type == "page" or "page" in metadata:
                    page = metadata.get("page") or loc_value.replace("Page", "").strip()
                    loc_value = f"Page {page}"
                elif loc_type == "tab_row" or metadata.get("sheet"):
                    sheet = metadata.get("sheet")
                    r = metadata.get("row")
                    if sheet and r is not None:
                        loc_value = f"Tab: {sheet}, Row: {r}"
                elif loc_type == "section" or metadata.get("section"):
                    sec = metadata.get("section")
                    if sec:
                        loc_value = f"Section: {sec}"
            except Exception:
                loc_value = row["location_value"]

            result.append(
                {
                    "id": row["id"],
                    "document_id": row["document_id"],
                    "document_name": row["document_name"],
                    "source_type": row["source_type"],
                    "text": row["text"],
                    "quote_text": row["quote_text"],
                    "location_type": loc_type,
                    "location_value": loc_value,
                    "metadata": metadata,
                    "embedding": json.loads(row["embedding_json"]),
                }
            )
        return result

    def get_or_create_session(self, session_id: str, user_id: str) -> str:
        conn = self.connect()
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO sessions (id, user_id, created_at) VALUES (?, ?, ?)",
                (session_id, user_id, datetime.utcnow().isoformat()),
            )
            conn.commit()
        conn.close()
        return session_id

    def add_message(self, message_id: str, session_id: str, role: str, content: str) -> None:
        conn = self.connect()
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

    def list_messages(self, session_id: str) -> list[dict[str, str]]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        conn.close()
        return [{"role": row["role"], "content": row["content"], "created_at": row["created_at"]} for row in rows]
