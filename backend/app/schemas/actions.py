from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel

class ActionType(str, Enum):
    CREATE_ESCALATION = "CREATE_ESCALATION"
    UPDATE_TICKET = "UPDATE_TICKET"
    CREATE_FOLLOWUP = "CREATE_FOLLOWUP"
    CANCEL_ORDER = "CANCEL_ORDER"

class ActionStatus(str, Enum):
    PREPARED = "PREPARED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class ActionProposal(BaseModel):
    action_id: str
    action_type: ActionType
    account_id: Optional[str] = None
    ticket_id: Optional[str] = None
    order_id: Optional[str] = None
    summary: str
    reason: str
    proposed_changes: Dict[str, Any] = {}
    created_by: str
    created_at: str
    status: ActionStatus
    expires_at: str

class AuditLogEntry(BaseModel):
    audit_id: Optional[int] = None
    action_id: str
    user_id: str
    role: str
    account_id: Optional[str] = None
    ticket_id: Optional[str] = None
    order_id: Optional[str] = None
    action_type: ActionType
    previous_state: Optional[str] = None
    proposed_state: Optional[str] = None
    final_state: Optional[str] = None
    timestamp: str
    result: str
    authorization_result: str
