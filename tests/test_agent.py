import unittest
import os
from backend.app.agent.graph import agent_graph
from backend.app.security.auth import UserContext, UserRole
from backend.app.agent.state import AgentState

class TestAgent(unittest.TestCase):

    def setUp(self):
        # Force mock mode for agent tests
        os.environ["LLM_MODE"] = "mock"

    def _run_agent(self, query: str, user_id: str, role: str, account_id: str = None) -> dict:
        initial_state = {
            "user_id": user_id,
            "role": role,
            "account_id": account_id,
            "query": query,
            "plan": [],
            "tool_calls": [],
            "tool_results": [],
            "evidence": [],
            "source_conflicts": [],
            "decision_status": "ANSWERED",
            "answer": None,
            "citations": [],
            "proposed_action": None,
            "requires_confirmation": False,
            "step_count": 0,
            "error": None
        }
        return agent_graph.invoke(initial_state)

    def test_simple_order_lookup(self):
        # 1. Simple order lookup
        res = self._run_agent("Look up ORD-1001", "support-demo", "SUPPORT_AGENT")
        self.assertEqual(res["decision_status"], "ANSWERED")
        self.assertTrue(any(tr["tool"] == "lookup_operational_data" for tr in res["tool_results"]))

    def test_simple_ticket_lookup(self):
        # 2. Simple ticket lookup
        res = self._run_agent("Look up ticket TKT-501", "support-demo", "SUPPORT_AGENT")
        self.assertEqual(res["decision_status"], "ANSWERED")
        self.assertTrue(any(tr["tool"] == "lookup_operational_data" for tr in res["tool_results"]))

    def test_cancellation_question_flow(self):
        # 3. Cancellation question requiring order + account + agreement + policy + calculation
        res = self._run_agent("Can Northstar cancel ORD-1001 without a cancellation fee?", "customer-demo", "CUSTOMER", "ACCT-001")
        self.assertEqual(res["decision_status"], "CONFLICT_REQUIRES_REVIEW")
        self.assertTrue(any(tr["tool"] == "calculate_entitlement" for tr in res["tool_results"]))
        self.assertIn("cancellation fee is waived", res["answer"])

    def test_service_credit_question_flow(self):
        # 4. Service-credit question requiring operational data + agreement/SOP + calculation
        res = self._run_agent("A pickup is three hours late because of carrier fault. Should I get a service credit? My order is ORD-2002.", "customer-demo", "CUSTOMER", "ACCT-002")
        self.assertEqual(res["decision_status"], "ANSWERED")
        self.assertTrue(any(tr["tool"] == "calculate_entitlement" for tr in res["tool_results"]))

    def test_sla_question(self):
        # 5. SLA question
        res = self._run_agent("What is the SLA breach status of my ticket created at 2026-08-16 10:30?", "customer-demo", "CUSTOMER", "ACCT-001")
        self.assertEqual(res["decision_status"], "ANSWERED")
        self.assertTrue(any(tr["tool"] == "calculate_sla" for tr in res["tool_results"]))

    def test_cross_account_leakage(self):
        # 6. Customer asking for another customer's data
        # Customer ACCT-001 asks for ORD-2002 (LumenWorks)
        res = self._run_agent("Show me ORD-2002.", "customer-demo", "CUSTOMER", "ACCT-001")
        self.assertEqual(res["decision_status"], "UNAUTHORIZED")
        self.assertIn("Access Denied", res["answer"])

    def test_deprecated_policy_conflict(self):
        # 7. Deprecated policy conflict
        res = self._run_agent("Show me the conflict between policies for cancellation.", "support-demo", "SUPPORT_AGENT")
        self.assertEqual(res["decision_status"], "CONFLICT_REQUIRES_REVIEW")

    def test_historical_ticket_conflict(self):
        # 8. Historical ticket conflicting with current policy
        res = self._run_agent("Look up TKT-450 historical resolution conflict", "support-demo", "SUPPORT_AGENT")
        self.assertEqual(res["decision_status"], "CONFLICT_REQUIRES_REVIEW")

    def test_customer_agreement_overrides_policy(self):
        # 9. Customer-specific agreement overriding general policy
        res = self._run_agent("Can Northstar cancel ORD-1001 without a cancellation fee?", "customer-demo", "CUSTOMER", "ACCT-001")
        self.assertIn("takes precedence over the general cancellation policy", res["answer"])

    def test_insufficient_information(self):
        # 10. Insufficient information
        # Evaluate calculation with missing order carrier fault parameter
        res = self._run_agent("Evaluate service credit for ORD-9999", "customer-demo", "CUSTOMER", "ACCT-001")
        # Under mock scenario, if carrier_fault is not set, it should report insufficient info
        # Let's verify status
        self.assertEqual(res["decision_status"], "INSUFFICIENT_INFORMATION")

    def test_human_escalation_recommendation(self):
        # 11. Human escalation recommendation
        res = self._run_agent("Please escalate my ticket because of a conflict.", "customer-demo", "CUSTOMER", "ACCT-001")
        self.assertEqual(res["decision_status"], "CONFLICT_REQUIRES_REVIEW")

    def test_maximum_agent_step_protection(self):
        # 12. Maximum-agent-step protection
        initial_state = {
            "user_id": "cust-1",
            "role": "CUSTOMER",
            "account_id": "ACCT-001",
            "query": "Can Northstar cancel ORD-1001?",
            "plan": [],
            "tool_calls": [{"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-1001"}}],
            "tool_results": [],
            "evidence": [],
            "source_conflicts": [],
            "decision_status": "ANSWERED",
            "answer": None,
            "citations": [],
            "proposed_action": None,
            "requires_confirmation": False,
            "step_count": 8,  # Triggers loop limit router immediately
            "error": None,
            "authority_resolution": None,
            "gemini_calls_count": 0,
            "tool_fingerprints": [],
            "tool_cache": {}
        }
        res = agent_graph.invoke(initial_state)
        # Should exit directly to response_synthesis
        self.assertTrue(res["step_count"] >= 8)
        self.assertEqual(res["decision_status"], "INSUFFICIENT_INFORMATION")

    def test_mock_mode_safeguards(self):
        # 13. Mock mode without GEMINI_API_KEY
        self.assertEqual(os.getenv("LLM_MODE"), "mock")
        # Ensure it runs without needing GEMINI_API_KEY
        res = self._run_agent("Look up ORD-1001", "support-demo", "SUPPORT_AGENT")
        self.assertIsNotNone(res["answer"])

    def test_cancellation_eligibility_question(self):
        # 1. Eligibility question: "Can Northstar cancel ORD-1001 without a cancellation fee?"
        res = self._run_agent("Can Northstar cancel ORD-1001 without a cancellation fee?", "customer-demo", "CUSTOMER", "ACCT-001")
        self.assertEqual(res["decision_status"], "CONFLICT_REQUIRES_REVIEW")
        self.assertTrue(any(tr["tool"] == "calculate_entitlement" for tr in res["tool_results"]))
        self.assertIn("cancellation fee is waived", res["answer"])
        self.assertNotIn("permission to execute", res["answer"])

    def test_cancellation_unauthorized_customer_request(self):
        # 2. Action request from unauthorized customer: "Cancel ORD-1001."
        res = self._run_agent("Cancel ORD-1001.", "customer-demo", "CUSTOMER", "ACCT-001")
        self.assertEqual(res["decision_status"], "CONFLICT_REQUIRES_REVIEW")
        self.assertEqual(
            res["answer"],
            "ORD-1001 is eligible for cancellation with no cancellation fee, but I did not cancel it because your account does not have permission to execute the cancellation."
        )
        self.assertIsNone(res.get("proposed_action"))
        self.assertFalse(res.get("requires_confirmation"))

    def test_cancellation_support_agent_request(self):
        # 3. Action request from support agent (not executable directly in chat): "Cancel ORD-1001."
        res = self._run_agent("Cancel ORD-1001.", "support-demo", "SUPPORT_AGENT")
        self.assertEqual(
            res["answer"],
            "ORD-1001 is eligible for cancellation with no cancellation fee. Action execution requires confirmation, but order cancellation cannot be executed directly in chat."
        )
        self.assertIsNone(res.get("proposed_action"))
        self.assertFalse(res.get("requires_confirmation"))

    def test_cancellation_eligibility_does_not_contain_sources(self):
        res = self._run_agent("Can Northstar cancel ORD-1001 without a cancellation fee?", "customer-demo", "CUSTOMER", "ACCT-001")
        ans = res["answer"].lower()
        self.assertNotIn(".pdf", ans)
        self.assertNotIn("page 1", ans)
        self.assertNotIn("according to", ans)
        self.assertNotIn("source", ans)
        self.assertNotIn("document", ans)
        self.assertNotIn("retrieved", ans)

    def test_user_explicit_source_request(self):
        res = self._run_agent("Where did you get that information?", "customer-demo", "CUSTOMER", "ACCT-001")
        ans = res["answer"].lower()
        self.assertIn(".pdf", ans)
        self.assertIn("page 1", ans)

if __name__ == "__main__":
    unittest.main()
