from typing import List, Dict, Any, Optional, TypedDict
from pydantic import BaseModel

class AgentState(TypedDict):
    user_id: str
    role: str
    account_id: Optional[str]
    query: str
    plan: List[str]
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    source_conflicts: List[Dict[str, Any]]
    decision_status: str
    answer: Optional[str]
    citations: List[Dict[str, Any]]
    proposed_action: Optional[Dict[str, Any]]
    requires_confirmation: bool
    step_count: int
    error: Optional[str]
    authority_resolution: Optional[Dict[str, Any]]
    gemini_calls_count: int
    tool_fingerprints: List[str]
    tool_cache: Dict[str, Any]

class AgentResponse(BaseModel):
    status: str
    answer: str
    citations: List[Dict[str, Any]] = []
    data_points: List[Dict[str, Any]] = []
    confidence: float = 1.0
    conflict_detected: bool = False
    requires_human_review: bool = False
    proposed_action: Optional[Dict[str, Any]] = None
    requires_confirmation: bool = False
    tools_used: List[str] = []
