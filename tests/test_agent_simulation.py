import unittest
from unittest.mock import patch, MagicMock
from backend.app.agent.graph import agent_graph

class TestAgentSimulation(unittest.TestCase):

    @patch("backend.app.agent.nodes.get_active_llm")
    def test_simulated_e2e_cancellation_flow(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        # We simulate the exact sequence of LLMCallResponse outputs from the orchestrator model:
        # Step 1: Request operational data lookup for ORD-1001
        # Step 2: Request customer agreement search
        # Step 3: Request standard policy SOP search
        # Step 4: Request cancellation entitlement evaluation
        # Step 5: Synthesize the final answer and close the loop (should_continue=False)
        mock_llm.generate.side_effect = [
            {
                "tool_calls": [{"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-1001"}}],
                "response": None,
                "should_continue": True
            },
            {
                "tool_calls": [{"name": "search_documents", "arguments": {"query": "Northstar agreement cancellation", "customer_account_id": "ACCT-001"}}],
                "response": None,
                "should_continue": True
            },
            {
                "tool_calls": [{"name": "search_documents", "arguments": {"query": "cancellation policy SOP", "customer_account_id": "ACCT-001"}}],
                "response": None,
                "should_continue": True
            },
            {
                "tool_calls": [{"name": "calculate_entitlement", "arguments": {"entitlement_type": "cancellation", "order_id": "ORD-1001"}}],
                "response": None,
                "should_continue": True
            },
            {
                "tool_calls": [],
                "response": "Under Northstar's enterprise agreement, the cancellation fee is waived for this scenario. The customer-specific agreement takes precedence over the general cancellation policy. You can cancel ORD-1001 with no cancellation fee.",
                "should_continue": False
            }
        ]

        initial_state = {
            "user_id": "usr-test-1",
            "role": "SUPPORT_AGENT",
            "account_id": "ACCT-001",
            "query": "Can Northstar cancel ORD-1001 without a cancellation fee?",
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

        # Run E2E Graph
        result = agent_graph.invoke(initial_state)

        # Assert correct final state
        self.assertEqual(result["decision_status"], "CONFLICT_REQUIRES_REVIEW")
        self.assertIn("cancellation fee is waived", result["answer"])
        self.assertEqual(result["gemini_calls_count"], 5)
        self.assertTrue(result["step_count"] >= 5)

        # Check tool sequence execution
        tools_run = [tr["tool"] for tr in result["tool_results"]]
        self.assertEqual(tools_run[0], "lookup_operational_data")
        self.assertEqual(tools_run[1], "search_documents")
        self.assertEqual(tools_run[2], "search_documents")
        self.assertEqual(tools_run[3], "calculate_entitlement")

if __name__ == "__main__":
    unittest.main()
