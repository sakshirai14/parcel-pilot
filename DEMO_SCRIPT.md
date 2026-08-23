# 5-Minute Assessment Demo Script: ParcelPilot

Use this script to guide the evaluation of the ParcelPilot Customer Support AI Agent application.

## Prerequisites & Running the Application

Ensure the assessment files have been copied to:
- `data/source/documents/` (the 6 PDFs)
- `data/source/` (`ParcelPilot_Assessment_Data.xlsx`)

### Commands to Run

```bash
# 1. Initialize data and ingest
python scripts/initialize.py

# 2. Run with Docker Compose
docker compose up --build

# Backend will run on http://localhost:8000
# Frontend will run on http://localhost:5173
```

---

## Script Flow

### 0:00–0:40 | Architecture Walkthrough
- **Visuals**: Show the codebase structure (backend, frontend, database, scripts).
- **Narrative**: "Welcome to the ParcelPilot Customer Support AI Agent demo. Our architecture uses FastAPI on the backend with LangGraph for multi-step agent execution, ChromaDB for document RAG, and SQLite for structured transactional operational lookups. The frontend is built on React + TypeScript. All calculations are handled deterministically in code rather than by LLM arithmetic."

### 0:40–2:00 | Customer Question (Standard QA)
- **Visuals**: Log in as customer demo user (`customer-demo`). Ask: *"What is the standard cancellation fee for my order?"*
- **Narrative**: "Logging in as a Customer. When asking about cancellation fees, the agent inspects the customer's active account context. Under the hood, it queries the vector store for standard policies and identifies specific customer agreements. Notice the citation panel displaying the authoritative PDF page, and the tool trace showing document search activity."

### 2:00–2:50 | Multi-Step Investigation
- **Visuals**: Log in as support agent (`support-demo`). Ask: *"Can Northstar Logistics cancel order ORD-1001 without a cancellation fee?"*
- **Narrative**: "Switching to a Support Agent. We request information on a specific order. The agent first looks up the order record from the SQLite database to locate the account. It retrieves the Northstar Logistics Enterprise Agreement. Then it references the Cancellation SOP. By resolving precedence—applying the contract override—the agent correctly reports the decision with detailed steps and references."

### 2:50–3:40 | RBAC + Action Confirmation
- **Visuals**: 
  - As Customer `customer-demo` (ACCT-001), try asking about `ACCT-002`'s tickets. Show the "Access Denied" or secure rejection.
  - As Support Agent, ask: *"Escalate ticket TKT-1001 due to SLA breach."* Show the Confirmation Card popup with [Confirm] / [Cancel].
- **Narrative**: "Security is handled at the database and tool layer. When a customer attempts to access records belonging to another account, the database wrapper returns a security error. For state-changing actions like ticket escalation, the agent cannot write directly. It prepares the action and generates a confirmation ticket for the user. Only when I click Confirm is the escalation written to the audit database."

### 3:40–4:30 | Operations Dashboard
- **Visuals**: Navigate to the Operations Dashboard page. Show the statistics, SLA breach warnings, issue clusters, and correlations.
- **Narrative**: "This is the Operations Dashboard, loaded from our snapshot database. We can see SLA breaches, tickets at risk, and systemic complaints. The analytics panel uses deterministic calculations to cluster tickets by issue pattern (e.g., carrier delays on specific routes), giving administrators an overview of current bottlenecks."

### 4:30–5:00 | Trust & Reliability Design
- **Visuals**: Ask a query where info is missing: *"What was the carrier fault explanation for order ORD-9999?"* (which has missing fields). Show agent reporting uncertainty.
- **Narrative**: "When key details are missing or contracts are ambiguous, our agent does not guess. It states that information is insufficient, outlines exactly what is missing, and recommends manual escalation. This guarantees accuracy and prevents hallucinations in critical operational environments."
