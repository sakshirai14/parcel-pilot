import os
import sys

# Add root folder to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environmental variables
from dotenv import load_dotenv
load_dotenv()

# Enforce LLM_MODE=gemini for the test script run
os.environ["LLM_MODE"] = "gemini"

if not os.getenv("GEMINI_API_KEY"):
    print("ERROR: GEMINI_API_KEY is not set in environment.")
    sys.exit(1)

from backend.app.agent.graph import agent_graph

def run_real_gemini_test():
    query = "Cancel ORD-1001"
    print(f"=== REAL GEMINI E2E MANUAL TEST ===")
    print(f"Query: '{query}'")
    print(f"Model: {os.getenv('LLM_MODEL', 'gemini-3.7-flash')}")
    print(f"Mode: {os.environ['LLM_MODE']}")
    print("-" * 50)

    initial_state = {
        "user_id": "ops-demo",
        "role": "OPERATIONS_ADMIN",
        "account_id": "ACCT-001",
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
        "error": None,
        "authority_resolution": None,
        "gemini_calls_count": 0,
        "tool_fingerprints": [],
        "tool_cache": {}
    }

    try:
        final_state = agent_graph.invoke(initial_state)
        print("-" * 50)
        print("=== TEST EXECUTION COMPLETED ===")
        print(f"Decision Status: {final_state.get('decision_status')}")
        print(f"Total Steps: {final_state.get('step_count')}")
        print(f"Total Gemini API Calls: {final_state.get('gemini_calls_count')}")
        print(f"Requires Confirmation: {final_state.get('requires_confirmation')}")
        print("-" * 50)
        print("Final Synthesized Answer:")
        print(final_state.get("answer"))
        print("=" * 50)
    except Exception as e:
        print(f"An error occurred during execution: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_real_gemini_test()
