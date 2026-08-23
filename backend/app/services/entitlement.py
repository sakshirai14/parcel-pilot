from typing import Dict, Any, Optional
from pydantic import BaseModel
from backend.app.services.time_service import TimeService

class EntitlementResult(BaseModel):
    status: str  # "CONFIDENT", "CONDITIONAL", "INSUFFICIENT_INFORMATION", "CONFLICT_REQUIRES_REVIEW"
    eligible: bool
    fee: Optional[float] = 0.0
    credit_amount: Optional[float] = 0.0
    currency: str = "INR"
    governing_source: str
    source_page: int = 1
    reason: str

class EntitlementService:
    @classmethod
    def evaluate_cancellation(
        cls, 
        order: Dict[str, Any], 
        account: Dict[str, Any]
    ) -> EntitlementResult:
        """
        Evaluate cancellation eligibility and fee.
        """
        order_id = order.get("order_id")
        account_id = account.get("account_id")
        status = order.get("status", "").upper()
        booked_at_str = order.get("booked_at")
        cancellation_requested_at_str = order.get("cancellation_requested_at")
        
        if not cancellation_requested_at_str:
            # Fallback to snapshot time if not explicitly requested yet
            cancellation_requested_at_str = TimeService.get_snapshot_time().strftime("%Y-%m-%d %H:%M:%S")

        # Basic status check
        if status == "CANCELLED":
            return EntitlementResult(
                status="CONFIDENT",
                eligible=False,
                fee=0.0,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="This order has already been cancelled."
            )
            
        if status == "DELIVERED":
            return EntitlementResult(
                status="CONFIDENT",
                eligible=False,
                fee=0.0,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="Delivered shipments cannot be cancelled."
            )
            
        if status == "PICKED_UP":
            return EntitlementResult(
                status="CONFIDENT",
                eligible=False,
                fee=0.0,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="Shipment has been picked up. Do not cancel; use the return-to-origin workflow."
            )
            
        if status == "DRAFT":
            return EntitlementResult(
                status="CONFIDENT",
                eligible=True,
                fee=0.0,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="Draft orders can be cancelled with no fee."
            )

        # Status is BOOKED
        if status == "BOOKED":
            # Northstar Logistics Custom Override
            if account_id == "ACCT-001":
                return EntitlementResult(
                    status="CONFIDENT",
                    eligible=True,
                    fee=0.0,
                    governing_source="05_Northstar_Logistics_Enterprise_Agreement.pdf",
                    reason="Northstar Logistics agreement allows cancellation of any booked shipment before pickup with no fee."
                )

            # Default SOP / LumenWorks (uses default SOP)
            if not booked_at_str:
                return EntitlementResult(
                    status="INSUFFICIENT_INFORMATION",
                    eligible=True,
                    fee=None,
                    governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                    reason="Booking time is missing. Cannot determine if cancellation fee applies."
                )
                
            try:
                # Calculate duration in minutes since booking
                minutes_since_booking = TimeService.hours_between(booked_at_str, cancellation_requested_at_str) * 60.0
            except Exception as e:
                return EntitlementResult(
                    status="ERROR",
                    eligible=True,
                    fee=None,
                    governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                    reason=f"Error parsing booking time: {e}"
                )
                
            if minutes_since_booking <= 30.0:
                return EntitlementResult(
                    status="CONFIDENT",
                    eligible=True,
                    fee=0.0,
                    governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                    reason="Cancellation requested within 30 minutes of booking. No fee applies."
                )
            else:
                source = "03_Cancellation_and_Service_Credit_SOP_v4.pdf"
                if account_id == "ACCT-002":
                    source = "06_LumenWorks_Service_Agreement.pdf"  # agreement references default SOP
                return EntitlementResult(
                    status="CONFIDENT",
                    eligible=True,
                    fee=250.0,
                    governing_source=source,
                    reason="Cancellation requested more than 30 minutes after booking. Standard INR 250 fee applies."
                )

        return EntitlementResult(
            status="INSUFFICIENT_INFORMATION",
            eligible=False,
            fee=0.0,
            governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
            reason=f"Unknown order status: {status}."
        )

    @classmethod
    def evaluate_service_credit(
        cls, 
        order: Dict[str, Any], 
        account: Dict[str, Any]
    ) -> EntitlementResult:
        """
        Evaluate service-credit eligibility and amount.
        """
        account_id = account.get("account_id")
        order_status = order.get("status", "").upper()
        pickup_window_end = order.get("pickup_window_end")
        pickup_actual_at = order.get("pickup_actual_at")
        carrier_fault = order.get("carrier_fault")
        customer_fault = order.get("customer_fault")
        shipment_fee = order.get("shipment_fee_inr", 0.0)

        # Standard validations
        if carrier_fault is None or customer_fault is None:
            return EntitlementResult(
                status="INSUFFICIENT_INFORMATION",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="Carrier or customer fault status is unknown. Cannot determine eligibility."
            )

        if customer_fault == 1:
            return EntitlementResult(
                status="CONFIDENT",
                eligible=False,
                credit_amount=0.0,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="Customer fault is identified. Service credit is not eligible."
            )

        if carrier_fault == 0:
            return EntitlementResult(
                status="CONFIDENT",
                eligible=False,
                credit_amount=0.0,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="Carrier was not at fault. Service credit is not eligible."
            )

        # Carrier is at fault and customer is not. Check pickup delay thresholds.
        if not pickup_window_end:
            return EntitlementResult(
                status="INSUFFICIENT_INFORMATION",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="Scheduled pickup window is missing. Cannot calculate delay."
            )

        # Calculate actual delay in hours
        try:
            delay_hours = TimeService.pickup_delay_hours(pickup_window_end, pickup_actual_at)
        except Exception as e:
            return EntitlementResult(
                status="INSUFFICIENT_INFORMATION",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason=f"Error parsing pickup window: {e}"
            )

        # Check thresholds
        if account_id == "ACCT-002":  # LumenWorks custom contract
            threshold = 4.0
            if delay_hours > threshold:
                return EntitlementResult(
                    status="CONFIDENT",
                    eligible=True,
                    credit_amount=300.0,
                    governing_source="06_LumenWorks_Service_Agreement.pdf",
                    reason="LumenWorks agreement: Pickup delay is more than 4 hours (carrier fault). Fixed INR 300 credit is eligible."
                )
            else:
                return EntitlementResult(
                    status="CONFIDENT",
                    eligible=False,
                    credit_amount=0.0,
                    governing_source="06_LumenWorks_Service_Agreement.pdf",
                    reason=f"Pickup delay ({delay_hours:.2f} hours) did not exceed the 4-hour threshold."
                )
        else:  # Default SOP / Northstar (uses default SOP)
            threshold = 2.0
            if delay_hours > threshold:
                default_credit = min(500.0, 0.10 * shipment_fee)
                
                # Check for Northstar cap
                source = "03_Cancellation_and_Service_Credit_SOP_v4.pdf"
                if account_id == "ACCT-001":
                    source = "05_Northstar_Logistics_Enterprise_Agreement.pdf"
                    reason = f"Northstar Agreement: Delay is {delay_hours:.2f} hours. Eligible for credit of {default_credit} INR (capped at 5,000 INR aggregate)."
                else:
                    reason = f"SOP: Delay is {delay_hours:.2f} hours. Eligible for credit of {default_credit} INR (min of 500 INR or 10% of fee)."
                
                return EntitlementResult(
                    status="CONFIDENT",
                    eligible=True,
                    credit_amount=default_credit,
                    governing_source=source,
                    reason=reason
                )
            else:
                return EntitlementResult(
                    status="CONFIDENT",
                    eligible=False,
                    credit_amount=0.0,
                    governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                    reason=f"Pickup delay ({delay_hours:.2f} hours) did not exceed the 2-hour default threshold."
                )
