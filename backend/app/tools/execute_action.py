import json
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional
from backend.app.config import DATABASE_PATH
from backend.app.schemas.actions import ActionProposal, ActionStatus, ActionType, AuditLogEntry
from backend.app.security.auth import UserContext, UserRole
from backend.app.security.permissions import enforce_ticket_access, enforce_account_access
from backend.app.services.time_service import TimeService
from backend.app.data.action_db import (
    get_action_proposal,
    update_action_proposal_status,
    save_audit_log,
    get_connection
)

class ActionExecutionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

def execute_action(
    user_context: UserContext, 
    action_id: str, 
    client_payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Executes a prepared ActionProposal after re-authorization and validations.
    """
    timestamp_str = datetime.now(TimeService.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Retrieve Action Proposal
    proposal = get_action_proposal(action_id)
    if not proposal:
        raise ActionExecutionError("ACTION_NOT_FOUND", f"Action {action_id} not found.")

    previous_state: Optional[str] = None
    proposed_state = json.dumps(proposal.proposed_changes)

    # Helper function to write audit log on failure
    def log_failure(code: str, msg: str, auth_res: str = "FAILED"):
        audit_entry = AuditLogEntry(
            action_id=action_id,
            user_id=user_context.customer_account_id or "system-agent",
            role=user_context.role.value,
            account_id=proposal.account_id,
            ticket_id=proposal.ticket_id,
            order_id=proposal.order_id,
            action_type=proposal.action_type,
            previous_state=previous_state,
            proposed_state=proposed_state,
            final_state=proposal.status.value,
            timestamp=timestamp_str,
            result=f"ERROR: {code} - {msg}",
            authorization_result=auth_res
        )
        save_audit_log(audit_entry)
        return {"status": code, "message": msg}

    # 2. Check Idempotency (Already Executed)
    if proposal.status == ActionStatus.EXECUTED:
        return {"status": "ALREADY_EXECUTED", "message": f"Action {action_id} was already executed."}

    # 3. Expiration Check
    try:
        expires_at_dt = TimeService.parse_timestamp(proposal.expires_at)
        now_dt = datetime.now(TimeService.TIMEZONE)
        if now_dt > expires_at_dt:
            update_action_proposal_status(action_id, ActionStatus.EXPIRED)
            return log_failure("ACTION_EXPIRED", "The action confirmation window has expired.", "PASSED")
    except Exception as e:
        return log_failure("INVALID_EXPIRATION_DATE", f"Error parsing expiration date: {e}", "PASSED")

    # 4. Check status is valid for execution
    if proposal.status not in (ActionStatus.PREPARED, ActionStatus.PENDING_CONFIRMATION, ActionStatus.CONFIRMED):
        return log_failure("INVALID_STATUS", f"Action status is {proposal.status.value}, cannot execute.", "PASSED")

    # 5. Payload modification check (Security check for tampered parameters)
    if client_payload is not None:
        # Compare client payload with database stored proposed changes
        # Strip/ignore status or ID fields to only compare actual payload fields
        client_clean = {k: v for k, v in client_payload.items() if k not in ("action_id", "status")}
        stored_clean = {k: v for k, v in proposal.proposed_changes.items() if k not in ("action_id", "status")}
        
        if client_clean != stored_clean:
            update_action_proposal_status(action_id, ActionStatus.FAILED)
            return log_failure("ACTION_INVALIDATED", "Proposed changes mismatch or payload tampered.", "PASSED")

    # 6. Re-Authorization Check (RBAC & ownership check)
    try:
        # Enforce role permissions
        if user_context.role == UserRole.CUSTOMER:
            # Customers cannot perform internal operational actions
            if proposal.action_type in (ActionType.UPDATE_TICKET, ActionType.CREATE_FOLLOWUP, ActionType.CANCEL_ORDER):
                raise PermissionError("ACCESS_DENIED: Customers cannot modify operational tickets, follow-ups, or orders.")
            
            # For escalations, customers can only escalate their own tickets
            if proposal.action_type == ActionType.CREATE_ESCALATION:
                if proposal.account_id != user_context.customer_account_id:
                    raise PermissionError("ACCESS_DENIED: Customers can only escalate tickets for their own account.")
                # Also enforce ticket level access
                if proposal.ticket_id:
                    enforce_ticket_access(user_context, proposal.account_id)
        
        elif user_context.role == UserRole.SUPPORT_AGENT:
            # Support agents can perform these actions, but let's check general ticket ownership if scoped
            if proposal.action_type == ActionType.CANCEL_ORDER:
                raise PermissionError("ACCESS_DENIED: Support agents are not authorized to execute order cancellations.")
            if proposal.account_id:
                enforce_account_access(user_context, proposal.account_id)
        
        elif user_context.role == UserRole.OPERATIONS_ADMIN:
            # Operations admin has broad access
            pass
            
    except Exception as e:
        return log_failure("ACCESS_DENIED", str(e), "FAILED")

    # 7. Execute Mutations in SQLite
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        if proposal.action_type == ActionType.CREATE_ESCALATION:
            # Insert into escalations table
            esc_id = f"ESC-{proposal.action_id.split('-')[-1]}"
            ticket_id = proposal.proposed_changes.get("ticket_id") or proposal.ticket_id
            reason = proposal.proposed_changes.get("reason") or proposal.reason
            priority = proposal.proposed_changes.get("priority") or "P1"
            
            # Fetch ticket to verify existence and get previous state
            cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
            t_row = cursor.fetchone()
            if not t_row:
                conn.close()
                return log_failure("TICKET_NOT_FOUND", f"Ticket {ticket_id} does not exist.", "PASSED")
            
            previous_state = json.dumps(dict(t_row))
            
            cursor.execute("""
            INSERT INTO escalations (escalation_id, ticket_id, reason, priority, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                esc_id,
                ticket_id,
                reason,
                priority,
                "OPEN",
                user_context.customer_account_id or "system-agent",
                timestamp_str
            ))
            
            # Update ticket assignee/notes or status in source tickets table if desired, or keep as is.
            # Usually escalations update ticket status to "ESCALATED" or assigned to Tier-2
            cursor.execute("UPDATE tickets SET status = 'ESCALATED' WHERE ticket_id = ?", (ticket_id,))
            
        elif proposal.action_type == ActionType.UPDATE_TICKET:
            ticket_id = proposal.proposed_changes.get("ticket_id") or proposal.ticket_id
            
            # Fetch current ticket state
            cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
            t_row = cursor.fetchone()
            if not t_row:
                conn.close()
                return log_failure("TICKET_NOT_FOUND", f"Ticket {ticket_id} does not exist.", "PASSED")
            
            previous_state = json.dumps(dict(t_row))
            
            # Dynamic update query
            updates = []
            params = []
            for col, val in proposal.proposed_changes.items():
                if col in ("ticket_id", "account_id", "created_at"):
                    continue # Do not allow modifying primary keys / creation time
                updates.append(f"{col} = ?")
                params.append(val)
                
            if updates:
                params.append(ticket_id)
                query = f"UPDATE tickets SET {', '.join(updates)} WHERE ticket_id = ?"
                cursor.execute(query, params)
                
        elif proposal.action_type == ActionType.CREATE_FOLLOWUP:
            task_id = f"TSK-{proposal.action_id.split('-')[-1]}"
            ticket_id = proposal.proposed_changes.get("ticket_id") or proposal.ticket_id
            title = proposal.proposed_changes.get("title", "Follow-up Task")
            desc = proposal.proposed_changes.get("description", "")
            assigned = proposal.proposed_changes.get("assigned_to")
            due = proposal.proposed_changes.get("due_at")
            
            # Check ticket existence
            cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
            t_row = cursor.fetchone()
            if not t_row:
                conn.close()
                return log_failure("TICKET_NOT_FOUND", f"Ticket {ticket_id} does not exist.", "PASSED")
            
            previous_state = json.dumps(dict(t_row))
            
            cursor.execute("""
            INSERT INTO follow_up_tasks (task_id, ticket_id, title, description, status, assigned_to, due_at, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                ticket_id,
                title,
                desc,
                "PENDING",
                assigned,
                due,
                user_context.customer_account_id or "system-agent",
                timestamp_str
            ))
            
        elif proposal.action_type == ActionType.CANCEL_ORDER:
            order_id = proposal.proposed_changes.get("order_id") or proposal.order_id
            
            # Fetch current order state
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            o_row = cursor.fetchone()
            if not o_row:
                conn.close()
                return log_failure("INVALID_STATUS", f"Order {order_id} does not exist.", "PASSED")
            
            order_dict = dict(o_row)
            previous_state = json.dumps(order_dict)
            
            # Re-validate order eligibility: status must be BOOKED
            current_status = order_dict.get("status", "").upper()
            if current_status != "BOOKED":
                conn.close()
                return log_failure("INVALID_STATUS", f"Order status is {current_status}, must be BOOKED to cancel.", "PASSED")
            
            # Perform mutation
            cursor.execute(
                "UPDATE orders SET status = 'CANCELLED', cancellation_requested_at = ? WHERE order_id = ?",
                (timestamp_str, order_id)
            )
            
        else:
            conn.close()
            return log_failure("UNKNOWN_ACTION_TYPE", f"Action type {proposal.action_type} is not supported.", "PASSED")
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        return log_failure("MUTATION_FAILED", f"Database mutation failed: {e}", "PASSED")
    finally:
        conn.close()

    # 8. Mark proposal as EXECUTED
    update_action_proposal_status(action_id, ActionStatus.EXECUTED)
    proposal.status = ActionStatus.EXECUTED

    # 9. Log successful execution in audit_logs
    audit_entry = AuditLogEntry(
        action_id=action_id,
        user_id=user_context.customer_account_id or "system-agent",
        role=user_context.role.value,
        account_id=proposal.account_id,
        ticket_id=proposal.ticket_id,
        order_id=proposal.order_id,
        action_type=proposal.action_type,
        previous_state=previous_state,
        proposed_state=proposed_state,
        final_state=ActionStatus.EXECUTED.value,
        timestamp=timestamp_str,
        result="SUCCESS",
        authorization_result="PASSED"
    )
    save_audit_log(audit_entry)

    return {"status": "EXECUTED", "action_id": action_id, "message": "Action executed successfully."}
