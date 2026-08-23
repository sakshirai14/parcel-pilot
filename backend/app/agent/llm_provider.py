import os
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from contextvars import ContextVar
import time
from backend.app.config import GEMINI_API_KEY, LLM_MODEL

current_session_request_count: ContextVar[int] = ContextVar("current_session_request_count", default=0)

from typing import Literal, Union

class LookupOperationalDataArgs(BaseModel):
    query_type: Literal["account", "order", "ticket"] = Field(description="Operational record type to look up")
    entity_id: str = Field(description="Unique ID of the entity (e.g. ORD-1001, ACCT-001, TKT-501)")

class SearchDocumentsArgs(BaseModel):
    query: str = Field(description="Search string query for policy sheets or agreements")
    customer_account_id: Optional[str] = Field(default=None, description="Optional account ID to filter documents")

class CalculateEntitlementArgs(BaseModel):
    entitlement_type: Literal["cancellation", "service_credit"] = Field(description="The entitlement calculation type")
    order_id: str = Field(description="Order ID to evaluate")

class CalculateSLAArgs(BaseModel):
    created_at: str = Field(description="Ticket creation timestamp in YYYY-MM-DD HH:MM:SS format")
    severity: str = Field(description="Ticket severity (e.g., standard, urgent)")
    plan: str = Field(description="Customer support SLA plan (e.g. Gold, Silver, Platinum)")
    account_id: str = Field(description="Target account ID")

class PrepareActionArgs(BaseModel):
    action_type: Literal["CREATE_ESCALATION", "UPDATE_TICKET", "CREATE_FOLLOW_UP", "CANCEL_ORDER"] = Field(description="Staged action type")
    entity_id: str = Field(description="Target entity ID to apply the action to")
    details: str = Field(description="Textual reasons or details for the proposal")

class LookupOperationalDataCall(BaseModel):
    name: Literal["lookup_operational_data"] = "lookup_operational_data"
    arguments: LookupOperationalDataArgs

class SearchDocumentsCall(BaseModel):
    name: Literal["search_documents"] = "search_documents"
    arguments: SearchDocumentsArgs

class CalculateEntitlementCall(BaseModel):
    name: Literal["calculate_entitlement"] = "calculate_entitlement"
    arguments: CalculateEntitlementArgs

class CalculateSLACall(BaseModel):
    name: Literal["calculate_sla"] = "calculate_sla"
    arguments: CalculateSLAArgs

class PrepareActionCall(BaseModel):
    name: Literal["prepare_action"] = "prepare_action"
    arguments: PrepareActionArgs

ToolCall = Union[
    LookupOperationalDataCall,
    SearchDocumentsCall,
    CalculateEntitlementCall,
    CalculateSLACall,
    PrepareActionCall
]

class LLMCallResponse(BaseModel):
    response: Optional[str] = Field(default=None, description="Final answer to the user. This field is REQUIRED and must be populated with a natural conversational answer when should_continue is False.")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Ordered list of tool calls to execute.")
    should_continue: bool = Field(description="True if the agent needs to invoke more tools, False if final response is complete.")

class LLMProvider:
    def generate(self, system_prompt: str, user_prompt: str, schema: Optional[BaseModel] = None) -> Dict[str, Any]:
        raise NotImplementedError

class MockLLMProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str, schema: Optional[BaseModel] = None) -> Dict[str, Any]:
        raw_res = self._generate_raw(system_prompt, user_prompt, schema)
        tool_calls = raw_res.get("tool_calls") or []
        text_resp = raw_res.get("text_response") or raw_res.get("response")
        should_continue = len(tool_calls) > 0
        return {
            "response": text_resp,
            "tool_calls": tool_calls,
            "should_continue": should_continue
        }

    def _generate_raw(self, system_prompt: str, user_prompt: str, schema: Optional[BaseModel] = None) -> Dict[str, Any]:
        """
        Determines mock tool planning or final response based on keywords.
        """
        user_prompt_lower = user_prompt.lower()
        
        # Extract the original user query line to inspect intent safely
        original_query = ""
        for line in user_prompt.split("\n"):
            if line.startswith("Query:"):
                original_query = line.lower()
                break
        
        # Check if user query explicitly asks for source/where did you get
        if any(w in original_query for w in ("source", "where did you get", "evidence", "provenance")):
            return {
                "text_response": "I retrieved this information from the Northstar Logistics Enterprise Agreement (05_Northstar_Logistics_Enterprise_Agreement.pdf, page 1)."
            }

        # Check intent in the original query
        is_cancel_intent = any(k in original_query for k in ("cancel", "fee", "credit"))
        
        # 1. Simple order lookup for ORD-1001 (no cancel/credit terms in query)
        if "ord-1001" in user_prompt_lower and not is_cancel_intent:
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-1001"}}
                    ]
                }
            else:
                return {
                    "text_response": "Order ORD-1001 details: Booked at 2026-08-16 09:00, fee 4200 INR."
                }
                
        # 2. Cancellation scenario for Northstar ORD-1001 (cancel / fee present)
        elif ("ord-1001" in user_prompt_lower or "ord-9999" in user_prompt_lower) and is_cancel_intent:
            # Check if it's the insufficient info test
            if "insufficient" in user_prompt_lower or "evaluate service credit" in user_prompt_lower:
                if "executed" not in user_prompt_lower:
                    return {
                        "tool_calls": [
                            {"name": "calculate_entitlement", "arguments": {"entitlement_type": "service_credit", "order_id": "ORD-9999"}}
                        ]
                    }
                else:
                    return {
                        "text_response": "Missing information: Carrier fault is not set. Cannot determine credit."
                    }
            # Otherwise normal cancellation
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-1001"}}
                    ]
                }
            elif "lookup_operational_data" in user_prompt_lower and "search_documents" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "search_documents", "arguments": {"query": "Northstar Logistics Enterprise Agreement cancellation"}}
                    ]
                }
            elif "search_documents" in user_prompt_lower and "calculate_entitlement" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "calculate_entitlement", "arguments": {"entitlement_type": "cancellation", "order_id": "ORD-1001"}}
                    ]
                }
            else:
                if "operations_admin" in user_prompt_lower:
                    if "prepare_action" not in user_prompt_lower:
                        return {
                            "tool_calls": [
                                {"name": "prepare_action", "arguments": {"action_type": "CANCEL_ORDER", "entity_id": "ORD-1001", "details": "Confirm order cancellation with fee waiver."}}
                            ]
                        }
                    else:
                        return {
                            "text_response": "ORD-1001 is eligible for cancellation with no cancellation fee. Would you like me to proceed?"
                        }
                return {
                    "text_response": "Under Northstar's enterprise agreement, the cancellation fee is waived for this scenario. The customer-specific agreement takes precedence over the general cancellation policy. You can cancel ORD-1001 with no cancellation fee."
                }
                
        # 3. Service credit scenario for ORD-2002
        elif "ord-2002" in user_prompt_lower:
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-2002"}}
                    ]
                }
            elif "unauthorized" in user_prompt_lower or "access denied" in user_prompt_lower or "access_denied" in user_prompt_lower:
                return {
                    "text_response": "Access Denied: You do not have permissions to access this order."
                }
            elif "lookup_operational_data" in user_prompt_lower and "calculate_entitlement" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "calculate_entitlement", "arguments": {"entitlement_type": "service_credit", "order_id": "ORD-2002"}}
                    ]
                }
            else:
                return {
                    "text_response": "Under LumenWorks' service agreement, the customer receives a fixed INR 300 service credit since the pickup delay exceeded 4 hours due to carrier fault. This overrides the default policy rules."
                }

        # 3b. Hypothetical service credit question (three hours late)
        elif "credit" in user_prompt_lower and "three hours" in user_prompt_lower:
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "search_documents", "arguments": {"query": "service credit SOP"}}
                    ]
                }
            else:
                if "acct-002" in user_prompt_lower:
                    return {
                        "text_response": "For LumenWorks Customer (ACCT-002), a 3-hour delay is not eligible for a service credit because your customer agreement overrides standard policy and sets a 4-hour delay threshold for carrier-fault credits."
                    }
                elif "acct-001" in user_prompt_lower:
                    return {
                        "text_response": "For Northstar Logistics (ACCT-001), a 3-hour delay is eligible for a service credit. Under the standard Service Credit SOP (which governs your account), a delay exceeding 2 hours due to carrier fault is eligible for a service credit of 10% of the shipment fee (capped at 500 INR)."
                    }
                else:
                    return {
                        "text_response": "Under the standard Service Credit SOP, a 3-hour pickup delay due to carrier fault is eligible for a service credit because it exceeds the 2-hour threshold. However, custom enterprise agreements may set different thresholds. Please provide your order or account details so I can confirm the exact terms."
                    }
                
        # 4. Simple Ticket Lookup or Escalation
        elif "tkt-501" in user_prompt_lower or ("escalate" in user_prompt_lower and "conflict" in user_prompt_lower):
            if "escalate" in user_prompt_lower:
                if "executed" not in user_prompt_lower:
                    return {
                        "tool_calls": [
                            {"name": "prepare_action", "arguments": {"action_type": "escalation", "entity_id": "TKT-501", "details": "Escalating due to policy conflict."}},
                            {"name": "search_documents", "arguments": {"query": "Support Policy v3"}}
                        ]
                    }
                else:
                    return {
                        "text_response": "Prepared escalation for TKT-501. Policy conflict requires review."
                    }
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "lookup_operational_data", "arguments": {"query_type": "ticket", "entity_id": "TKT-501"}}
                    ]
                }
            else:
                return {
                    "text_response": "Ticket TKT-501 is currently open and assigned to Rohit. Subject: 'All shipment creation is failing'."
                }

        # 5. Historical ticket conflict (TKT-450)
        elif "tkt-450" in user_prompt_lower or "historical resolution conflict" in user_prompt_lower:
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "lookup_operational_data", "arguments": {"query_type": "ticket", "entity_id": "TKT-450"}},
                        {"name": "search_documents", "arguments": {"query": "cancellation policy"}}
                    ]
                }
            else:
                return {
                    "text_response": "Historical ticket guidance for ACCT-001 (Northstar) suggested a cancellation fee applied, but the active Customer Agreement overrides this and waives all booked cancellation fees before pickup. Current policy/agreement takes precedence."
                }
                
        # 6. Deprecated Policy conflict
        elif "conflict between policies" in user_prompt_lower or "deprecated policy conflict" in user_prompt_lower:
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "search_documents", "arguments": {"query": "Support Policy v3"}},
                        {"name": "search_documents", "arguments": {"query": "Support Policy v2"}}
                    ]
                }
            else:
                return {
                    "text_response": "Current version Support Policy v3 overrides deprecated Support Policy v2."
                }
                
        # 7. SLA check
        elif "sla" in user_prompt_lower or "breach" in user_prompt_lower or "created at 2026-08-16" in user_prompt_lower:
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "calculate_sla", "arguments": {"created_at": "2026-08-16 10:30", "severity": "P1", "plan": "Enterprise", "account_id": "ACCT-001"}}
                    ]
                }
            else:
                return {
                    "text_response": "SLA status is BREACHED. Target response time for Northstar Logistics P1 is 15 minutes, but 30 minutes has elapsed since ticket creation."
                }
                
        # 8. Cross-account lookup of ORD-2001
        elif "ord-2001" in user_prompt_lower:
            if "executed" not in user_prompt_lower:
                return {
                    "tool_calls": [
                        {"name": "lookup_operational_data", "arguments": {"query_type": "order", "entity_id": "ORD-2001"}}
                    ]
                }
            else:
                return {
                    "text_response": "Access Denied: You do not have permissions to access this order."
                }
                
        # Default fallback / general QA
        return {
            "text_response": "This is a mock LLM response. The query has been processed without contacting the Gemini API."
        }

def get_gemini_schema(pydantic_model: Any) -> dict:
    """
    Generates a Gemini-compatible JSON schema dictionary from a Pydantic model.
    Inlines all '$ref' definitions and removes 'additionalProperties' keys.
    """
    raw_schema = pydantic_model.model_json_schema()
    defs = raw_schema.get("$defs", {})
    
    def resolve_and_clean(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                ref_key = ref_path.split("/")[-1]
                if ref_key in defs:
                    return resolve_and_clean(defs[ref_key])
            cleaned = {}
            for k, v in node.items():
                if k == "additionalProperties":
                    continue
                cleaned[k] = resolve_and_clean(v)
            return cleaned
        elif isinstance(node, list):
            return [resolve_and_clean(item) for item in node]
        return node

    cleaned_schema = resolve_and_clean(raw_schema)
    if "$defs" in cleaned_schema:
        del cleaned_schema["$defs"]
    return cleaned_schema

class GeminiLLMProvider(LLMProvider):

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment.")
        from google import genai
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = LLM_MODEL or "gemini-1.5-flash"
        self._cache = {}

    def generate(self, system_prompt: str, user_prompt: str, schema: Optional[BaseModel] = None) -> Dict[str, Any]:
        """
        Executes structured or text generation using the Gemini API, enforcing cache and session request limits.
        """
        # Session request rate limiting (Max 20 requests per session)
        count = current_session_request_count.get() + 1
        if count > 20:
            raise ValueError("LLM execution limit exceeded (Max 20 requests per session).")
        current_session_request_count.set(count)

        # In-memory caching
        cache_enabled = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
        schema_name = schema.__name__ if schema else None
        cache_key = (self.model_name, system_prompt, user_prompt, schema_name)

        if cache_enabled and cache_key in self._cache:
            print("Token Usage Observability: CACHE HIT (No tokens used)")
            return self._cache[cache_key]

        # pyrefly: ignore [missing-import]
        from google.genai import types

        prompt_content = user_prompt
        
        generation_schema = None
        if schema:
            generation_schema = get_gemini_schema(schema)

        generation_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json" if schema else "text/plain",
            response_schema=generation_schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )

        max_retries = 2
        backoff = 1.0
        response = None
        latency = 0.0
        
        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt_content,
                    config=generation_config
                )
                latency = time.time() - start_time
                break
            except Exception as e:
                import traceback
                print("ACTUAL GEMINI EXCEPTION CAUGHT:")
                traceback.print_exc()
                err_str = str(e)
                
                # Check for 404 Model Not Found
                if "404" in err_str or "not_found" in err_str.lower() or "model not found" in err_str.lower():
                    raise ValueError(f"Gemini configuration error: The requested model '{self.model_name}' was not found. Details: {e}")
                
                # Check for 401/403 Authentication/Permissions
                if "401" in err_str or "403" in err_str or "auth" in err_str.lower() or "key" in err_str.lower() or "permission" in err_str.lower() or "unauthorized" in err_str.lower():
                    raise ValueError(f"Gemini authentication error: Invalid API key or permission denied. Details: {e}")

                # Check for 429 Quota Exhausted
                if "429" in err_str or "quota" in err_str.lower() or "exhausted" in err_str.lower() or "limit" in err_str.lower():
                    print("DIAGNOSTIC - Quota Exhausted (429). Terminating immediately.")
                    raise ValueError(f"Gemini API quota is exhausted or unavailable for the configured project/model. Details: {e}")
                
                is_unavailable = "503" in err_str or "unavailable" in err_str.lower() or "overloaded" in err_str.lower() or "high demand" in err_str.lower()
                
                if is_unavailable and attempt < max_retries:
                    print(f"DIAGNOSTIC - 503 Service Unavailable on attempt {attempt + 1}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                
                raise ValueError(f"Gemini is temporarily unavailable. Details: {e}")

        # Token usage observability
        tokens_info = {}
        usage = response.usage_metadata if response else None
        if usage:
            tokens_info = {
                "input_tokens": usage.prompt_token_count,
                "output_tokens": usage.candidates_token_count,
                "total_tokens": usage.total_token_count
            }
        
        print({
            "event": "gemini_call",
            "model": self.model_name,
            "latency_sec": round(latency, 4),
            "usage": tokens_info,
            "cache_hit": False
        })

        if os.getenv("LLM_DEBUG_LOGGING", "false").lower() == "true":
            print("\n=== RAW GEMINI RESPONSE DEBUG ===")
            print(f"Model: {self.model_name}")
            print(f"Response schema supplied: {generation_schema is not None}")
            print(f"Response type: {type(response)}")
            if response:
                try:
                    print(f"Response.text: {response.text}")
                except Exception as tex:
                    print(f"Response.text failed: {tex}")
                try:
                    print(f"Response.parsed: {getattr(response, 'parsed', 'N/A')}")
                except Exception as parx:
                    print(f"Response.parsed failed: {parx}")
                try:
                    print(f"Response.candidates: {response.candidates}")
                except Exception as candx:
                    print(f"Response.candidates failed: {candx}")
            print("==================================\n")

        if schema:
            try:
                result = json.loads(response.text) if response else {}
                # Ensure should_continue is set correctly
                if "should_continue" not in result:
                    result["should_continue"] = len(result.get("tool_calls", [])) > 0
                if "response" not in result:
                    result["response"] = result.get("text_response")
            except Exception as e:
                result = {"tool_calls": [], "response": f"Error parsing response: {e}", "should_continue": False}
        else:
            result = {"response": response.text if response else "", "tool_calls": [], "should_continue": False}

        if cache_enabled:
            self._cache[cache_key] = result

        return result

def get_llm_provider() -> LLMProvider:
    mode = os.getenv("LLM_MODE", "mock").lower()
    if mode == "gemini" and GEMINI_API_KEY:
        return GeminiLLMProvider()
    return MockLLMProvider()
