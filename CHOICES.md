# Engineering Choices & Tradeoffs: ParcelPilot

This document summarizes the technical choices, libraries, and design omissions in the ParcelPilot AI Support system.

## Chosen Technologies

### 1. Backend Orchestration: LangGraph
- **Why**: Standard RAG frameworks (like LangChain or LlamaIndex pipelines) are too linear. Support workflows are cyclic—retrieving an order might prompt searching an agreement, which might trigger an entitlement calculation, which might require another document lookup. LangGraph allows cyclical, stateful agent routing.

### 2. Relational Store: SQLite
- **Why**: SQLite is a self-contained, zero-configuration database, making it ideal for assessments. It allows us to load the entire Excel workbook into structured relational tables using SQLAlchemy.

### 3. Vector Database: ChromaDB
- **Why**: ChromaDB is lightweight, runs in-process, and allows easy metadata filtering (e.g. status, customer account ID, authority level), which is essential for our Source Precedence strategy.

### 4. LLM Provider: Google Gemini API (with Abstraction Layer)
- **Why**: Gemini offers high context limits, native structured output capabilities, and excellent performance. A model provider abstraction is implemented in code so that switching to OpenAI, Anthropic, or local models requires editing a single wrapper class.

### 5. API Server: FastAPI
- **Why**: High performance, asynchronous capability, automatic Pydantic validation, and clean Swagger/OpenAPI documentation generation.

### 6. Frontend: React, Vite, & TypeScript
- **Why**: React is standard for interactive stateful dashboards. Vite provides sub-second hot reloading, and TypeScript guarantees type safety across our chat messages and tool traces.

## Core Architectural Tradeoffs

### 1. Deterministic Calculation Service vs. LLM Arithmetic
- **Why**: LLMs are notorious for mathematical inaccuracies, especially when calculating timestamps or currency credits. We routing all math to a dedicated Python calculation service.

### 2. Mocked Authentication vs. OAuth2/OpenID
- **Why**: To keep the assessment runnable in a local Docker container without requiring setting up Firebase, Auth0, or PostgreSQL user schemas, we implemented a robust mocked role selector representing `CUSTOMER`, `SUPPORT_AGENT`, and `OPERATIONS_ADMIN`.

## What Was Intentionally NOT Built & Why

1. **Celery / Redis Background Queues**: Ingestion and analytics are computed synchronously or via simple async background tasks in FastAPI. Introducing Redis/Celery adds deployment overhead without a real performance bottleneck for this scale.
2. **Kubernetes Deployment**: Simple Docker Compose is used since it provides multi-container orchestration (Backend + Frontend) and is highly portable for local evaluations.
3. **Real-time Streaming WebSockets**: Normal HTTP long polling or SSE is used for simplicity, keeping the frontend state flow direct and easy to debug.

## Phase 5 safe state-changing action design choices

### 1. State-Changing Separation
- **Choice**: The LLM / LangGraph agent cannot directly execute state-changing actions. It can only call `prepare_action` which records a proposal in the `action_proposals` SQLite table and returns `requires_confirmation = True`.
- **Why**: Ensures that state updates can never happen via hallucination or indirect prompt injection. Execution is deterministic and requires explicit human consent.

### 2. Double Authorization (Re-Authorization)
- **Choice**: Checking permissions both at action preparation time AND immediately before execution.
- **Why**: Prevents race conditions or session-jacking where a user's role might change between preparing and executing an action.

### 3. Server-Side Proposals & Expiration
- **Choice**: Action proposals are stored in SQLite (rather than in-memory) and expire after a configurable TTL (e.g. `ACTION_CONFIRMATION_TTL_MINUTES=15`).
- **Why**: Storing proposals in-memory would lose state upon backend restart. Database persistence ensures robustness, and expiration guarantees that stale decisions aren't executed accidentally.

### 4. Idempotency & Tamper Prevention
- **Choice**: Storing a unique `action_id` (acting as an idempotency key) and comparing optional request payloads with the database-stored proposal.
- **Why**: Re-running the same `action_id` returns `ALREADY_EXECUTED` to prevent double-mutations (e.g. creating duplicate follow-up tasks). Validating the payload against the database-stored changes blocks malicious parameter tampering.

