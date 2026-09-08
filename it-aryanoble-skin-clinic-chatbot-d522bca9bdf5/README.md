# Arya Noble AI Chatbot System

Enterprise Skin Clinic AI Chatbot Monorepo powering intelligent clinical assistance, knowledge base RAG retrieval, clinic branch administration, and automated Clinic Information System (CIS) data integration.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Project Modules & Scope Index](#project-modules--scope-index)
3. [Technology Stack Summary](#technology-stack-summary)
4. [Quick Start with Docker Compose](#quick-start-with-docker-compose)
5. [Service Endpoints](#service-endpoints)
6. [Data Integration & RSA Security](#data-integration--rsa-security)
7. [Repository Structure](#repository-structure)

---

## System Architecture

```
                       ┌────────────────────────┐
                       │    Next.js Frontend    │
                       │    (Port 3000 / Web)   │
                       └───────────┬────────────┘
                                   │ HTTP / REST
                                   ▼
┌───────────────────────────────────────────────────────────────┐                  ┌─────────────────────────┐
│                    FastAPI Backend Core                       │ <── Webhooks ─── │  Mock CIS Microservice  │
│  ┌────────────────────┬────────────────────────────────────┐  │  RSA Signed      │ (Automated Startup &    │
│  │ Authentication     │  RBAC, Branch, & Admin Services    │  │ (X-Signature)    │  Hourly Push Worker)    │
│  ├────────────────────┴────────────────────────────────────┤  │                  └─────────────────────────┘
│  │  RAG Engine Subsystem (app/rag)                         │  │
│  │  Docling Parser -> Chunker -> pgvector -> Hybrid Search │  │
│  └──────────────────────────────┬──────────────────────────┘  │
└─────────────────────────────────┼─────────────────────────────┘
                                  │ Async ORM (SQLAlchemy 2.0)
                                  ▼
                     ┌──────────────────────────┐
                     │      PostgreSQL DB       │
                     │  (Relational + pgvector) │
                     └──────────────────────────┘
```

---

## Project Modules & Scope Index

| Directory / Scope | Description | Primary Tech Stack | Documentation |
| :--- | :--- | :--- | :--- |
| [**`backend/`**](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/README.md) | FastAPI Modular Monolith REST API backend powering core services & enterprise RAG pipeline. | Python 3.11, FastAPI, SQLAlchemy, PostgreSQL (`pgvector`), Docling | [Backend README](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/backend/README.md) |
| [**`frontend/`**](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/frontend/README.md) | Next.js App Router frontend featuring a unified `/dashboard` interface with granular Role-Based Access Control (RBAC), plus a Chatbot Widget. | Next.js 16, React 19, TypeScript, Tailwind CSS, TanStack Query | [Frontend README](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/frontend/README.md) |
| [**`mock-cis/`**](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/mock-cis/README.md) | Mock Clinic Information System (CIS) pushing RSA-signed branch and doctor master data to backend. | Python 3.11, FastAPI, Cryptography (RSA), HTTPX | [Mock CIS README](file:///d:/Work/Company/widya-robotics/projects/arya-noble/project/mock-cis/README.md) |

---

## Technology Stack Summary

- **Frontend**: Next.js 16 (App Router), React 19, Tailwind CSS v4, TanStack Query v5, Axios
- **Backend API**: Python 3.11, FastAPI, Uvicorn, Pydantic v2
- **Database & Vectors**: PostgreSQL 16+ with `pgvector` extension, SQLAlchemy 2.0 (AsyncIO), Alembic
- **RAG & AI Pipeline**: LangChain, HuggingFace (`BAAI/bge-m3`), OpenAI GPT-4o, Google Gemini, Docling Document Parser
- **Security & Auth**: OAuth2 JWT Tokens, Passlib (`bcrypt`), RSA-SHA256 Payload Signature Verification
- **Container Orchestration**: Docker, Docker Compose

---

## Quick Start with Docker Compose

Ensure Docker Engine and Docker Compose are installed, then run from project root:

### 1. Launch All Services (Development Mode)
```bash
docker compose up --build
```

### 2. Launch All Services (Production Mode)
```bash
docker compose -f docker-compose.prod.yaml up --build -d
```

### 3. Service Verification
Once containers boot up:
- Backend will run at `http://localhost:8000`
- Frontend will run at `http://localhost:3000`
- Mock CIS will run at `http://localhost:8001`
- PostgreSQL pgvector DB will run at `localhost:50010`

---

## Service Endpoints

| Service | Local URL | Key Documentation / Interfaces |
| :--- | :--- | :--- |
| **Frontend Web App** | `http://localhost:3000` | Unified `/dashboard` with granular Role-Based Access Control |
| **Backend OpenAPI Docs** | `http://localhost:8000/docs` | Interactive Swagger UI |
| **Backend ReDoc** | `http://localhost:8000/redoc` | API Specification Reference |
| **Backend Health Check** | `http://localhost:8000/health` | Service status JSON |
| **Mock CIS API Docs** | `http://localhost:8001/docs` | Mock CIS trigger endpoints |

---

## Data Integration & RSA Security

The system uses a **Push-Only, RSA-Signed Webhook Architecture** for integrating external master data from CIS:

1. **One-Way Push**: Backend does not initiate outbound HTTP pull requests. CIS pushes branch and doctor updates directly to `POST /api/webhooks/cis`.
2. **RSA Signature Verification**: Webhook requests are signed by CIS using its RSA Private Key (`RSA-SHA256`). The backend validates the base64 signature sent in the `X-Signature` header against CIS's RSA Public Key (`CIS_RSA_PUBLIC_KEY_PATH=keys/cis_public_key.pem`).
3. **Automated Seed & Periodic Sync**: On startup, `mock-cis` automatically pushes initial seed data (`bulk.sync`) to the backend and repeats every **1 hour** automatically in the background.

---

## Repository Structure

```text
.
├── backend/                  # FastAPI Backend Core & RAG Subsystem
├── frontend/                 # Next.js App Router Web Client
├── mock-cis/                 # Mock Clinic Information System & RSA Webhook Pusher
├── docker-compose.yaml       # Development container orchestration manifest
├── docker-compose.prod.yaml  # Production container orchestration manifest
└── README.md                 # Project root documentation
```
