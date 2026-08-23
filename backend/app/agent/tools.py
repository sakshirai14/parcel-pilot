from typing import Optional, Dict, Any, List
from backend.app.security.auth import UserContext
from backend.app.retrieval.retriever import DocumentRetriever
from backend.app.retrieval.authority import AuthorityEngine
from backend.app.services.source_resolution import SourceResolver
from backend.app.tools.data_lookup import DataLookupTool
from backend.app.services.sla import SLAService
from backend.app.tools.entitlement import EntitlementTool

# Instantiate singletons/instances
retriever_inst = DocumentRetriever()

class AgentTools:
    @staticmethod
    def search_documents(query: str, customer_account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search through all policies and customer agreements using semantic vector store.
        """
        res = retriever_inst.search(query=query, customer_account_id=customer_account_id)
        return [r.model_dump() for r in res]

    @staticmethod
    def lookup_operational_data(
        query_type: str, 
        entity_id: str, 
        user_context: UserContext
    ) -> Dict[str, Any]:
        """
        Retrieves database objects (account, order, ticket) from SQLite.
        """
        query_type = query_type.lower()
        if query_type == "account":
            res = DataLookupTool.lookup_account(user_context, entity_id)
        elif query_type == "order":
            res = DataLookupTool.lookup_order(user_context, entity_id)
        elif query_type == "ticket":
            res = DataLookupTool.lookup_ticket(user_context, entity_id)
        else:
            return {"status": "ERROR", "message": f"Unsupported query type: {query_type}"}
            
        if res.status != "SUCCESS":
            return {"status": res.status, "message": res.message}
            
        return {
            "status": "SUCCESS", 
            "data": res.data.model_dump() if res.data else None
        }

    @staticmethod
    def calculate_entitlement(
        entitlement_type: str, 
        order_id: str, 
        user_context: UserContext
    ) -> Dict[str, Any]:
        """
        Deterministic calculation of refund/cancellation fees or service credits.
        """
        entitlement_type = entitlement_type.lower()
        if entitlement_type == "cancellation":
            res = EntitlementTool.check_cancellation_entitlement(user_context, order_id)
        elif entitlement_type in ("service_credit", "credit"):
            res = EntitlementTool.check_service_credit_entitlement(user_context, order_id)
        else:
            return {"status": "ERROR", "message": f"Unsupported entitlement calculation: {entitlement_type}"}
            
        return res.model_dump()

    @staticmethod
    def calculate_sla(
        created_at: str, 
        severity: str, 
        plan: str, 
        account_id: str
    ) -> Dict[str, Any]:
        """
        Calculate ticket response targets and identify SLA breaches.
        """
        res = SLAService.calculate_sla(created_at, severity, plan, account_id)
        return res.model_dump()

    @staticmethod
    def prepare_action(
        action_type: str, 
        entity_id: str, 
        details: str, 
        user_context: Optional[UserContext] = None
    ) -> Dict[str, Any]:
        """
        Prepares a state-changing action such as escalations. Requires user approval later.
        """
        from datetime import datetime, timedelta
        import os
        import json
        import uuid
        from backend.app.schemas.actions import ActionProposal, ActionStatus, ActionType
        from backend.app.data.action_db import save_action_proposal
        from backend.app.services.time_service import TimeService
        from backend.app.tools.data_lookup import DataLookupTool
        from backend.app.security.auth import UserRole

        # Normalize action_type
        a_type_str = action_type.upper()
        if "ESCALAT" in a_type_str:
            action_type_enum = ActionType.CREATE_ESCALATION
        elif "UPDATE" in a_type_str:
            action_type_enum = ActionType.UPDATE_TICKET
        elif "FOLLOWUP" in a_type_str or "FOLLOW_UP" in a_type_str:
            action_type_enum = ActionType.CREATE_FOLLOWUP
        elif "CANCEL" in a_type_str:
            action_type_enum = ActionType.CANCEL_ORDER
        else:
            return {
                "status": "ERROR",
                "message": f"Unsupported action type: {action_type}"
            }

        # If user context is not passed, use a default fallback
        if not user_context:
            user_context = UserContext(role=UserRole.SUPPORT_AGENT)

        # Enforce limits during prepare
        if user_context.role == UserRole.CUSTOMER and action_type_enum in (ActionType.UPDATE_TICKET, ActionType.CREATE_FOLLOWUP, ActionType.CANCEL_ORDER):
            return {"status": "UNAUTHORIZED", "message": "ACCESS_DENIED: Customers cannot perform internal operational modifications."}
        if user_context.role == UserRole.SUPPORT_AGENT and action_type_enum == ActionType.CANCEL_ORDER:
            return {"status": "UNAUTHORIZED", "message": "ACCESS_DENIED: Support agents are not authorized to prepare order cancellations."}

        # Look up entity to fetch account_id/order_id context if possible
        account_id = None
        order_id = None
        ticket_id = None

        if action_type_enum in (ActionType.CREATE_ESCALATION, ActionType.UPDATE_TICKET, ActionType.CREATE_FOLLOWUP):
            ticket_id = entity_id
            t_res = DataLookupTool.lookup_ticket(user_context, entity_id)
            if t_res.status == "SUCCESS" and t_res.data:
                account_id = t_res.data.account_id
                order_id = None
            elif t_res.status == "UNAUTHORIZED":
                return {"status": "UNAUTHORIZED", "message": t_res.message}
            else:
                return {"status": "NOT_FOUND", "message": f"Ticket {entity_id} not found."}
        elif action_type_enum == ActionType.CANCEL_ORDER:
            order_id = entity_id
            o_res = DataLookupTool.lookup_order(user_context, entity_id)
            if o_res.status == "SUCCESS" and o_res.data:
                account_id = o_res.data.account_id
            elif o_res.status == "UNAUTHORIZED":
                return {"status": "UNAUTHORIZED", "message": o_res.message}
            else:
                return {"status": "NOT_FOUND", "message": f"Order {entity_id} not found."}

        # Generate a unique action ID
        uid = str(uuid.uuid4())[:8].upper()
        action_id = f"ACT-{uid}"

        now = datetime.now(TimeService.TIMEZONE)
        created_at_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        ttl_mins = int(os.getenv("ACTION_CONFIRMATION_TTL_MINUTES", "15"))
        expires_at_str = (now + timedelta(minutes=ttl_mins)).strftime("%Y-%m-%d %H:%M:%S")

        # Build proposed changes
        proposed_changes = {}
        if action_type_enum == ActionType.CREATE_ESCALATION:
            proposed_changes = {
                "ticket_id": ticket_id,
                "reason": details,
                "priority": "P1"
            }
        elif action_type_enum == ActionType.UPDATE_TICKET:
            try:
                proposed_changes = json.loads(details)
            except Exception:
                proposed_changes = {
                    "ticket_id": ticket_id,
                    "historical_resolution": details,
                    "status": "CLOSED"
                }
        elif action_type_enum == ActionType.CREATE_FOLLOWUP:
            proposed_changes = {
                "ticket_id": ticket_id,
                "title": f"Follow-up for {ticket_id}",
                "description": details,
                "assigned_to": "Tier-2 Support",
                "due_at": (now + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
            }
        elif action_type_enum == ActionType.CANCEL_ORDER:
            proposed_changes = {
                "order_id": order_id,
                "status": "CANCELLED",
                "details": details
            }

        # Build proposal
        proposal = ActionProposal(
            action_id=action_id,
            action_type=action_type_enum,
            account_id=account_id,
            ticket_id=ticket_id,
            order_id=order_id,
            summary=f"Prepare {action_type_enum.value} for {entity_id}",
            reason=details,
            proposed_changes=proposed_changes,
            created_by=user_context.user_id or user_context.customer_account_id or "system-agent",
            created_at=created_at_str,
            status=ActionStatus.PENDING_CONFIRMATION,
            expires_at=expires_at_str
        )

        save_action_proposal(proposal)

        return {
            "status": "PENDING_CONFIRMATION",
            "action_id": action_id,
            "action_type": action_type_enum.value,
            "entity_id": entity_id,
            "details": details,
            "requires_confirmation": True,
            "message": f"Prepared action {action_type_enum.value} for {entity_id}. Please confirm."
        }

    @staticmethod
    def execute_action(action_id: str, user_context: Optional[UserContext] = None) -> Dict[str, Any]:
        """
        Executes a prepared action.
        """
        from backend.app.tools.execute_action import execute_action as real_execute
        from backend.app.security.auth import UserRole
        if not user_context:
            user_context = UserContext(role=UserRole.SUPPORT_AGENT)
        try:
            return real_execute(user_context, action_id)
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
