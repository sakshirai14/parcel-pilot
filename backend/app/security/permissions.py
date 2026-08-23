from backend.app.security.auth import UserContext, UserRole

class AccessDeniedException(PermissionError):
    pass

def enforce_account_access(user_context: UserContext, target_account_id: str):
    """
    Enforces that the user has access to the target account.
    """
    if user_context.role == UserRole.CUSTOMER:
        if not user_context.customer_account_id or user_context.customer_account_id != target_account_id:
            raise AccessDeniedException("ACCESS_DENIED: Customers can only access their own account data.")
    # SUPPORT_AGENT and OPERATIONS_ADMIN have access to all accounts.

def enforce_order_access(user_context: UserContext, order_account_id: str):
    """
    Enforces that the user has access to the order.
    """
    if user_context.role == UserRole.CUSTOMER:
        if not user_context.customer_account_id or user_context.customer_account_id != order_account_id:
            raise AccessDeniedException("ACCESS_DENIED: Customers can only access orders belonging to their account.")

def enforce_ticket_access(user_context: UserContext, ticket_account_id: str):
    """
    Enforces that the user has access to the ticket.
    """
    if user_context.role == UserRole.CUSTOMER:
        if not user_context.customer_account_id or user_context.customer_account_id != ticket_account_id:
            raise AccessDeniedException("ACCESS_DENIED: Customers can only access tickets belonging to their account.")
