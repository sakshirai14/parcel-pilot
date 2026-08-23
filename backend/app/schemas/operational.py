from typing import Optional, List
from pydantic import BaseModel

class AccountData(BaseModel):
    account_id: str
    account_name: str
    plan: str
    status: str
    csm: Optional[str] = None
    contract_file: Optional[str] = None
    premium_support: Optional[int] = 0
    notes: Optional[str] = None

class OrderData(BaseModel):
    order_id: str
    account_id: str
    carrier: str
    status: str
    booked_at: str
    pickup_window_start: str
    pickup_window_end: str
    pickup_actual_at: Optional[str] = None
    shipment_fee_inr: float
    carrier_fault: Optional[int] = 0
    customer_fault: Optional[int] = 0
    cancellation_requested_at: Optional[str] = None
    notes: Optional[str] = None

class TicketData(BaseModel):
    ticket_id: str
    account_id: str
    created_at: str
    status: str
    subject: str
    description: Optional[str] = None
    channel: str
    assigned_to: Optional[str] = None
    last_customer_message_at: Optional[str] = None
    historical_resolution: Optional[str] = None
