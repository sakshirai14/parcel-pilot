import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.app.security.auth import UserContext, UserRole
from backend.app.agent.graph import agent_graph
from backend.app.agent.state import AgentResponse
from backend.app.services.time_service import TimeService
from backend.app.schemas.actions import ActionStatus, ActionType, ActionProposal
from backend.app.data.action_db import (
    initialize_action_tables, 
    get_action_proposal, 
    get_latest_pending_action_for_user, 
    update_action_proposal_status,
    get_audit_logs_for_action
)
from backend.app.tools.execute_action import execute_action, ActionExecutionError
from backend.app.agent.tools import AgentTools
from fastapi.responses import JSONResponse

app = FastAPI(title="ParcelPilot Support API", version="1.0")

@app.exception_handler(ActionExecutionError)
async def action_execution_error_handler(request, exc):
    status_code = 404 if exc.code == "ACTION_NOT_FOUND" else 400
    return JSONResponse(status_code=status_code, content={"status": exc.code, "message": exc.message})

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    initialize_action_tables()
    
    import os
    llm_mode = os.getenv("LLM_MODE", "mock").lower()
    llm_model = os.getenv("LLM_MODEL")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    if llm_mode == "gemini":
        if not gemini_key or gemini_key == "your_gemini_api_key_here":
            raise RuntimeError("FastAPI Startup Failed: LLM_MODE=gemini is configured, but GEMINI_API_KEY is missing or invalid in environment variables.")
        if not llm_model:
            raise RuntimeError("FastAPI Startup Failed: LLM_MODE=gemini is configured, but LLM_MODEL is not set.")
        try:
            import google.genai
            sdk_version = getattr(google.genai, "__version__", "unknown")
            print(f"Startup Config Validation: SDK Version: {sdk_version} | Mode: {llm_mode} | Model: {llm_model}")
        except ImportError:
            raise RuntimeError("FastAPI Startup Failed: LLM_MODE=gemini but official google-genai SDK is not installed.")

class ChatRequest(BaseModel):
    message: str
    user_id: str

class AuthorityResolution(BaseModel):
    conflict_detected: bool
    governing_source: Optional[str] = None
    reason: Optional[str] = None
    conflict_message: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    status: str
    citations: List[Dict[str, Any]]
    tools_used: List[Dict[str, Any]]
    requires_human_review: bool
    requires_confirmation: bool
    proposed_action: Optional[Dict[str, Any]] = None
    authority_resolution: Optional[AuthorityResolution] = None

def authenticate_user(user_id: str) -> UserContext:
    """
    Mocked authentication mapping user_id to UserContext (role and account_id).
    """
    if user_id.startswith("ACCT-"):
        return UserContext(role=UserRole.CUSTOMER, customer_account_id=user_id, user_id=user_id)
    if user_id == "customer-demo":
        return UserContext(role=UserRole.CUSTOMER, customer_account_id="ACCT-001", user_id=user_id)
    if user_id in ("support-demo", "agent-demo", "Rohit", "Maya"):
        return UserContext(role=UserRole.SUPPORT_AGENT, user_id=user_id)
    if user_id in ("ops-demo", "admin-demo", "admin"):
        return UserContext(role=UserRole.OPERATIONS_ADMIN, user_id=user_id)
        
    return UserContext(role=UserRole.CUSTOMER, customer_account_id="ACCT-003", user_id=user_id)

# Action API endpoints
class PrepareActionRequest(BaseModel):
    user_id: str
    action_type: str
    entity_id: str
    details: str

class ConfirmActionRequest(BaseModel):
    user_id: str
    client_payload: Optional[Dict[str, Any]] = None

class ExecuteActionRequest(BaseModel):
    user_id: str
    action_id: str
    client_payload: Optional[Dict[str, Any]] = None

@app.post("/api/actions/prepare")
async def api_prepare_action(req: PrepareActionRequest):
    user_ctx = authenticate_user(req.user_id)
    res = AgentTools.prepare_action(
        action_type=req.action_type,
        entity_id=req.entity_id,
        details=req.details,
        user_context=user_ctx
    )
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("message"))
    if res.get("status") == "UNAUTHORIZED":
        raise HTTPException(status_code=403, detail=res.get("message"))
    if res.get("status") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res

@app.post("/api/actions/confirm")
async def api_confirm_action(req: ExecuteActionRequest):
    user_ctx = authenticate_user(req.user_id)
    res = execute_action(user_ctx, req.action_id, req.client_payload)
    if res.get("status") in ("ACCESS_DENIED", "UNAUTHORIZED"):
        raise HTTPException(status_code=403, detail=res.get("message"))
    if res.get("status") == "ACTION_NOT_FOUND":
        raise HTTPException(status_code=404, detail=res.get("message"))
    if res.get("status") == "ALREADY_EXECUTED":
        return res
    if res.get("status") in ("ACTION_EXPIRED", "ACTION_INVALIDATED", "INVALID_STATUS"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.post("/api/actions/{action_id}/confirm")
async def api_confirm_action_path(action_id: str, req: ConfirmActionRequest):
    user_ctx = authenticate_user(req.user_id)
    res = execute_action(user_ctx, action_id, req.client_payload)
    if res.get("status") in ("ACCESS_DENIED", "UNAUTHORIZED"):
        raise HTTPException(status_code=403, detail=res.get("message"))
    if res.get("status") == "ACTION_NOT_FOUND":
        raise HTTPException(status_code=404, detail=res.get("message"))
    if res.get("status") == "ALREADY_EXECUTED":
        return res
    if res.get("status") in ("ACTION_EXPIRED", "ACTION_INVALIDATED", "INVALID_STATUS"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.post("/api/actions/execute")
async def api_execute_action(req: ExecuteActionRequest):
    user_ctx = authenticate_user(req.user_id)
    res = execute_action(user_ctx, req.action_id, req.client_payload)
    if res.get("status") in ("ACCESS_DENIED", "UNAUTHORIZED"):
        raise HTTPException(status_code=403, detail=res.get("message"))
    if res.get("status") == "ACTION_NOT_FOUND":
        raise HTTPException(status_code=404, detail=res.get("message"))
    if res.get("status") == "ALREADY_EXECUTED":
        return res
    if res.get("status") in ("ACTION_EXPIRED", "ACTION_INVALIDATED", "INVALID_STATUS"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.post("/api/actions/{action_id}/cancel")
async def api_cancel_action(action_id: str, req: ConfirmActionRequest):
    user_ctx = authenticate_user(req.user_id)
    proposal = get_action_proposal(action_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Action not found")
    if user_ctx.role == UserRole.CUSTOMER and proposal.account_id != user_ctx.customer_account_id:
        raise HTTPException(status_code=403, detail="Access denied")
    update_action_proposal_status(action_id, ActionStatus.CANCELLED)
    return {"status": "CANCELLED", "action_id": action_id, "message": "Action cancelled successfully."}

@app.get("/api/actions/{action_id}")
async def api_get_action(action_id: str):
    proposal = get_action_proposal(action_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found.")
    return proposal

@app.get("/api/config")
async def api_get_config():
    import os
    from backend.app.config import LLM_MODEL
    mode = os.getenv("LLM_MODE", "mock").lower()
    return {
        "llm_mode": mode,
        "llm_model": LLM_MODEL
    }

@app.get("/api/actions/{action_id}/audit")
async def api_get_action_audit(action_id: str):
    logs = get_audit_logs_for_action(action_id)
    return logs

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    from backend.app.agent.llm_provider import current_session_request_count, get_llm_provider
    current_session_request_count.set(0)
    provider = get_llm_provider()
    print(f"DIAGNOSTIC - LLM provider class used: {provider.__class__.__name__}")
    user_ctx = authenticate_user(req.user_id)
    
    # Deterministic confirmation flow interception
    message_clean = req.message.strip().lower().rstrip(".")
    confirm_phrases = {"yes", "confirm", "proceed", "do it"}
    
    pending_proposal = get_latest_pending_action_for_user(req.user_id)
    if pending_proposal:
        # Expiration check
        try:
            expires_at_dt = TimeService.parse_timestamp(pending_proposal.expires_at)
            is_expired = datetime.now(TimeService.TIMEZONE) > expires_at_dt
        except Exception:
            is_expired = False
            
        if is_expired:
            update_action_proposal_status(pending_proposal.action_id, ActionStatus.EXPIRED)
            pending_proposal = None
            
    if pending_proposal:
        is_confirm = message_clean in confirm_phrases or "confirm" in message_clean or "proceed" in message_clean or "do it" in message_clean or message_clean.startswith("yes")
        if is_confirm:
            res = execute_action(user_ctx, pending_proposal.action_id)
            if res.get("status") == "EXECUTED":
                if pending_proposal.action_type == ActionType.CANCEL_ORDER.value:
                    ans_text = f"{pending_proposal.order_id} has been successfully cancelled."
                elif pending_proposal.action_type == "CREATE_ESCALATION":
                    ans_text = "The escalation has been successfully created."
                elif pending_proposal.action_type == "UPDATE_TICKET":
                    ans_text = "The ticket has been successfully updated."
                else:
                    ans_text = "Action confirmed and executed successfully."
                return ChatResponse(
                    answer=ans_text,
                    status="EXECUTED",
                    citations=[{"action_id": pending_proposal.action_id}],
                    tools_used=[{"tool": "execute_action", "status": "completed"}],
                    requires_human_review=False,
                    requires_confirmation=False,
                    proposed_action=None
                )
            else:
                status_val = res.get("status", "FAILED")
                return ChatResponse(
                    answer=f"Action execution failed: {res.get('message')}",
                    status=status_val,
                    citations=[],
                    tools_used=[{"tool": "execute_action", "status": "failed"}],
                    requires_human_review=True,
                    requires_confirmation=False,
                    proposed_action=None
                )
        else:
            # User changed/cancelled the action before confirming
            update_action_proposal_status(pending_proposal.action_id, ActionStatus.CANCELLED)

    # Initialize LangGraph state
    initial_state = {
        "user_id": req.user_id,
        "role": user_ctx.role.value,
        "account_id": user_ctx.customer_account_id,
        "query": req.message,
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
    
    start_time = time.time()
    try:
        final_state = agent_graph.invoke(initial_state)
    except Exception as e:
        err_msg = str(e)
        if "quota is temporarily exhausted" in err_msg:
            raise HTTPException(status_code=429, detail="Gemini request quota is temporarily exhausted.")
        if "Gemini is temporarily unavailable" in err_msg:
            raise HTTPException(status_code=503, detail="Gemini is temporarily unavailable. Please try again.")
        raise HTTPException(status_code=500, detail=f"Error executing agent graph: {err_msg}")
        
    latency = time.time() - start_time
    
    tools_used = []
    for tr in final_state.get("tool_results", []):
        tools_used.append({
            "tool": tr.get("tool"),
            "status": "completed"
        })
        
    response_data = ChatResponse(
        answer=final_state.get("answer") or "Could not formulate response.",
        status=final_state.get("decision_status", "ANSWERED"),
        citations=final_state.get("citations", []),
        tools_used=tools_used,
        requires_human_review=(final_state.get("decision_status") in ("CONFLICT_REQUIRES_REVIEW", "INSUFFICIENT_INFORMATION", "MODEL_BUDGET_EXCEEDED")),
        requires_confirmation=final_state.get("requires_confirmation", False),
        proposed_action=final_state.get("proposed_action"),
        authority_resolution=final_state.get("authority_resolution")
    )
    
    import os
    print({
        "event": "agent_trace",
        "query": req.message,
        "user": req.user_id,
        "role": user_ctx.role.value,
        "tools_used": [t["tool"] for t in tools_used],
        "decision_status": response_data.status,
        "latency_sec": round(latency, 4),
        "llm_provider": os.getenv("LLM_MODE", "mock").lower()
    })
    
    return response_data

# Serve frontend production static files (Option B)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Resolve frontend/dist path relative to project root
frontend_dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist"))

if os.path.exists(frontend_dist_path):
    # Mount assets subfolder first
    assets_path = os.path.join(frontend_dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    # Fallback to index.html for React SPA router
    @app.get("/{fallback_path:path}")
    async def spa_fallback(fallback_path: str):
        if fallback_path.startswith("api/") or fallback_path.startswith("api"):
            return JSONResponse(status_code=404, content={"status": "ERROR", "message": "Not Found"})
        
        file_path = os.path.join(frontend_dist_path, fallback_path)
        if fallback_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
            
        return FileResponse(os.path.join(frontend_dist_path, "index.html"))


