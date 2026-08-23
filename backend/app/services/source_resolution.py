from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from backend.app.retrieval.authority import AuthorityEngine

class ConflictResolutionResult(BaseModel):
    conflict_detected: bool
    sources: List[str]
    selected_source: Optional[str]
    reason: str
    requires_human_review: bool

class SourceResolver:
    @classmethod
    def resolve_conflicts(
        cls,
        retrieved_sources: List[Dict[str, Any]],
        customer_account_id: Optional[str] = None
    ) -> ConflictResolutionResult:
        """
        Detects conflicts in retrieved sources and resolves them using the authority hierarchy.
        """
        source_names = list(set(src.get("source_name") for src in retrieved_sources if src.get("source_name")))
        
        if not source_names:
            return ConflictResolutionResult(
                conflict_detected=False,
                sources=[],
                selected_source=None,
                reason="No sources retrieved.",
                requires_human_review=False
            )
            
        # Detect deprecated vs current policy conflicts
        has_current_policy = any("CURRENT" in src.get("document_status", "") for src in retrieved_sources)
        has_deprecated_policy = any("DEPRECATED" in src.get("document_status", "") for src in retrieved_sources)
        
        # Resolve governing source using authority engine
        governing = AuthorityEngine.resolve_governing_source(retrieved_sources, customer_account_id)
        
        if not governing:
            return ConflictResolutionResult(
                conflict_detected=False,
                sources=source_names,
                selected_source=None,
                reason="Could not determine governing source.",
                requires_human_review=True
            )
            
        selected_source = governing.get("source_name")
        
        # Check if there is an override/conflict
        conflict_detected = False
        reason = "Governing policy applied."
        requires_human_review = False
        
        # Agreement override check
        has_customer_agreement = any(
            AuthorityEngine.get_source_info(name).get("customer_account_id") == customer_account_id
            for name in source_names if AuthorityEngine.get_source_info(name)
        ) if customer_account_id else False

        if has_customer_agreement and len(source_names) > 1:
            conflict_detected = True
            reason = "Customer-specific agreement applies to this account and overrides the general policy."
        elif has_current_policy and has_deprecated_policy:
            conflict_detected = True
            reason = "Current policy version overrides the deprecated version."
        elif len(source_names) > 1:
            # General case where multiple documents are present
            conflict_detected = True
            reason = f"Resolved conflict in favor of higher authority document: {selected_source}."
            
        # If there are historical tickets, clarify they do not override current policy
        has_historical_ticket = any("TKT-" in src.get("source_name", "") or "ticket" in src.get("document_type", "").lower() for src in retrieved_sources)
        if has_historical_ticket:
            conflict_detected = True
            reason = "Historical ticket guidance conflicts with the current policy. Current policy takes precedence."
            
        return ConflictResolutionResult(
            conflict_detected=conflict_detected,
            sources=source_names,
            selected_source=selected_source,
            reason=reason,
            requires_human_review=requires_human_review
        )
