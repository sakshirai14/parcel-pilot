import os
import unittest
import json
import sqlite3
from datetime import datetime
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.security.auth import UserContext, UserRole
from backend.app.schemas.actions import ActionStatus, ActionType
from backend.app.data.action_db import get_action_proposal, get_audit_logs_for_action, initialize_action_tables

class TestCancelOrderFlow(unittest.TestCase):

    def setUp(self):
        # Force mock mode
        os.environ["LLM_MODE"] = "mock"
        self.client = TestClient(app)
        initialize_action_tables()
        
        # Reset DB state
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM action_proposals")
        cursor.execute("DELETE FROM audit_logs")
        
        # Ensure order ORD-1001 is BOOKED
        cursor.execute("UPDATE orders SET status = 'BOOKED', cancellation_requested_at = NULL WHERE order_id = 'ORD-1001'")
        # Ensure order ORD-2002 is PICKED_UP (ineligible)
        cursor.execute("UPDATE orders SET status = 'PICKED_UP', cancellation_requested_at = NULL WHERE order_id = 'ORD-2002'")
        
        conn.commit()
        conn.close()

    def tearDown(self):
        # Restore DB state for other tests
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'BOOKED', cancellation_requested_at = NULL WHERE order_id = 'ORD-1001'")
        cursor.execute("UPDATE orders SET status = 'PICKED_UP', cancellation_requested_at = NULL WHERE order_id = 'ORD-2002'")
        conn.commit()
        conn.close()

    def test_01_ops_admin_can_prepare_cancel_order(self):
        # Prepare order cancellation as OPERATIONS_ADMIN
        response = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-1001",
            "details": "Cancel requested by customer."
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "PENDING_CONFIRMATION")
        self.assertTrue(data["requires_confirmation"])
        self.assertIn("action_id", data)
        
        # Verify no execution has happened yet
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM orders WHERE order_id = 'ORD-1001'")
        self.assertEqual(cursor.fetchone()[0], "BOOKED")
        conn.close()

    def test_02_ops_admin_confirm_executes_cancellation(self):
        # Prepare
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-1001",
            "details": "Cancel order"
        })
        action_id = res_prep.json()["action_id"]

        # Confirm
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ops-demo"
        })
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(res_conf.json()["status"], "EXECUTED")

        # Verify mutation occurred
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT status, cancellation_requested_at FROM orders WHERE order_id = 'ORD-1001'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "CANCELLED")
        self.assertIsNotNone(row[1])
        conn.close()
        
        # Verify audit log exists
        logs = get_audit_logs_for_action(action_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].result, "SUCCESS")
        self.assertEqual(logs[0].action_type, ActionType.CANCEL_ORDER)

    def test_03_customer_cannot_prepare_or_execute(self):
        # Prepare as customer should fail
        response = self.client.post("/api/actions/prepare", json={
            "user_id": "customer-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-1001",
            "details": "Cancel order"
        })
        self.assertEqual(response.status_code, 403)
        
        # Let's prepare as ops-admin first to get a valid action_id
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-1001",
            "details": "Cancel order"
        })
        action_id = res_prep.json()["action_id"]
        
        # Try to execute as customer -> should be unauthorized
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "customer-demo"
        })
        self.assertEqual(res_conf.status_code, 403)

    def test_04_support_agent_cannot_execute(self):
        # Prepare
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-1001",
            "details": "Cancel order"
        })
        action_id = res_prep.json()["action_id"]

        # Support agent execution is ACCESS_DENIED
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "support-demo"
        })
        self.assertEqual(res_conf.status_code, 403)

    def test_05_ineligible_order_cannot_be_prepared(self):
        # Prepare cancellation for ORD-2002 which is PICKED_UP
        # prepare_action does lookup, but we should make sure that if prepared, execute_action re-validates
        # Prepare:
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-2002",
            "details": "Cancel order"
        })
        self.assertEqual(res_prep.status_code, 200)
        action_id = res_prep.json()["action_id"]
        
        # Try to execute: should return bad request 400 (INVALID_ORDER_STATUS)
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ops-demo"
        })
        self.assertEqual(res_conf.status_code, 400)
        self.assertIn("must be BOOKED to cancel", res_conf.json()["detail"])

    def test_06_already_cancelled_order_cannot_be_cancelled_again(self):
        # Prepare
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-1001",
            "details": "Cancel order"
        })
        action_id = res_prep.json()["action_id"]

        # Update order status directly to CANCELLED in DB to simulate concurrent update
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'CANCELLED' WHERE order_id = 'ORD-1001'")
        conn.commit()
        conn.close()

        # Try to execute
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ops-demo"
        })
        self.assertEqual(res_conf.status_code, 400)
        self.assertIn("must be BOOKED to cancel", res_conf.json()["detail"])

    def test_07_confirmation_without_pending_action_does_nothing(self):
        # Confirming an action that doesn't exist
        res_conf = self.client.post("/api/actions/ACT-NONEXIST/confirm", json={
            "user_id": "ops-demo"
        })
        self.assertEqual(res_conf.status_code, 404)

    def test_08_duplicate_confirmation_prevention(self):
        # Prepare
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-1001",
            "details": "Cancel order"
        })
        action_id = res_prep.json()["action_id"]

        # First confirm
        res_conf1 = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ops-demo"
        })
        self.assertEqual(res_conf1.status_code, 200)
        self.assertEqual(res_conf1.json()["status"], "EXECUTED")

        # Second confirm (should return ALREADY_EXECUTED)
        res_conf2 = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ops-demo"
        })
        self.assertEqual(res_conf2.status_code, 200)
        self.assertEqual(res_conf2.json()["status"], "ALREADY_EXECUTED")

    def test_09_chat_endpoint_e2e_confirmation_flow(self):
        # 1. Ask agent to cancel ORD-1001 as operations admin
        res_chat1 = self.client.post("/api/chat", json={
            "user_id": "ops-demo",
            "message": "Cancel ORD-1001"
        })
        self.assertEqual(res_chat1.status_code, 200)
        data1 = res_chat1.json()
        self.assertTrue(data1["requires_confirmation"])
        self.assertIn("Would you like me to proceed?", data1["answer"])
        
        # 2. Say "Yes, confirm the cancellation"
        res_chat2 = self.client.post("/api/chat", json={
            "user_id": "ops-demo",
            "message": "Yes, confirm the cancellation"
        })
        self.assertEqual(res_chat2.status_code, 200)
        data2 = res_chat2.json()
        self.assertEqual(data2["status"], "EXECUTED")
        self.assertIn("has been successfully cancelled", data2["answer"])

        # Verify mutation occurred
        conn = sqlite3.connect("data/database/parcelpilot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM orders WHERE order_id = 'ORD-1001'")
        self.assertEqual(cursor.fetchone()[0], "CANCELLED")
        conn.close()

    def test_10_should_continue_false_preserves_tool_calls(self):
        from unittest.mock import patch
        from backend.app.agent.llm_provider import MockLLMProvider
        
        with patch.object(MockLLMProvider, 'generate') as mock_gen:
            call_count = 0
            def mock_generate(system_prompt, user_prompt, schema=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return {
                        "tool_calls": [
                            {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-1001"}},
                            {"name": "calculate_entitlement", "arguments": {"entitlement_type": "cancellation", "order_id": "ORD-1001"}}
                        ],
                        "should_continue": True
                    }
                else:
                    return {
                        "tool_calls": [
                            {
                                "name": "prepare_action",
                                "arguments": {
                                    "action_type": "CANCEL_ORDER",
                                    "entity_id": "ORD-1001",
                                    "details": "Prepared action cancellation"
                                }
                            }
                        ],
                        "should_continue": False
                    }
            
            mock_gen.side_effect = mock_generate
            
            res_chat = self.client.post("/api/chat", json={
                "user_id": "ops-demo",
                "message": "Cancel ORD-1001"
            })
            self.assertEqual(res_chat.status_code, 200)
            data = res_chat.json()
            self.assertTrue(data["requires_confirmation"])
            self.assertIn("Would you like me to proceed?", data["answer"])
            
            conn = sqlite3.connect("data/database/parcelpilot.db")
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM action_proposals WHERE order_id = 'ORD-1001'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "PENDING_CONFIRMATION")
            conn.close()

    def test_11_status_query_after_order_cancellation(self):
        from unittest.mock import patch
        from backend.app.agent.llm_provider import MockLLMProvider

        # 1. Cancel the order first
        res_prep = self.client.post("/api/actions/prepare", json={
            "user_id": "ops-demo",
            "action_type": "CANCEL_ORDER",
            "entity_id": "ORD-1001",
            "details": "Cancel order for status query check"
        })
        action_id = res_prep.json()["action_id"]
        
        res_conf = self.client.post(f"/api/actions/{action_id}/confirm", json={
            "user_id": "ops-demo"
        })
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(res_conf.json()["status"], "EXECUTED")
        
        with patch.object(MockLLMProvider, 'generate') as mock_gen:
            mock_gen.return_value = {
                "response": "Order ORD-1001 details: Status CANCELLED.",
                "should_continue": False
            }
            
            # 2. Ask what is the status of ORD-1001
            res_chat = self.client.post("/api/chat", json={
                "user_id": "ops-demo",
                "message": "What is the status of ORD-1001?"
            })
            self.assertEqual(res_chat.status_code, 200)
            data = res_chat.json()
            self.assertNotIn("Action execution requires confirmation", data["answer"])
            self.assertNotIn("order cancellation cannot be executed directly in chat", data["answer"])
            self.assertIn("cancelled", data["answer"].lower())

if __name__ == "__main__":
    unittest.main()
