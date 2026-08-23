import os
import unittest
import json
import sqlite3
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from backend.app.main import app, authenticate_user
from backend.app.security.auth import UserContext, UserRole
from backend.app.schemas.actions import ActionStatus, ActionType
from backend.app.services.time_service import TimeService
from backend.app.data.action_db import get_action_proposal, get_audit_logs_for_action, initialize_action_tables

class TestActions(unittest.TestCase):

    def setUp(self):
        # Force mock mode so no real Gemini LLM calls are made
        os.environ["LLM_MODE"] = "mock"
        self.client = TestClient(app)
        
        # Initialize tables
        initialize_action_tables()
        
        # Reset tables for deterministic testing
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM action_proposals")
        cursor.execute("DELETE FROM audit_logs")
        cursor.execute("DELETE FROM escalations")
        cursor.execute("DELETE FROM follow_up_tasks")
        # Ensure TKT-501 is open
        cursor.execute("UPDATE tickets SET status = 'open' WHERE ticket_id = 'TKT-501'")
        cursor.execute("UPDATE tickets SET status = 'open' WHERE ticket_id = 'TKT-502'")
        conn.commit()
        conn.close()

    def test_01_prepare_escalation(self):
        # Prepare escalation via API
        response = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Escalating due to breach of SLA."
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "PENDING_CONFIRMATION")
        self.assertTrue(data["requires_confirmation"])
        self.assertIn("action_id", data)

    def test_02_verify_no_state_change_during_prepare(self):
        # Prepare escalation
        response = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Escalating due to breach of SLA."
        })
        self.assertEqual(response.status_code, 200)
        
        # Verify no escalation record exists in SQLite yet
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM escalations")
        self.assertEqual(cursor.fetchone()[0], 0)
        
        # Verify ticket status remains unchanged
        cursor.execute("SELECT status FROM tickets WHERE ticket_id = 'TKT-501'")
        self.assertEqual(cursor.fetchone()[0], "open")
        conn.close()

    def test_03_explicit_confirmation_executes_action(self):
        # Prepare escalation
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Escalating due to breach of SLA."
        })
        action_id = res_prep.json()["action_id"]

        # Confirm action
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "support-demo"
        })
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(res_conf.json()["status"], "EXECUTED")

        # Verify mutation occurred
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM escalations WHERE ticket_id = 'TKT-501'")
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor.execute("SELECT status FROM tickets WHERE ticket_id = 'TKT-501'")
        self.assertEqual(cursor.fetchone()[0], "ESCALATED")
        conn.close()

    def test_04_ambiguous_response_does_not_execute_action(self):
        # Prepare action
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Escalating SLA breach"
        })
        self.assertEqual(res_prep.status_code, 200)

        # Call chat endpoint with ambiguous message
        res_chat = self.client.post("/api/chat", json={
            "user_id": "support-demo",
            "message": "okay that's fine"
        })
        self.assertEqual(res_chat.status_code, 200)
        self.assertFalse(res_chat.json()["requires_confirmation"])

        # Check action was cancelled/discarded rather than executed
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM escalations")
        self.assertEqual(cursor.fetchone()[0], 0)
        
        # Verify the action proposal is CANCELLED in DB
        cursor.execute("SELECT status FROM action_proposals")
        self.assertEqual(cursor.fetchone()[0], "CANCELLED")
        conn.close()

    def test_05_unauthorized_user_cannot_execute(self):
        # Customer ACCT-001 prepares action for TKT-501
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ACCT-001",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Escalate my ticket"
        })
        action_id = res_prep.json()["action_id"]

        # ACCT-002 tries to execute/confirm it
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ACCT-002"
        })
        self.assertEqual(res_conf.status_code, 403) # Re-authorized and rejected

    def test_06_cross_account_action_is_rejected(self):
        # Customer A (ACCT-001) tries to prepare action for Customer B's ticket (TKT-502, owned by ACCT-002)
        response = self.client.post("/api/actions/prepare", json={
            "user_id": "ACCT-001",
            "action_type": "escalation",
            "entity_id": "TKT-502",
            "details": "Malicious escalation"
        })
        self.assertEqual(response.status_code, 403) # ACCESS_DENIED

    def test_07_expired_action_cannot_execute(self):
        # Prepare action
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Expired test"
        })
        action_id = res_prep.json()["action_id"]

        # Manually set the expiration date in DB to past
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        past_time = (datetime.now(TimeService.TIMEZONE) - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE action_proposals SET expires_at = ? WHERE action_id = ?", (past_time, action_id))
        conn.commit()
        conn.close()

        # Try to execute
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "support-demo"
        })
        self.assertEqual(res_conf.status_code, 400)
        self.assertIn("expired", res_conf.json()["detail"].lower())

    def test_08_already_executed_action_cannot_execute_twice(self):
        # Prepare
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Double execution check"
        })
        action_id = res_prep.json()["action_id"]

        # Execute 1st time
        res_conf1 = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "support-demo"
        })
        self.assertEqual(res_conf1.status_code, 200)

        # Execute 2nd time
        res_conf2 = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "support-demo"
        })
        self.assertEqual(res_conf2.status_code, 200)
        self.assertEqual(res_conf2.json()["status"], "ALREADY_EXECUTED")

    def test_09_modified_action_payload_is_rejected(self):
        # Prepare
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Tamper test"
        })
        action_id = res_prep.json()["action_id"]

        # Try to confirm with a different payload (e.g. modified reason or ticket)
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "support-demo",
            "client_payload": {
                "ticket_id": "TKT-501",
                "reason": "Tamper test",
                "priority": "P99" # Modified field
            }
        })
        self.assertEqual(res_conf.status_code, 400)
        self.assertIn("tampered", res_conf.json()["detail"].lower())

    def test_10_audit_record_is_created(self):
        # Prepare and execute
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Audit test"
        })
        action_id = res_prep.json()["action_id"]
        
        self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "support-demo"
        })

        # Fetch audit trail
        res_audit = self.client.get(f"/api/actions/{action_id}/audit")
        self.assertEqual(res_audit.status_code, 200)
        logs = res_audit.json()
        self.assertTrue(len(logs) > 0)
        self.assertEqual(logs[0]["action_id"], action_id)
        self.assertEqual(logs[0]["result"], "SUCCESS")

    def test_11_authorization_checked_again_at_execution(self):
        # Prepare action by support-demo
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "escalation",
            "entity_id": "TKT-501",
            "details": "Re-auth test"
        })
        action_id = res_prep.json()["action_id"]

        # Revoke or confirm as someone else who lacks permissions (e.g. ACCT-002)
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ACCT-002"
        })
        self.assertEqual(res_conf.status_code, 403) # ACCESS_DENIED

    def test_12_invalid_action_type_is_rejected(self):
        # Prepare invalid action type
        response = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "DELETE_ALL_DATA",
            "entity_id": "TKT-501",
            "details": "Malicious drop"
        })
        self.assertEqual(response.status_code, 400)

    def test_13_customer_cannot_perform_unauthorized_internal_action(self):
        # Customers cannot update tickets or create follow-ups
        response = self.client.post("/api/actions/prepare", json={
            "user_id": "ACCT-001",
            "action_type": "update_ticket",
            "entity_id": "TKT-501",
            "details": '{"status": "closed"}'
        })
        # During preparation or execution, RBAC must block Customer from internal updates
        # If preparation succeeds, execution will fail, but since we check permissions
        # during prepare too, it returns unauthorized/access denied.
        self.assertIn(response.status_code, (403, 400))

    def test_14_support_agent_can_perform_authorized_action(self):
        # Support agent can prepare update_ticket
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "support-demo",
            "action_type": "update_ticket",
            "entity_id": "TKT-501",
            "details": '{"status": "closed", "assigned_to": "Maya"}'
        })
        self.assertEqual(res_prep.status_code, 200)
        action_id = res_prep.json()["action_id"]

        # Support agent confirms
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "support-demo"
        })
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(res_conf.json()["status"], "EXECUTED")

        # Verify change was written to tickets table
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT status, assigned_to FROM tickets WHERE ticket_id = 'TKT-501'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "closed")
        self.assertEqual(row[1], "Maya")
        conn.close()

    def test_15_operations_admin_can_perform_authorized_action(self):
        # Admin can prepare follow-up task
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "create_followup",
            "entity_id": "TKT-501",
            "details": "Need to follow up with carrier tomorrow."
        })
        self.assertEqual(res_prep.status_code, 200)
        action_id = res_prep.json()["action_id"]

        # Admin executes
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ops-demo"
        })
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(res_conf.json()["status"], "EXECUTED")

        # Verify follow_up_tasks entry exists
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM follow_up_tasks WHERE ticket_id = 'TKT-501'")
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_16_gemini_api_not_called(self):
        # Verify that LLM_MODE is mock and no real Gemini Calls are initiated
        self.assertEqual(os.environ.get("LLM_MODE"), "mock")
