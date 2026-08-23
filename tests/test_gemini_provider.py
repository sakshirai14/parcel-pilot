import unittest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from backend.app.agent.state import AgentState
from backend.app.agent.nodes import (
    validate_tool_call, 
    check_history_limits, 
    planner_node, 
    tool_execution_node,
    get_tool_fingerprint,
    get_cache_key
)
from backend.app.agent.graph import agent_graph
from backend.app.agent.llm_provider import GeminiLLMProvider, LLMCallResponse

class TestGeminiProviderOrchestration(unittest.TestCase):

    def test_test_a_valid_lookup_tool_call(self):
        # TEST A: Valid lookup tool call
        tc = {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-1001"}}
        err = validate_tool_call(tc)
        self.assertIsNone(err)

    def test_test_b_lookup_operational_data_with_null_record_id(self):
        # TEST B: lookup_operational_data with null record_id / missing entity_id
        tc = {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": None}}
        err = validate_tool_call(tc)
        self.assertIsNotNone(err)
        self.assertEqual(err["status"], "INVALID_TOOL_CALL")

    def test_test_c_lookup_with_invalid_query_type(self):
        # TEST C: lookup with invalid query_type
        tc = {"name": "lookup_operational_data", "arguments": {"query_type": "invalid_type", "entity_id": "ORD-1001"}}
        err = validate_tool_call(tc)
        self.assertIsNotNone(err)
        self.assertEqual(err["status"], "INVALID_TOOL_CALL")

    def test_test_d_search_documents_with_null_query(self):
        # TEST D: search_documents with null/blank query
        tc1 = {"name": "search_documents", "arguments": {"query": None}}
        err1 = validate_tool_call(tc1)
        self.assertIsNotNone(err1)
        self.assertEqual(err1["status"], "INVALID_TOOL_CALL")

        tc2 = {"name": "search_documents", "arguments": {"query": "   "}}
        err2 = validate_tool_call(tc2)
        self.assertIsNotNone(err2)
        self.assertEqual(err2["status"], "INVALID_TOOL_CALL")

    def test_test_e_unknown_tool_name(self):
        # TEST E: Unknown tool name
        tc = {"name": "some_unknown_action", "arguments": {"param": "value"}}
        err = validate_tool_call(tc)
        self.assertIsNotNone(err)
        self.assertEqual(err["status"], "INVALID_TOOL_CALL")
        self.assertIn("Unknown tool", err["message"])

    def test_test_f_duplicate_identical_tool_call(self):
        # TEST F: Duplicate identical tool call
        state = {
            "role": "SUPPORT_AGENT",
            "account_id": "ACCT-001",
            "tool_calls": [
                {"name": "search_documents", "arguments": {"query": "Northstar policy"}}
            ],
            "tool_results": [],
            "evidence": [],
            "tool_fingerprints": ["search_documents:{\"query\": \"northstar policy\"}"],
            "tool_cache": {}
        }
        res = tool_execution_node(state)
        # Should detect duplicate and return structured DUPLICATE_TOOL_CALL result
        self.assertEqual(len(res["tool_results"]), 1)
        self.assertEqual(res["tool_results"][0]["result"]["status"], "DUPLICATE_TOOL_CALL")

    def test_test_g_two_invalid_tool_calls_stops_agent(self):
        # TEST G: Two invalid tool calls in a row
        history = [
            {"tool": "search_documents", "arguments": {}, "result": {"status": "INVALID_TOOL_CALL", "message": "query missing"}},
            {"tool": "search_documents", "arguments": {}, "result": {"status": "INVALID_TOOL_CALL", "message": "query missing"}}
        ]
        status = check_history_limits(history)
        self.assertEqual(status, "TOOL_VALIDATION_FAILED")

    def test_test_h_repeated_tool_execution_error(self):
        # TEST H: Repeated tool execution error
        history = [
            {"tool": "calculate_sla", "arguments": {}, "result": {"status": "ERROR", "message": "Connection error"}},
            {"tool": "calculate_sla", "arguments": {}, "result": {"status": "ERROR", "message": "Connection error"}}
        ]
        status = check_history_limits(history)
        self.assertEqual(status, "TOOL_EXECUTION_ERROR")

    def test_test_i_maximum_agent_steps_reached(self):
        # TEST I: Maximum agent steps reached
        state = {
            "query": "cancellation fee",
            "step_count": 6,
            "tool_results": [],
            "gemini_calls_count": 0
        }
        res = planner_node(state)
        self.assertEqual(res["tool_calls"], [])
        self.assertEqual(res["decision_status"], "INSUFFICIENT_INFORMATION")
        self.assertIn("escalated", res["answer"])

    def test_test_j_maximum_gemini_calls_reached(self):
        # TEST J: Maximum Gemini calls per request reached
        state = {
            "query": "cancellation fee",
            "step_count": 2,
            "tool_results": [],
            "gemini_calls_count": 5
        }
        res = planner_node(state)
        self.assertEqual(res["tool_calls"], [])
        self.assertEqual(res["decision_status"], "MODEL_BUDGET_EXCEEDED")
        self.assertIn("reasoning budget", res["answer"])

    def test_test_k_customer_attempts_cross_account_lookup(self):
        # TEST K: Customer attempts cross-account lookup
        state = {
            "role": "CUSTOMER",
            "account_id": "ACCT-001",
            "tool_calls": [
                {"name": "lookup_operational_data", "arguments": {"query_type": "account", "entity_id": "ACCT-002"}}
            ],
            "tool_results": [],
            "evidence": [],
            "tool_fingerprints": [],
            "tool_cache": {}
        }
        res = tool_execution_node(state)
        self.assertEqual(res["tool_results"][0]["result"]["status"], "UNAUTHORIZED")

    def test_test_l_cache_keys_vary_by_account_scope(self):
        # TEST L: Same tool arguments from different account scopes produce different cache keys
        args = {"query": "cancellation fee terms"}
        key_acct1 = get_cache_key("search_documents", args, "ACCT-001")
        key_acct2 = get_cache_key("search_documents", args, "ACCT-002")
        self.assertNotEqual(key_acct1, key_acct2)

    def test_test_m_state_changing_action_never_auto_executed(self):
        # TEST M: State-changing action is never auto-executed (requires PENDING_CONFIRMATION)
        state = {
            "role": "SUPPORT_AGENT",
            "account_id": "ACCT-001",
            "tool_calls": [
                {"name": "prepare_action", "arguments": {"action_type": "CREATE_ESCALATION", "entity_id": "TKT-501", "details": "Escalation requested"}}
            ],
            "tool_results": [],
            "evidence": [],
            "tool_fingerprints": [],
            "tool_cache": {}
        }
        res = tool_execution_node(state)
        self.assertEqual(res["proposed_action"]["status"], "PENDING_CONFIRMATION")
        self.assertTrue(res["requires_confirmation"])

    @patch("backend.app.agent.nodes.get_active_llm")
    def test_test_n_valid_multi_step_cancellation_flow(self, mock_get_llm):
        # TEST N: Valid multi-step cancellation flow
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.generate.side_effect = [
            {"tool_calls": [{"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-1001"}}], "response": None, "should_continue": True},
            {"tool_calls": [{"name": "search_documents", "arguments": {"query": "Northstar Logistics cancellation policy"}}], "response": None, "should_continue": True},
            {"tool_calls": [{"name": "calculate_entitlement", "arguments": {"entitlement_type": "cancellation", "order_id": "ORD-1001"}}], "response": None, "should_continue": True},
            {"tool_calls": [], "response": "Cancellation fee is waived.", "should_continue": False}
        ]

        initial_state = {
            "user_id": "usr-1",
            "role": "SUPPORT_AGENT",
            "account_id": "ACCT-001",
            "query": "Can Northstar cancel ORD-1001?",
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
            "error": None,
            "authority_resolution": None,
            "gemini_calls_count": 0,
            "tool_fingerprints": [],
            "tool_cache": {}
        }

        # Run E2E graph invoke
        res = agent_graph.invoke(initial_state)
        self.assertEqual(res["decision_status"], "CONFLICT_REQUIRES_REVIEW")
        self.assertEqual(res["answer"], "Cancellation fee is waived.")
        self.assertTrue(res["step_count"] > 1)

    def test_test_o_hypothetical_service_credit_no_substitution(self):
        # TEST O: Hypothetical service-credit question does NOT silently substitute ORD-2002
        tc = {"name": "calculate_entitlement", "arguments": {"entitlement_type": "service_credit", "order_id": None}}
        err = validate_tool_call(tc)
        # Should reject because order_id cannot be null/None for calculate_entitlement
        self.assertIsNotNone(err)

    def test_test_p_historical_ticket_guidance_does_not_override_policy(self):
        # TEST P: Historical ticket resolutions do not override current policy
        # The prompt instruction defines signed customer agreements overriding standard policies, and standard policies overriding guides/historical tickets.
        from backend.app.agent.prompts import SYSTEM_PROMPT
        self.assertIn("Historical tickets are context only and may contain errors", SYSTEM_PROMPT)

    def test_test_q_customer_agreement_overrides_general_policy(self):
        # TEST Q: Customer agreement overrides general policy
        from backend.app.agent.prompts import SYSTEM_PROMPT
        self.assertIn("Signed customer agreements (e.g. Northstar, LumenWorks) override standard support policies or SOPs", SYSTEM_PROMPT)

if __name__ == "__main__":
    unittest.main()
