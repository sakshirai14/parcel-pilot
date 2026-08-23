import sqlite3
import json
from typing import Optional, List, Dict, Any
from backend.app.config import DATABASE_PATH
from backend.app.schemas.actions import ActionProposal, ActionStatus, ActionType, AuditLogEntry

import shutil
from pathlib import Path

def _ensure_db_exists():
    from backend.app.config import DATABASE_DIR
    bundled_db = DATABASE_DIR / "parcelpilot.db"
    if DATABASE_PATH != bundled_db and not DATABASE_PATH.exists() and bundled_db.exists():
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_db, DATABASE_PATH)

def get_connection():
    _ensure_db_exists()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_action_tables():
    """
    Creates action_proposals, audit_logs, escalations, and follow_up_tasks tables if they don't exist.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Action proposals table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_proposals (
            action_id TEXT PRIMARY KEY,
            action_type TEXT NOT NULL,
            account_id TEXT,
            ticket_id TEXT,
            order_id TEXT,
            summary TEXT NOT NULL,
            reason TEXT NOT NULL,
            proposed_changes TEXT NOT NULL, -- JSON string
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """)
        
        # 2. Audit logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id TEXT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            account_id TEXT,
            ticket_id TEXT,
            order_id TEXT,
            action_type TEXT NOT NULL,
            previous_state TEXT,
            proposed_state TEXT,
            final_state TEXT,
            timestamp TEXT NOT NULL,
            result TEXT NOT NULL,
            authorization_result TEXT NOT NULL
        )
        """)
        
        # 3. Escalations table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS escalations (
            escalation_id TEXT PRIMARY KEY,
            ticket_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        
        # 4. Follow-up tasks table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS follow_up_tasks (
            task_id TEXT PRIMARY KEY,
            ticket_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL,
            assigned_to TEXT,
            due_at TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        
        conn.commit()
    finally:
        conn.close()

def save_action_proposal(proposal: ActionProposal):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO action_proposals (
            action_id, action_type, account_id, ticket_id, order_id, 
            summary, reason, proposed_changes, created_by, created_at, status, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proposal.action_id,
            proposal.action_type.value,
            proposal.account_id,
            proposal.ticket_id,
            proposal.order_id,
            proposal.summary,
            proposal.reason,
            json.dumps(proposal.proposed_changes),
            proposal.created_by,
            proposal.created_at,
            proposal.status.value,
            proposal.expires_at
        ))
        conn.commit()
    finally:
        conn.close()

def get_action_proposal(action_id: str) -> Optional[ActionProposal]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_proposals WHERE action_id = ?", (action_id,))
        row = cursor.fetchone()
        if not row:
            return None
        r = dict(row)
        r["proposed_changes"] = json.loads(r["proposed_changes"])
        return ActionProposal(**r)
    finally:
        conn.close()

def get_latest_pending_action_for_user(created_by: str) -> Optional[ActionProposal]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM action_proposals WHERE created_by = ? AND status = ? ORDER BY created_at DESC LIMIT 1",
            (created_by, ActionStatus.PENDING_CONFIRMATION.value)
        )
        row = cursor.fetchone()
        if not row:
            return None
        r = dict(row)
        r["proposed_changes"] = json.loads(r["proposed_changes"])
        return ActionProposal(**r)
    finally:
        conn.close()

def update_action_proposal_status(action_id: str, status: ActionStatus):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE action_proposals SET status = ? WHERE action_id = ?", (status.value, action_id))
        conn.commit()
    finally:
        conn.close()

def save_audit_log(entry: AuditLogEntry):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO audit_logs (
            action_id, user_id, role, account_id, ticket_id, order_id, 
            action_type, previous_state, proposed_state, final_state, 
            timestamp, result, authorization_result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.action_id,
            entry.user_id,
            entry.role,
            entry.account_id,
            entry.ticket_id,
            entry.order_id,
            entry.action_type.value,
            entry.previous_state,
            entry.proposed_state,
            entry.final_state,
            entry.timestamp,
            entry.result,
            entry.authorization_result
        ))
        conn.commit()
    finally:
        conn.close()

def get_audit_logs_for_action(action_id: str) -> List[AuditLogEntry]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action_id = ? ORDER BY timestamp DESC", (action_id,))
        rows = cursor.fetchall()
        return [AuditLogEntry(**dict(row)) for row in rows]
    finally:
        conn.close()
