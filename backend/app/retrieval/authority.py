from typing import Dict, Any, Optional, List
from pydantic import BaseModel

class SourceAuthority(BaseModel):
    source_name: str
    authority_level: int
    status: str
    customer_account_id: Optional[str] = None
    effective_date: str
    version: str
    is_governing: bool = False

class AuthorityEngine:
    # Deterministic authority configuration mapped to filenames
    HIERARCHY = {
        "05_Northstar_Logistics_Enterprise_Agreement.pdf": {
            "authority_level": 100,
            "status": "CURRENT",
            "customer_account_id": "ACCT-001",
            "effective_date": "2023-06-01",
            "version": "1.0"
        },
        "06_LumenWorks_Service_Agreement.pdf": {
            "authority_level": 100,
            "status": "CURRENT",
            "customer_account_id": "ACCT-002",
            "effective_date": "2023-09-01",
            "version": "1.0"
        },
        "01_Support_Policy_v3_CURRENT.pdf": {
            "authority_level": 80,
            "status": "CURRENT",
            "effective_date": "2026-05-01",
            "version": "3.0"
        },
        "03_Cancellation_and_Service_Credit_SOP_v4.pdf": {
            "authority_level": 70,
            "status": "CURRENT",
            "effective_date": "2026-06-15",
            "version": "4.0"
        },
        "04_Product_Operations_Guide_and_Known_Issues.pdf": {
            "authority_level": 60,
            "status": "CURRENT",
            "effective_date": "2026-08-14",
            "version": "1.0"
        },
        "02_Support_Policy_v2_DEPRECATED.pdf": {
            "authority_level": 0,
            "status": "DEPRECATED",
            "effective_date": "2025-01-01",
            "version": "2.0"
        }
    }

    @classmethod
    def get_source_info(cls, source_name: str) -> Optional[Dict[str, Any]]:
        return cls.HIERARCHY.get(source_name)

    @classmethod
    def resolve_governing_source(
        cls, 
        sources: List[Dict[str, Any]], 
        customer_account_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Determines the governing source among a list of retrieved sources.
        - customer_account_id: The ID of the customer involved in the request.
        - Rules:
          1. Deprecated files are ignored / given lowest precedence.
          2. Customer Agreement (authority 100) wins for that specific customer.
          3. For other customers, general policies or SOPs apply.
          4. Returns the governing source information.
        """
        valid_sources = []
        for src in sources:
            name = src.get("source_name")
            info = cls.get_source_info(name)
            if not info:
                continue
            
            # Skip deprecated policies if a current one is present
            if info["status"] == "DEPRECATED":
                continue
                
            valid_sources.append((src, info))
            
        if not valid_sources:
            return None
            
        # Prioritize matching customer agreements first
        if customer_account_id:
            for src, info in valid_sources:
                if info.get("customer_account_id") == customer_account_id:
                    return {**src, **info, "is_governing": True}
                    
        # Otherwise, pick the one with the highest authority level
        valid_sources.sort(key=lambda x: x[1]["authority_level"], reverse=True)
        best_src, best_info = valid_sources[0]
        return {**best_src, **best_info, "is_governing": True}
