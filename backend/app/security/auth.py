from enum import Enum
from typing import Optional
from pydantic import BaseModel

class UserRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    SUPPORT_AGENT = "SUPPORT_AGENT"
    OPERATIONS_ADMIN = "OPERATIONS_ADMIN"

class UserContext(BaseModel):
    role: UserRole
    # If role is CUSTOMER, customer_account_id MUST be set.
    customer_account_id: Optional[str] = None
    user_id: Optional[str] = None
