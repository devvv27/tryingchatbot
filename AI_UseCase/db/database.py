from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from config.config import get_settings
from db.models import BookingPayload


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                booking_type TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_customer(name: str, email: str, phone: str) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT customer_id FROM customers WHERE email = ?", (email,))
        row = cur.fetchone()
        if row:
            customer_id = int(row["customer_id"])
            cur.execute(
                "UPDATE customers SET name = ?, phone = ? WHERE customer_id = ?",
                (name, phone, customer_id),
            )
            conn.commit()
            return customer_id

        cur.execute(
            "INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)",
            (name, email, phone),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def create_booking(payload: BookingPayload) -> int:
    conn = get_connection()
    try:
        customer_id = upsert_customer(payload.name, payload.email, payload.phone)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bookings (customer_id, booking_type, date, time, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                payload.booking_type,
                payload.booking_date,
                payload.booking_time,
                payload.status,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_bookings(
    name: Optional[str] = None,
    email: Optional[str] = None,
    date: Optional[str] = None,
) -> List[Dict]:
    conn = get_connection()
    try:
        base_query = """
            SELECT
                b.id,
                c.name,
                c.email,
                c.phone,
                b.booking_type,
                b.date,
                b.time,
                b.status,
                b.created_at
            FROM bookings b
            JOIN customers c ON b.customer_id = c.customer_id
            WHERE 1=1
        """
        params = []

        if name:
            base_query += " AND c.name LIKE ?"
            params.append(f"%{name}%")
        if email:
            base_query += " AND c.email LIKE ?"
            params.append(f"%{email}%")
        if date:
            base_query += " AND b.date = ?"
            params.append(date)

        base_query += " ORDER BY b.created_at DESC"

        cur = conn.cursor()
        cur.execute(base_query, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
