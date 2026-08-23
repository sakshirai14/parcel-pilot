# System Design: ParcelPilot AI Support Agent

This document explains the structural and architectural design choices of the ParcelPilot AI Support system.

## 1. Agent vs. Simple RAG
A simple RAG (Retrieval-Augmented Generation) pipeline maps user queries to vector database lookups and directly feeds them into a generation model. While this works for simple QA, it fails for customer support where queries require:
- **Routing**: Decisions like whether to check a shipping log, a service contract, or common support policies.
- **Verification**: Cross-checking user authorization to access records.
- **Calculation**: Running complex arithmetic for refund eligibility.
- **Iterative Tool Calls**: Fetching an order ID first, then searching the customer contract using the account ID tied to that order, and then looking up the cancellation rules.

By framing this as a **LangGraph-driven Agent**, the system has a dynamic state and can loop through multiple reasoning steps to fulfill complex workflows.

## 2. Separation of Document Retrieval & Structured Lookup
- **Document Search (Vector DB)**: Unstructured information like SLA definitions, agreements, and policies are stored and searched semantically.
- **Operational Data Lookup (SQLite)**: Core transaction records (accounts, orders, tickets) require precise, relational structured queries. 
Mixing these (e.g. putting transaction rows as chunks inside a vector database) leads to hallucinations, missing records, and inability to filter by date or status accurately.

## 3. Deterministic Business Calculations
Under no circumstances should the LLM calculate refund amounts, cancellation fees, or SLA time differences using text prompts. Arithmetic and rule verification are implemented in pure Python. The agent's role is to extract variables (dates, amounts) from the structured data and feed them to these deterministic service functions.

## 4. Source Precedence & Customer Agreement Overrides
When information conflict occurs, the system resolves it according to a strict priority list:
1. **Signed Customer Agreements** (Maximum authority, customer-specific).
2. **Current Support Policy** (Standard baseline).
3. **Product Operations Guide** (Operational references).
4. **Historical Tickets** (Used only as context; does not govern active decisions).

## 5. Handling Deprecated & Misinformative Documents
- **Deprecated Policies**: Flagged in metadata. During ingestion, they are given `authority_level = 0`. The document search filters these out or ranks them below current guidelines.
- **Historical Tickets**: May contain outdated suggestions. The system explicitly ranks official documentation and current policies above historical ticket resolutions.

## 6. Role-Based Access Control (RBAC)
Security is enforced at the backend tool/service layer, not in the LLM system prompt. If a customer tries to query orders belonging to a different account ID, the `lookup_operational_data` tool returns `ACCESS_DENIED` before compiling the payload for the LLM.

## 7. Action Confirmation & Execution Lifecycle (Human-in-the-Loop)
Any state-changing action (such as escalations, ticket updates, or task creations) is governed by a strict confirmation and execution lifecycle:
1. **User Request & Investigation**: The agent analyses the query and operational database state.
2. **Action Proposal (`prepare_action`)**: The agent calls `prepare_action` (a read-only tool) which writes a proposal with status `PENDING_CONFIRMATION` into the `action_proposals` SQLite table and returns `requires_confirmation = True` to terminate the agent loop.
3. **Explicit Confirmation**: The user confirms the action with an explicit phrase (e.g. "Yes", "Proceed").
4. **Re-Authorization**: Immediately prior to execution, the backend performs role-based checks again using `UserContext` to ensure the session and user are still authorized.
5. **Execution (`execute_action`)**: The transaction is committed to SQLite (creating escalations, updating tickets, or creating tasks).
6. **Idempotency & Expiration**: Unique action IDs prevent duplicate execution (returning `ALREADY_EXECUTED`). Stale proposals expire after a configurable period (e.g. 15 minutes).
7. **Audit Logging**: Every mutation creates a secure log entry in the `audit_logs` table tracking previous/final state, authorization outcome, and action metadata.


## 8. Proactive Issue Detection
The operational dashboard analyzes tickets, orders, and known issues using deterministic aggregations. It groups issues by known clusters (e.g., repeating complaints on the same route or carrier) and SLA risks, highlighting systemic anomalies in the logistics operation.

## 9. Uncertainty and Trust
If data is missing (e.g., carrier fault flag not set), the agent flags an uncertainty status and escalates rather than guessing the outcome.

## 10. Production Scalability
To transition to production, the system would replace ChromaDB with an enterprise-grade vector database (e.g. pgvector or Qdrant) and SQLite with PostgreSQL, and deploy LangGraph under LangGraph Cloud or a distributed state store.
