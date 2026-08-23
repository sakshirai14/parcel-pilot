import os
from typing import Dict, Any, List, Optional
from backend.app.agent.state import AgentState
from backend.app.agent.tools import AgentTools
from backend.app.agent.llm_provider import get_llm_provider
from backend.app.agent.prompts import SYSTEM_PROMPT
from backend.app.security.auth import UserContext, UserRole
from backend.app.services.source_resolution import SourceResolver

# Dynamic lookup of LLM provider to support test overrides cleanly
def get_active_llm():
    return get_llm_provider()

import json
from pydantic import ValidationError
from backend.app.agent.llm_provider import (
    LookupOperationalDataCall,
    SearchDocumentsCall,
    CalculateEntitlementCall,
    CalculateSLACall,
    PrepareActionCall
)

MAX_LLM_CALLS_PER_REQUEST = int(os.getenv("LLM_MAX_CALLS_PER_REQUEST", "5"))

def get_tool_fingerprint(name: str, arguments: Dict[str, Any]) -> str:
    """
    Generates a unique deterministic string fingerprint for a tool call.
    """
    normalized = {}
    if isinstance(arguments, dict):
        for k, v in sorted(arguments.items()):
            if v is not None and v != "":
                if isinstance(v, str):
                    normalized[k] = v.strip().lower()
                else:
                    normalized[k] = v
    return f"{name}:{json.dumps(normalized)}"

def get_cache_key(name: str, arguments: Dict[str, Any], account_scope: Optional[str]) -> str:
    """
    Generates a cache key including the tool fingerprint and account scope.
    """
    fp = get_tool_fingerprint(name, arguments)
    scope = (account_scope or "").strip().lower()
    return f"{fp}::scope:{scope}"

def validate_tool_call(tool_call: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Validates a tool call object using Pydantic schemas.
    """
    tool_name = tool_call.get("name")
    args = tool_call.get("arguments") or {}
    
    if not tool_name:
        return {
            "status": "INVALID_TOOL_CALL",
            "tool": "",
            "message": "Tool name is missing"
        }

    try:
        if tool_name == "lookup_operational_data":
            LookupOperationalDataCall(name=tool_name, arguments=args)
        elif tool_name == "search_documents":
            # Semantic check: query must not be empty/blank
            query = args.get("query")
            if isinstance(query, str) and query.strip() == "":
                return {
                    "status": "INVALID_TOOL_CALL",
                    "tool": tool_name,
                    "message": "Argument 'query' must be a non-empty string"
                }
            SearchDocumentsCall(name=tool_name, arguments=args)
        elif tool_name == "calculate_entitlement":
            CalculateEntitlementCall(name=tool_name, arguments=args)
        elif tool_name == "calculate_sla":
            CalculateSLACall(name=tool_name, arguments=args)
        elif tool_name == "prepare_action":
            PrepareActionCall(name=tool_name, arguments=args)
        else:
            return {
                "status": "INVALID_TOOL_CALL",
                "tool": tool_name,
                "message": f"Unknown tool: {tool_name}"
            }
    except ValidationError as e:
        first_err = e.errors()[0]
        field_loc = " -> ".join(str(loc) for loc in first_err["loc"])
        msg = f"Validation failed at '{field_loc}': {first_err['msg']}"
        return {
            "status": "INVALID_TOOL_CALL",
            "tool": tool_name,
            "message": msg
        }
    return None

def check_history_limits(tool_results: List[Dict[str, Any]]) -> Optional[str]:
    """
    Checks history of tool results to enforce error recovery limits.
    """
    invalid_count = 0
    error_count = 0
    
    for tr in tool_results:
        res = tr.get("result") or {}
        status = res.get("status") if isinstance(res, dict) else None
        
        if status == "UNAUTHORIZED" or status == "ACCESS_DENIED":
            return "ACCESS_DENIED"
            
        if status == "INVALID_TOOL_CALL" or status == "DUPLICATE_TOOL_CALL":
            invalid_count += 1
            if invalid_count > 1:
                return "TOOL_VALIDATION_FAILED"
                
        if status == "ERROR":
            error_count += 1
            if error_count > 1:
                return "TOOL_EXECUTION_ERROR"
                
    return None

def query_understanding_node(state: AgentState) -> Dict[str, Any]:
    """
    Initial node to parse/log the request.
    """
    return {
        "step_count": state.get("step_count", 0),
        "tool_calls": [],
        "tool_results": [],
        "evidence": [],
        "source_conflicts": [],
        "error": None
    }

def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    Planner node: Invokes LLM or Mock provider to retrieve tool calls or generate final answer.
    """
    from backend.app.agent.llm_provider import LLMCallResponse
    
    # 1. Enforce Hard Agent Step Limit
    step_count = state.get("step_count", 0)
    if step_count >= 6:
        print(f"DIAGNOSTIC - Hard Agent Step Limit reached ({step_count} >= 6). Terminating loop.")
        return {
            "tool_calls": [],
            "answer": "The request could not be resolved automatically and should be escalated.",
            "decision_status": "INSUFFICIENT_INFORMATION",
            "step_count": step_count
        }

    # 2. Enforce LLM Call Budget
    gemini_calls_count = state.get("gemini_calls_count", 0)
    if gemini_calls_count >= MAX_LLM_CALLS_PER_REQUEST:
        print(f"DIAGNOSTIC - Max LLM Calls Limit reached ({gemini_calls_count} >= {MAX_LLM_CALLS_PER_REQUEST}). Terminating loop.")
        return {
            "tool_calls": [],
            "answer": "The AI reasoning budget was reached. Please retry or escalate.",
            "decision_status": "MODEL_BUDGET_EXCEEDED",
            "step_count": step_count,
            "gemini_calls_count": gemini_calls_count
        }

    # 3. Check History Limits
    history_error = check_history_limits(state.get("tool_results", []))
    if history_error:
        print(f"DIAGNOSTIC - History error limit hit: {history_error}. Terminating loop.")
        if history_error == "ACCESS_DENIED":
            answer = "Access Denied: You do not have permissions to access this order."
            decision_status = "UNAUTHORIZED"
        elif history_error == "TOOL_VALIDATION_FAILED":
            custom_msg = None
            for tr in state.get("tool_results", []):
                res = tr.get("result") or {}
                if "Unable to safely retrieve" in str(res.get("message", "")):
                    custom_msg = res.get("message")
                    break
            answer = custom_msg or "Tool validation failed. The request could not be resolved automatically and should be escalated."
            decision_status = "INSUFFICIENT_INFORMATION"
        else: # TOOL_EXECUTION_ERROR
            answer = "A backend tool error occurred. The request could not be resolved automatically and should be escalated."
            decision_status = "INSUFFICIENT_INFORMATION"
            
        return {
            "tool_calls": [],
            "answer": answer,
            "decision_status": decision_status,
            "step_count": step_count,
            "gemini_calls_count": gemini_calls_count
        }

    # Compile execution history for LLM context
    history_lines = []
    for tr in state.get("tool_results", []):
        history_lines.append(f"Tool {tr.get('tool')} executed with result: {tr.get('result')}")
        
    history = "\n".join(history_lines)
    user_prompt = f"Query: {state.get('query')}\nRole: {state.get('role')}\nAccount ID: {state.get('account_id')}\nHistory:\n{history}"
    
    tool_instructions = """
Available tools you can call:

1. `lookup_operational_data`
   - Purpose: Retrieve operational order, customer account, or support ticket data.
   - Arguments:
     * `query_type` (Required): Must be one of: "account", "order", "ticket".
     * `entity_id` (Required): Must be a non-empty string target ID (e.g. "ORD-1001", "ACCT-001", "TKT-501").
   - VALID CALL: {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-1001"}}
   - INVALID CALL: {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": null}}

2. `search_documents`
   - Purpose: Retrieve relevant sections from standard policies, standard operating procedures (SOPs), or customer-specific enterprise agreements.
   - Arguments:
     * `query` (Required): Search string query terms. Must be a non-empty, non-blank string.
     * `customer_account_id` (Optional): String filter to narrow searches to specific accounts (e.g. "ACCT-001").
   - VALID CALL: {"name": "search_documents", "arguments": {"query": "Northstar cancellation terms", "customer_account_id": "ACCT-001"}}
   - INVALID CALL: {"name": "search_documents", "arguments": {"query": ""}}

3. `calculate_entitlement`
   - Purpose: Performs deterministic calculation of refund eligibility, fees, or late-pickup credit entitlements.
   - Arguments:
     * `entitlement_type` (Required): Must be one of: "cancellation", "service_credit".
     * `order_id` (Required): Order ID string to evaluate (e.g. "ORD-1001").
   - VALID CALL: {"name": "calculate_entitlement", "arguments": {"entitlement_type": "cancellation", "order_id": "ORD-1001"}}
   - INVALID CALL: {"name": "calculate_entitlement", "arguments": {"entitlement_type": "cancellation", "order_id": null}}

4. `calculate_sla`
   - Purpose: Evaluates ticket details against response targets to determine SLA breach status.
   - Arguments:
     * `created_at` (Required): Ticket creation timestamp string (e.g., "2026-08-16 10:30:00").
     * `severity` (Required): Ticket severity level (e.g., "P1", "P2", "P3").
     * `plan` (Required): Customer support SLA plan name (e.g., "Enterprise", "Growth", "Standard").
     * `account_id` (Required): Target account ID (e.g. "ACCT-001").
   - VALID CALL: {"name": "calculate_sla", "arguments": {"created_at": "2026-08-16 10:30:00", "severity": "P1", "plan": "Enterprise", "account_id": "ACCT-001"}}
   - INVALID CALL: {"name": "calculate_sla", "arguments": {"created_at": null, "severity": "P1", "plan": "Enterprise", "account_id": null}}

5. `prepare_action`
   - Purpose: Drafts/stages action requests requiring human/manager confirmation (e.g. escalation).
   - Arguments:
      * `action_type` (Required): Must be one of: "CREATE_ESCALATION", "UPDATE_TICKET", "CREATE_FOLLOW_UP", "CANCEL_ORDER".
      * `entity_id` (Required): Target ticket or entity ID (e.g., "TKT-501", "ORD-1001").
      * `details` (Required): Textual reasons or description.
    - VALID CALL: {"name": "prepare_action", "arguments": {"action_type": "CREATE_ESCALATION", "entity_id": "TKT-501", "details": "Policy conflict identified."}}
    - INVALID CALL: {"name": "prepare_action", "arguments": {"action_type": "CREATE_ESCALATION", "entity_id": null, "details": ""}}

CRITICAL INSTRUCTIONS & TOOL CONTRACT PROTOCOLS:
- NEVER pass null or empty string for a required argument.
- If required information (like order ID, account ID, severity, or plan name) is missing or unavailable, do NOT guess or call tools with null/blank arguments. Stop and set should_continue=false, request clarification, or set decision_status="INSUFFICIENT_INFORMATION".
- NEVER invent an order ID, account ID, ticket ID, filename, or policy.
- Use tools to retrieve factual information instead of relying on prior knowledge.

TOOL DEPENDENCY & RESOLUTION GUIDELINES:
1. If the user provides an explicit order ID, FIRST retrieve the order operational data via lookup_operational_data.
2. Once the order data is retrieved and identifies a customer account (e.g., account_id="ACCT-001"), use that account context to search customer-specific agreements.
3. Customer-specific enterprise agreements (e.g. Northstar, LumenWorks) override general standard operating policies (SOPs). Use search_documents to fetch the agreement terms.
4. Always call calculate_entitlement to determine standard and customer-agreement-based cancellation eligibility, fees, or service credit amounts. Do NOT perform calculations yourself.
5. Historical tickets are context only and must never override current policies or agreements.
"""
    full_system_prompt = SYSTEM_PROMPT + "\n" + tool_instructions

    print(f"\nDIAGNOSTIC - Planner Node Request:")
    print(f"  Query: {state.get('query')}")
    print(f"  Step Count: {state.get('step_count', 0)}")
    print(f"  Available Tools: lookup_operational_data, search_documents, calculate_entitlement, calculate_sla, prepare_action")
    if history:
        print(f"  History:\n{history}")
    
    # Generate decision
    response = get_active_llm().generate(full_system_prompt, user_prompt, schema=LLMCallResponse)
    gemini_calls_count += 1
    
    tool_calls = response.get("tool_calls", [])
    answer = response.get("response")
    should_continue = response.get("should_continue", True)
    
    if tool_calls:
        should_continue = True
    elif not should_continue:
        tool_calls = []
        
    if not should_continue and not tool_calls and not answer:
        tool_results = state.get("tool_results", [])
        for tr in reversed(tool_results):
            if tr.get("tool") == "lookup_operational_data":
                res_data = tr.get("result") or {}
                if res_data.get("status") == "SUCCESS" and isinstance(res_data.get("data"), dict):
                    entity_data = res_data["data"]
                    if "order_id" in entity_data:
                        answer = f"The current status of {entity_data['order_id']} is {entity_data.get('status')}."
                        break
                    elif "ticket_id" in entity_data:
                        answer = f"Ticket {entity_data['ticket_id']} has status {entity_data.get('status')} and priority {entity_data.get('priority')}."
                        break
                    elif "account_id" in entity_data:
                        answer = f"Account details for {entity_data['account_id']}: Plan is {entity_data.get('plan')}, status is {entity_data.get('status')}."
                        break
    
    # Normalise tool calls from Pydantic model format if returned as dicts with object shapes
    normalized_calls = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            normalized_calls.append(tc)
        else:
            normalized_calls.append({
                "name": getattr(tc, "name", ""),
                "arguments": getattr(tc, "arguments", {})
            })

    print(f"DIAGNOSTIC - Planner Node Response:")
    print(f"  Selected Tool Calls: {normalized_calls}")
    print(f"  Synthesized Answer: {answer}")
    
    return {
        "tool_calls": normalized_calls,
        "answer": answer,
        "step_count": step_count + 1,
        "gemini_calls_count": gemini_calls_count
    }

def is_repeated_failure(tc: dict, tool_results: list) -> bool:
    name = tc.get("name")
    args = tc.get("arguments", {})
    current_fp = get_tool_fingerprint(name, args)
    
    for tr in tool_results:
        tr_name = tr.get("tool")
        tr_args = tr.get("arguments", {})
        tr_result = tr.get("result") or {}
        tr_status = tr_result.get("status") if isinstance(tr_result, dict) else None
        
        if tr_status in ("INVALID_TOOL_CALL", "DUPLICATE_TOOL_CALL", "ERROR"):
            tr_fp = get_tool_fingerprint(tr_name, tr_args)
            if current_fp == tr_fp:
                return True
    return False

def tool_execution_node(state: AgentState) -> Dict[str, Any]:
    """
    Node to execute tool calls determined by the planner.
    """
    tool_calls = state.get("tool_calls", [])
    tool_results = list(state.get("tool_results", []))
    evidence = list(state.get("evidence", []))
    source_conflicts = list(state.get("source_conflicts", []))
    proposed_action = state.get("proposed_action")
    requires_confirmation = state.get("requires_confirmation", False)
    tool_fingerprints = list(state.get("tool_fingerprints", []))
    tool_cache = dict(state.get("tool_cache", {}))
    
    user_context = UserContext(
        role=UserRole(state.get("role", "CUSTOMER")),
        customer_account_id=state.get("account_id"),
        user_id=state.get("user_id")
    )
    account_scope = state.get("account_id")
    
    for tc in tool_calls:
        tool_name = tc.get("name")
        args = tc.get("arguments", {})
        
        # Log raw tool call details safely
        arg_types = {k: type(v).__name__ for k, v in args.items()} if isinstance(args, dict) else {}
        print(f"[RAW TOOL CALL]\nname={tool_name}\narguments={args}\nargument types={arg_types}")
        
        # Check repeated failure thrashing guard
        if is_repeated_failure(tc, tool_results):
            print(f"DIAGNOSTIC - Repeated failed tool call detected for '{tool_name}' with args {args}. Terminating.")
            tool_results.append({
                "tool": tool_name,
                "arguments": args,
                "result": {
                    "status": "INVALID_TOOL_CALL",
                    "message": "Unable to safely retrieve the required record because the tool request was invalid. Escalation recommended."
                }
            })
            continue

        # 1. Pydantic & Semantic Validation
        val_error = validate_tool_call(tc)
        if val_error:
            print(f"DIAGNOSTIC - Tool Validation FAILED for '{tool_name}': {val_error['message']}")
            tool_results.append({
                "tool": tool_name,
                "arguments": args,
                "result": val_error
            })
            continue

        # 2. RBAC Validation
        role = state.get("role", "CUSTOMER")
        state_account = state.get("account_id")
        
        rbac_failed = False
        if role == "CUSTOMER":
            if tool_name == "lookup_operational_data":
                query_type = args.get("query_type")
                entity_id = args.get("entity_id")
                if query_type == "account" and entity_id != state_account:
                    rbac_failed = True
            elif tool_name == "search_documents":
                customer_account_id = args.get("customer_account_id") or state_account
                if customer_account_id != state_account:
                    rbac_failed = True
            elif tool_name == "calculate_sla":
                account_id = args.get("account_id")
                if account_id != state_account:
                    rbac_failed = True

        if rbac_failed:
            print(f"DIAGNOSTIC - RBAC FAILED: Customer {state_account} tried to access resource unauthorized.")
            tool_results.append({
                "tool": tool_name,
                "arguments": args,
                "result": {
                    "status": "UNAUTHORIZED",
                    "message": "Access Denied: You do not have permissions to perform this operation."
                }
            })
            continue

        # 3. Duplicate Call Fingerprint Check
        fp = get_tool_fingerprint(tool_name, args)
        if fp in tool_fingerprints:
            print(f"DIAGNOSTIC - Duplicate Tool Call Detected: {fp}")
            tool_results.append({
                "tool": tool_name,
                "arguments": args,
                "result": {
                    "status": "DUPLICATE_TOOL_CALL",
                    "message": "This tool request has already been executed."
                }
            })
            continue
            
        # Register fingerprint
        tool_fingerprints.append(fp)

        # 4. Cache Check (for cacheable tools)
        cacheable = tool_name in ("lookup_operational_data", "search_documents", "calculate_sla", "calculate_entitlement")
        cache_key = get_cache_key(tool_name, args, account_scope)
        if cacheable and cache_key in tool_cache:
            print(f"DIAGNOSTIC - Tool Cache HIT for key: {cache_key}")
            cached_result = tool_cache[cache_key]
            tool_results.append({
                "tool": tool_name,
                "arguments": args,
                "result": cached_result
            })
            if tool_name == "search_documents" and isinstance(cached_result, list):
                for item in cached_result:
                    evidence.append(item)
            continue

        print(f"DIAGNOSTIC - Tool Execution Node: Executing '{tool_name}' with args: {args}")
        result = None
        try:
            if tool_name == "search_documents":
                customer_account_id = args.get("customer_account_id") or state.get("account_id")
                # Extra RBAC safety check
                if state.get("role") == "CUSTOMER" and customer_account_id != state.get("account_id"):
                    result = {"status": "UNAUTHORIZED", "message": "Access Denied"}
                else:
                    result = AgentTools.search_documents(
                        query=args.get("query"),
                        customer_account_id=customer_account_id
                    )
                    for item in result:
                        evidence.append(item)
                    
            elif tool_name == "lookup_operational_data":
                result = AgentTools.lookup_operational_data(
                    query_type=args.get("query_type"),
                    entity_id=args.get("entity_id"),
                    user_context=user_context
                )
                
            elif tool_name == "calculate_entitlement":
                result = AgentTools.calculate_entitlement(
                    entitlement_type=args.get("entitlement_type"),
                    order_id=args.get("order_id"),
                    user_context=user_context
                )
                
            elif tool_name == "calculate_sla":
                result = AgentTools.calculate_sla(
                    created_at=args.get("created_at"),
                    severity=args.get("severity"),
                    plan=args.get("plan"),
                    account_id=args.get("account_id")
                )
                
            elif tool_name == "prepare_action":
                result = AgentTools.prepare_action(
                    action_type=args.get("action_type"),
                    entity_id=args.get("entity_id"),
                    details=args.get("details"),
                    user_context=user_context
                )
                proposed_action = result
                requires_confirmation = (result.get("status") == "PENDING_CONFIRMATION") if isinstance(result, dict) else False
                
            else:
                result = {"status": "ERROR", "message": f"Unknown tool: {tool_name}"}
        except Exception as e:
            result = {"status": "ERROR", "message": str(e)}
            
        print(f"DIAGNOSTIC - Tool Execution Result for '{tool_name}': {result}")
        tool_results.append({
            "tool": tool_name,
            "arguments": args,
            "result": result
        })
        
        # Save to request-level cache if successful and cacheable
        if cacheable and isinstance(result, dict) and result.get("status") not in ("ERROR", "UNAUTHORIZED"):
            tool_cache[cache_key] = result
        elif cacheable and isinstance(result, list): # search_documents returns list of dicts
            tool_cache[cache_key] = result
        
    # If document search was run, execute conflict resolution on retrieved evidence
    if any(tr.get("tool") == "search_documents" for tr in tool_results) and evidence:
        res = SourceResolver.resolve_conflicts(evidence, state.get("account_id"))
        if res.conflict_detected:
            source_conflicts.append(res.model_dump())
            
    # Clear tool calls once executed
    return {
        "tool_calls": [],
        "tool_results": tool_results,
        "evidence": evidence,
        "source_conflicts": source_conflicts,
        "proposed_action": proposed_action,
        "requires_confirmation": requires_confirmation,
        "tool_fingerprints": tool_fingerprints,
        "tool_cache": tool_cache
    }

def response_synthesis_node(state: AgentState) -> Dict[str, Any]:
    """
    Compiles final answers, citations, and decision states.
    """
    evidence = state.get("evidence", [])
    tool_results = state.get("tool_results", [])
    source_conflicts = state.get("source_conflicts", [])
    proposed_action = state.get("proposed_action")
    requires_confirmation = state.get("requires_confirmation", False)
    
    citations = []
    
    # 1. Document citations
    for item in evidence:
        citation = {
            "type": "DOCUMENT",
            "source_name": item.get("source_name"),
            "description": item.get("section") or "Standard policy/agreement terms",
            "page": item.get("page"),
            "authority_status": item.get("document_status") or "CURRENT"
        }
        if citation not in citations:
            citations.append(citation)
            
    # 2. Operational citations
    for tr in tool_results:
        res_data = tr.get("result")
        if isinstance(res_data, dict) and res_data.get("status") == "SUCCESS" and "data" in res_data:
            entity_data = res_data.get("data")
            if entity_data:
                # Form entity citation
                if "order_id" in entity_data:
                    citations.append({
                        "type": "OPERATIONAL_DATA",
                        "source_name": entity_data["order_id"],
                        "description": "Order record from operational database",
                        "authority_status": "DATABASE_RECORD"
                    })
                elif "ticket_id" in entity_data:
                    citations.append({
                        "type": "OPERATIONAL_DATA",
                        "source_name": entity_data["ticket_id"],
                        "description": "Ticket record from operational database",
                        "authority_status": "DATABASE_RECORD"
                    })
                elif "account_id" in entity_data:
                    citations.append({
                        "type": "OPERATIONAL_DATA",
                        "source_name": entity_data["account_id"],
                        "description": "Customer account profile",
                        "authority_status": "DATABASE_RECORD"
                    })

    # Evaluate decision status
    status = state.get("decision_status") or "ANSWERED"
    conflict_detected = len(source_conflicts) > 0
    requires_human_review = (status in ("CONFLICT_REQUIRES_REVIEW", "INSUFFICIENT_INFORMATION", "LLM_CALL_LIMIT_REACHED"))
    
    if status == "ANSWERED":
        # Check if any tool returned errors
        for tr in tool_results:
            res_data = tr.get("result")
            if isinstance(res_data, dict):
                if res_data.get("status") == "UNAUTHORIZED":
                    status = "UNAUTHORIZED"
                elif res_data.get("status") == "INSUFFICIENT_INFORMATION":
                    status = "INSUFFICIENT_INFORMATION"
                    requires_human_review = True
                elif res_data.get("status") == "CONFLICT_REQUIRES_REVIEW":
                    status = "CONFLICT_REQUIRES_REVIEW"
                    requires_human_review = True
                
    if conflict_detected:
        status = "CONFLICT_REQUIRES_REVIEW"
        requires_human_review = True
        
    # Compile authority resolution summary
    authority_resolution = None
    if source_conflicts:
        latest_conflict = source_conflicts[-1]
        authority_resolution = {
            "conflict_detected": latest_conflict.get("conflict_detected", False),
            "governing_source": latest_conflict.get("selected_source"),
            "reason": latest_conflict.get("reason"),
            "conflict_message": "Customer agreement overrides current standard policy." if latest_conflict.get("conflict_detected") else None
        }
    elif evidence:
        highest = None
        for item in evidence:
            src_name = item.get("source_name")
            if src_name:
                highest = src_name
                break
        if highest:
            authority_resolution = {
                "conflict_detected": False,
                "governing_source": highest,
                "reason": "Standard operational document/policy rules govern this request.",
                "conflict_message": None
            }

    # Final answer formatting
    answer = state.get("answer") or "Could not formulate an answer."
    
    # Hard safety invariant: derive actual mutation completion from trusted backend state
    # We do not trust the LLM to verify if a state change / order cancellation actually completed.
    # In our chat agent flow, no write mutation is executed (only prepared/queried).
    import re
    query_str = (state.get("query") or "").strip().lower()
    is_cancellation_query = any(w in query_str for w in ("cancel", "cancellation"))
    is_cancellation_request = query_str.startswith("cancel ")
    role = state.get("role", "CUSTOMER")
    
    if is_cancellation_query:
        # Check if the answer mistakenly claims the order has been cancelled or processed
        claims_completion = any(pattern in answer.lower() for pattern in ("processed", "has been cancelled", "was cancelled", "successfully cancelled", "order is cancelled", "cancellation request for"))
        if claims_completion or is_cancellation_request:
            # Determine fee information from calculation results in tool_results
            fee_info = "with no cancellation fee"
            for tr in tool_results:
                if tr.get("tool") == "calculate_entitlement":
                    res_val = tr.get("result") or {}
                    if res_val.get("status") == "CONFIDENT":
                        fee = res_val.get("fee", 0.0)
                        fee_info = f"with a fee of INR {fee}" if fee > 0 else "with no cancellation fee"
                        break
            
            order_match = re.search(r"ORD-\d+", (state.get("query") or ""))
            order_str = order_match.group(0) if order_match else "your order"
            
            if role == "CUSTOMER":
                answer = f"{order_str} is eligible for cancellation {fee_info}, but I did not cancel it because your account does not have permission to execute the cancellation."
            elif role == "OPERATIONS_ADMIN" and proposed_action and proposed_action.get("action_type") == "CANCEL_ORDER":
                answer = f"{order_str} is eligible for cancellation {fee_info}. Would you like me to proceed?"
            else:
                # For support agents or operations admins (if no proposed action exists/unauthorized), explain that confirmation is required but cannot be prepared
                answer = f"{order_str} is eligible for cancellation {fee_info}. Action execution requires confirmation, but order cancellation cannot be executed directly in chat."

    requested_sources = any(w in query_str for w in ("source", "where did you get", "evidence", "provenance"))
    if role == "CUSTOMER" and not requested_sources:
        # Strip parenthesized file/page references
        answer = re.sub(r"\([A-Za-z0-9_-]+\.pdf(?:,\s*(?:page|p\.)\s*\d+)?\)", "", answer)
        answer = re.sub(r"[A-Za-z0-9_-]+\.pdf", "", answer)
        # Strip attribution/provenance phrasing
        answer = re.sub(r"(?i)(?:according to|per|based on|as stated in|under)\s+(?:the\s+|your\s+)?(?:[A-Za-z0-9_-]+\s+)*(?:enterprise agreement|customer agreement|agreement|standard operating procedure|sop|standard policy|policy document|policy)(?:,\s*(?:page|p\.)\s*\d+)?(?:,\s*)?", "", answer)
        answer = re.sub(r"(?i)\bpage\s+\d+\b", "", answer)
        # Clean up punctuation and formatting leftovers
        answer = re.sub(r"\(\s*\)", "", answer)
        answer = re.sub(r"^[,\.\s]+", "", answer)
        answer = re.sub(r"\s+", " ", answer).strip()
        if answer:
            answer = answer[0].upper() + answer[1:]

    return {
        "decision_status": status,
        "citations": citations,
        "answer": answer,
        "authority_resolution": authority_resolution
    }
