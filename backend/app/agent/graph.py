from langgraph.graph import StateGraph, END
from backend.app.agent.state import AgentState
from backend.app.agent.nodes import (
    query_understanding_node,
    planner_node,
    tool_execution_node,
    response_synthesis_node
)
from backend.app.agent.router import router

def create_agent_graph():
    # Initialize graph with our TypedDict State
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("query_understanding", query_understanding_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("tool_execution", tool_execution_node)
    workflow.add_node("response_synthesis", response_synthesis_node)
    
    # Define edges
    workflow.set_entry_point("query_understanding")
    workflow.add_edge("query_understanding", "planner")
    
    # Add conditional router path after planning
    workflow.add_conditional_edges(
        "planner",
        router,
        {
            "tool_execution": "tool_execution",
            "response_synthesis": "response_synthesis"
        }
    )
    
    # Tool execution returns to planner for next iteration/reasoning step
    workflow.add_edge("tool_execution", "planner")
    
    # Response synthesis completes the workflow
    workflow.add_edge("response_synthesis", END)
    
    return workflow.compile()

# Compile single instance
agent_graph = create_agent_graph()
