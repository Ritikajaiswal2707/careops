"""SQLite-backed approval lifecycle for synthetic CareOps recovery proposals.

This records coordinator decisions only. It does not book appointments or send
messages. Configure CAREOPS_DB_PATH for a durable writable database location.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CaseNotFoundError(LookupError):
    pass


class CaseConflictError(ValueError):
    pass


def _db_path() -> Path:
    configured = os.getenv("CAREOPS_DB_PATH")
    if configured:
        return Path(configured)
    # Keep runtime data outside the source tree by default.
    return Path(os.getenv("TMPDIR", "/tmp")) / "careops_agent_cases.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_default(value: Any):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Cannot JSON encode {type(value).__name__}")


def init_store() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS approval_cases (
                case_id TEXT PRIMARY KEY,
                appointment_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending_approval','approved','rejected')),
                proposal_json TEXT NOT NULL,
                agent_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                decision_note TEXT
            );
            CREATE TABLE IF NOT EXISTS approval_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL REFERENCES approval_cases(case_id),
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_approval_cases_appointment
                ON approval_cases(appointment_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_approval_events_case
                ON approval_events(case_id, event_id);
            CREATE TABLE IF NOT EXISTS simulated_executions (
                execution_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL UNIQUE REFERENCES approval_cases(case_id),
                appointment_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                target_date TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)


def create_case(agent_result: dict) -> dict | None:
    """Persist a proposal requiring approval; return None when no proposal exists."""
    proposal = agent_result.get("proposal")
    if not proposal:
        return None
    if not agent_result.get("approval_required", proposal.get("approval_required", False)):
        raise ValueError("Only approval-gated proposals may be persisted")

    init_store()
    case_id = f"CASE-{uuid.uuid4().hex[:12].upper()}"
    now = _now()
    proposal_json = json.dumps(proposal, default=_json_default, sort_keys=True)
    with _connect() as conn:
        conn.execute(
            """INSERT INTO approval_cases
               (case_id, appointment_id, status, proposal_json, agent_version, created_at, updated_at)
               VALUES (?, ?, 'pending_approval', ?, ?, ?, ?)""",
            (case_id, str(agent_result["appointment_id"]), proposal_json,
             str(agent_result.get("agent_version", "unknown")), now, now),
        )
        conn.execute(
            "INSERT INTO approval_events (case_id,event_type,actor,note,created_at) VALUES (?,?,?,?,?)",
            (case_id, "proposal_created", "agent", "Synthetic proposal created; no booking executed.", now),
        )
    return get_case(case_id)


def get_case(case_id: str) -> dict:
    init_store()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM approval_cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            raise CaseNotFoundError(case_id)
        events = conn.execute(
            "SELECT event_type, actor, note, created_at FROM approval_events WHERE case_id = ? ORDER BY event_id",
            (case_id,),
        ).fetchall()
        execution_row = conn.execute(
            "SELECT * FROM simulated_executions WHERE case_id = ?", (case_id,)
        ).fetchone()
    execution = None
    if execution_row is not None:
        execution = {
            "execution_id": execution_row["execution_id"],
            "appointment_id": execution_row["appointment_id"],
            "provider_id": execution_row["provider_id"],
            "target_date": execution_row["target_date"],
            "details": json.loads(execution_row["details_json"]),
            "created_at": execution_row["created_at"],
            "simulated": True,
        }
    return {
        "case_id": row["case_id"],
        "appointment_id": row["appointment_id"],
        "status": row["status"],
        "proposal": json.loads(row["proposal_json"]),
        "agent_version": row["agent_version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "decision_note": row["decision_note"],
        "simulated": True,
        "booking_executed": False,
        "simulated_execution": execution,
        "workflow_status": "simulated_resolved" if execution else row["status"],
        "events": [dict(event) for event in events],
    }


def record_simulated_execution(case_id: str, validated: dict) -> dict:
    """Persist a single simulated execution after revalidation; idempotent by case."""
    init_store()
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status, appointment_id, proposal_json FROM approval_cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise CaseNotFoundError(case_id)
        existing = conn.execute(
            "SELECT execution_id FROM simulated_executions WHERE case_id = ?", (case_id,)
        ).fetchone()
        if existing is not None:
            # A repeated request returns the existing record without duplicate events.
            pass
        elif row["status"] != "approved":
            raise CaseConflictError("Case must be approved before simulated execution.")
        else:
            proposal = json.loads(row["proposal_json"])
            if str(validated.get("appointment_id")) != str(row["appointment_id"]):
                raise CaseConflictError("Revalidated appointment does not match the approved case.")
            if str(validated.get("provider_id")) != str(proposal.get("provider_id")):
                raise CaseConflictError("Revalidated provider does not match the approved proposal.")
            if str(validated.get("target_date")) != str(proposal.get("new_date")):
                raise CaseConflictError("Revalidated date does not match the approved proposal.")
            execution_id = f"SIM-{uuid.uuid4().hex[:12].upper()}"
            conn.execute(
                """INSERT INTO simulated_executions
                   (execution_id, case_id, appointment_id, provider_id, target_date, details_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (execution_id, case_id, row["appointment_id"], str(validated["provider_id"]),
                 str(validated["target_date"]), json.dumps(validated, default=_json_default, sort_keys=True), now),
            )
            conn.execute(
                "INSERT INTO approval_events (case_id,event_type,actor,note,created_at) VALUES (?,?,?,?,?)",
                (case_id, "simulated_recovery_executed", "system",
                 "Recovery recorded in simulation only; no real booking or notification occurred.", now),
            )
    return get_case(case_id)


def decide_case(case_id: str, decision: str, note: str | None = None, actor: str = "coordinator") -> dict:
    """Record an approval/rejection. Repeated same decisions are idempotent."""
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    target_status = "approved" if decision == "approve" else "rejected"
    event_type = "proposal_approved" if decision == "approve" else "proposal_rejected"
    now = _now()
    init_store()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status FROM approval_cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            raise CaseNotFoundError(case_id)
        current = row["status"]
        if current == target_status:
            # Idempotent retry: do not duplicate audit events.
            pass
        elif current != "pending_approval":
            raise CaseConflictError(f"Case already has decision: {current}")
        else:
            conn.execute(
                "UPDATE approval_cases SET status=?, updated_at=?, decision_note=? WHERE case_id=? AND status='pending_approval'",
                (target_status, now, note, case_id),
            )
            conn.execute(
                "INSERT INTO approval_events (case_id,event_type,actor,note,created_at) VALUES (?,?,?,?,?)",
                (case_id, event_type, actor, note, now),
            )
    return get_case(case_id)
