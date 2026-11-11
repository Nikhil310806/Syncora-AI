import sqlite3
import json
from typing import Dict, Any, Optional

DB_FILE = "github_data.db"

def init_audit_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audits (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                tools_parameter TEXT,
                tools_output TEXT,
                control_parameter TEXT,
                control_output TEXT,
                final_report TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

def save_pending_audit(audit_id: str, query: str, state: dict):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO audits (id, query, status, tools_parameter, tools_output, control_parameter)
            VALUES (?, ?, 'PENDING_APPROVAL', ?, ?, ?)
        """, (
            audit_id,
            query,
            json.dumps(state.get("tools_parameter", [])),
            json.dumps(state.get("tools_output", [])),
            json.dumps(state.get("control_parameter", []))
        ))

def get_audit(audit_id: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM audits WHERE id = ?", (audit_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        for field in ["tools_parameter", "tools_output", "control_parameter", "control_output"]:
            if res.get(field):
                res[field] = json.loads(res[field])
        return res

def complete_audit(audit_id: str, control_output: list, report: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE audits 
            SET status = 'COMPLETED',
                control_output = ?,
                final_report = ?
            WHERE id = ?
        """, (json.dumps(control_output), report, audit_id))

def reject_audit(audit_id: str, reason: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE audits 
            SET status = 'REJECTED',
                final_report = ?
            WHERE id = ?
        """, (f"Rejected by Compliance Manager: {reason}", audit_id))