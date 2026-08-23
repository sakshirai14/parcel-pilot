from backend.app.agent.state import AgentState

def router(state: AgentState) -> str:
    """
    Determines next state node.
    - If step count or call budget limit is reached, route to response synthesis.
    - If any limit failure is detected in history, route to response synthesis.
    - Otherwise, route to tool execution if there are pending tool calls.
    """
    from backend.app.agent.nodes import check_history_limits, MAX_LLM_CALLS_PER_REQUEST
    
    # 1. Enforce Hard Step Limit
    if state.get("step_count", 0) >= 6:
        return "response_synthesis"
        
    # 2. Enforce LLM Call Budget
    if state.get("gemini_calls_count", 0) >= MAX_LLM_CALLS_PER_REQUEST:
        return "response_synthesis"
        
    # 3. Check History Limits (Access Denied, Validation Failures, Repeat Errors)
    if check_history_limits(state.get("tool_results", [])) is not None:
        return "response_synthesis"
        
    # 4. Route to Tool Execution
    tool_calls = state.get("tool_calls", [])
    if tool_calls:
        return "tool_execution"
        
    return "response_synthesis"
