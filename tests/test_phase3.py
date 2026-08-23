import unittest
from backend.app.security.auth import UserContext, UserRole
from backend.app.retrieval.retriever import DocumentRetriever
from backend.app.retrieval.authority import AuthorityEngine
from backend.app.services.source_resolution import SourceResolver
from backend.app.tools.data_lookup import DataLookupTool
from backend.app.services.time_service import TimeService
from backend.app.services.sla import SLAService
from backend.app.tools.entitlement import EntitlementTool
from backend.app.services.entitlement import EntitlementService

class TestPhase3(unittest.TestCase):

    def setUp(self):
        # Create standard contexts for tests
        self.cust_a = UserContext(role=UserRole.CUSTOMER, customer_account_id="ACCT-001")
        self.cust_b = UserContext(role=UserRole.CUSTOMER, customer_account_id="ACCT-002")
        self.agent = UserContext(role=UserRole.SUPPORT_AGENT)
        self.admin = UserContext(role=UserRole.OPERATIONS_ADMIN)
        self.retriever = DocumentRetriever()

    # ==========================================
    # RETRIEVAL TESTS
    # ==========================================

    def test_retrieval_current_policy(self):
        # 1. Current policy is retrievable
        res = self.retriever.search("support severity", status="CURRENT")
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0].document_status, "CURRENT")

    def test_retrieval_deprecated_policy(self):
        # 2. Deprecated policy is identifiable as deprecated
        res = self.retriever.search("Support Policy v2", status="DEPRECATED")
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0].document_status, "DEPRECATED")

    def test_retrieval_customer_agreement(self):
        # 3. Customer agreement can be retrieved
        res = self.retriever.search("Northstar Logistics Enterprise Agreement", customer_account_id="ACCT-001")
        filenames = [r.source_name for r in res]
        self.assertIn("05_Northstar_Logistics_Enterprise_Agreement.pdf", filenames)

    # ==========================================
    # AUTHORIZATION & RBAC TESTS
    # ==========================================

    def test_customer_access_own_order(self):
        # 6. Customer can access own order
        res = DataLookupTool.lookup_order(self.cust_a, "ORD-1001")
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.data.account_id, "ACCT-001")

    def test_customer_denied_other_order(self):
        # 7. Customer cannot access another account's order
        res = DataLookupTool.lookup_order(self.cust_a, "ORD-2001")
        self.assertEqual(res.status, "UNAUTHORIZED")
        self.assertIsNone(res.data)

    def test_customer_denied_other_tickets(self):
        # 8. Customer cannot access another account's tickets
        res = DataLookupTool.get_account_tickets(self.cust_a, "ACCT-002")
        self.assertEqual(res.status, "UNAUTHORIZED")
        self.assertIsNone(res.data)

    def test_internal_user_access_authorized(self):
        # 9. Internal user can access authorized operational data
        res = DataLookupTool.lookup_order(self.agent, "ORD-2001")
        self.assertEqual(res.status, "SUCCESS")
        self.assertIsNotNone(res.data)

    # ==========================================
    # AUTHORITY & PRECEDENCE TESTS
    # ==========================================

    def test_customer_agreement_wins(self):
        # 10. Customer agreement wins when applicable (authority resolution)
        sources = [
            {"source_name": "01_Support_Policy_v3_CURRENT.pdf", "document_status": "CURRENT"},
            {"source_name": "05_Northstar_Logistics_Enterprise_Agreement.pdf", "document_status": "CURRENT"}
        ]
        gov = AuthorityEngine.resolve_governing_source(sources, customer_account_id="ACCT-001")
        self.assertEqual(gov["source_name"], "05_Northstar_Logistics_Enterprise_Agreement.pdf")

    def test_deprecated_does_not_override(self):
        # 11. Deprecated policy does not override current policy
        sources = [
            {"source_name": "01_Support_Policy_v3_CURRENT.pdf", "document_status": "CURRENT"},
            {"source_name": "02_Support_Policy_v2_DEPRECATED.pdf", "document_status": "DEPRECATED"}
        ]
        gov = AuthorityEngine.resolve_governing_source(sources)
        self.assertEqual(gov["source_name"], "01_Support_Policy_v3_CURRENT.pdf")

    def test_historical_ticket_resolution_override(self):
        # 12. Historical ticket does not override current policy (Conflict Detection)
        sources = [
            {"source_name": "01_Support_Policy_v3_CURRENT.pdf", "document_status": "CURRENT", "document_type": "Support Policy"},
            {"source_name": "TKT-450", "document_status": "CLOSED", "document_type": "ticket"}
        ]
        res = SourceResolver.resolve_conflicts(sources)
        self.assertEqual(res.selected_source, "01_Support_Policy_v3_CURRENT.pdf")
        self.assertIn("Historical ticket guidance conflicts", res.reason)

    # ==========================================
    # TIME & SLA TESTS
    # ==========================================

    def test_snapshot_time_is_used(self):
        # 14. Snapshot time is used
        snapshot = TimeService.get_snapshot_time()
        self.assertEqual(snapshot.year, 2026)
        self.assertEqual(snapshot.month, 8)
        self.assertEqual(snapshot.day, 16)

    def test_sla_calculation(self):
        # 15. SLA calculation is deterministic
        # TKT-501 (ACCT-001) P1 created on 2026-08-16 10:30. Northstar agreement P1 is 15 minutes, 24x7.
        res = SLAService.calculate_sla(
            created_at_str="2026-08-16 10:30",
            severity="P1",
            plan="Enterprise",
            account_id="ACCT-001"
        )
        self.assertEqual(res.status, "BREACHED")
        self.assertEqual(res.target_hours, 0.25)
        self.assertEqual(res.elapsed_hours, 0.5)  # 10:30 to 11:00 snapshot is 30 mins

    # ==========================================
    # BUSINESS LOGIC TESTS
    # ==========================================

    def test_cancellation_calculation(self):
        # 16. Cancellation calculation
        # ACCT-001 (Northstar) ORD-1001 BOOKED, cancelled 2 hours later. Northstar agreement says 0 fee before pickup.
        res = EntitlementTool.check_cancellation_entitlement(self.cust_a, "ORD-1001")
        self.assertTrue(res.eligible)
        self.assertEqual(res.fee, 0.0)

        # Standard customer (ACCT-003) ORD-3001 within 30 mins -> fee should be 0.
        res_standard = EntitlementTool.check_cancellation_entitlement(self.agent, "ORD-3001")
        self.assertTrue(res_standard.eligible)
        self.assertEqual(res_standard.fee, 0.0)

    def test_service_credit_calculation(self):
        # 17. Service-credit calculation
        # ACCT-002 (LumenWorks) ORD-2002: missed pickup by 4.5 hours, carrier fault. Custom agreement gets fixed 300 INR credit.
        res = EntitlementTool.check_service_credit_entitlement(self.cust_b, "ORD-2002")
        self.assertTrue(res.eligible)
        self.assertEqual(res.credit_amount, 300.0)
        self.assertEqual(res.governing_source, "06_LumenWorks_Service_Agreement.pdf")

    def test_missing_info_handling(self):
        # 18. Missing-information handling
        # If we pass an order with missing details (e.g. carrier fault None), it must return uncertainty.
        order = {"order_id": "ORD-X", "account_id": "ACCT-003", "status": "BOOKED", "carrier_fault": None}
        account = {"account_id": "ACCT-003"}
        res = EntitlementService.evaluate_service_credit(order, account)
        self.assertEqual(res.status, "INSUFFICIENT_INFORMATION")

if __name__ == "__main__":
    unittest.main()
