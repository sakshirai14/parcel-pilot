from backend.app.security.auth import UserContext
from backend.app.tools.data_lookup import DataLookupTool
from backend.app.services.entitlement import EntitlementService, EntitlementResult

class EntitlementTool:
    @classmethod
    def check_cancellation_entitlement(
        cls, 
        user_context: UserContext, 
        order_id: str
    ) -> EntitlementResult:
        """
        Check cancellation eligibility and fees for a given order.
        """
        # Lookup order
        order_res = DataLookupTool.lookup_order(user_context, order_id)
        if order_res.status == "UNAUTHORIZED":
            return EntitlementResult(
                status="UNAUTHORIZED",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="User is unauthorized to view this order."
            )
        if order_res.status == "NOT_FOUND" or not order_res.data:
            return EntitlementResult(
                status="INSUFFICIENT_INFORMATION",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason=f"Order {order_id} could not be found."
            )
            
        order_data = order_res.data
        
        # Lookup account
        account_res = DataLookupTool.lookup_account(user_context, order_data.account_id)
        if account_res.status != "SUCCESS" or not account_res.data:
            return EntitlementResult(
                status="INSUFFICIENT_INFORMATION",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason=f"Account {order_data.account_id} for order {order_id} could not be found."
            )
            
        account_data = account_res.data
        
        # Convert Pydantic to Dict
        return EntitlementService.evaluate_cancellation(
            order=order_data.model_dump(), 
            account=account_data.model_dump()
        )

    @classmethod
    def check_service_credit_entitlement(
        cls, 
        user_context: UserContext, 
        order_id: str
    ) -> EntitlementResult:
        """
        Check service-credit eligibility and amount for a given order.
        """
        # Lookup order
        order_res = DataLookupTool.lookup_order(user_context, order_id)
        if order_res.status == "UNAUTHORIZED":
            return EntitlementResult(
                status="UNAUTHORIZED",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason="User is unauthorized to view this order."
            )
        if order_res.status == "NOT_FOUND" or not order_res.data:
            return EntitlementResult(
                status="INSUFFICIENT_INFORMATION",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason=f"Order {order_id} could not be found."
            )
            
        order_data = order_res.data
        
        # Lookup account
        account_res = DataLookupTool.lookup_account(user_context, order_data.account_id)
        if account_res.status != "SUCCESS" or not account_res.data:
            return EntitlementResult(
                status="INSUFFICIENT_INFORMATION",
                eligible=False,
                governing_source="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                reason=f"Account {order_data.account_id} for order {order_id} could not be found."
            )
            
        account_data = account_res.data
        
        return EntitlementService.evaluate_service_credit(
            order=order_data.model_dump(), 
            account=account_data.model_dump()
        )
