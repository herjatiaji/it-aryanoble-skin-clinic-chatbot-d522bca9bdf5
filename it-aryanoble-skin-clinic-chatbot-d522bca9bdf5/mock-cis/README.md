# Mock CIS (Clinic Information System) Service

This module simulates the external **Clinic Information System (CIS)** environment. It serves as both a testing ground and a **reference implementation** for the external CIS development team to integrate with the Arya Noble AI Chatbot ecosystem.

---

## Integration Overview

The integration between the CIS and the Arya Noble AI Chatbot consists of three main pillars:

1. **Master Data Synchronization**: Background webhooks to keep clinics and doctors in sync.
2. **Seamless SSO (Single Sign-On)**: Secure token generation so doctors don't need to log in twice.
3. **Chatbot UI Integration**: Embedding the AI assistant widget directly into the CIS dashboard.

---

## 1. Master Data Synchronization (Backend-to-Backend)

The CIS must push real-time master data (Branches and Doctors) to the AI Chatbot Backend via **RSA-signed webhooks**.

### How it works:

- **Push-Only Architecture**: The CIS pushes data to `POST /api/webhooks/cis`.
- **Security**: Payloads must be signed using an RSA Private Key (`RS256`). The signature is sent in the `X-Signature` HTTP header.
- **Auto-Sync**: In this mock service, data is pushed automatically every hour.

### Webhook Event Types:

- `branch.upsert`: Insert or update clinic branches.
- `doctor.upsert`: Insert or update doctors.
- `bulk.sync`: Sync all data at once.

---

## 2. Seamless SSO Authentication

To provide a seamless experience, doctors logged into the CIS should automatically be authenticated when interacting with the Chatbot widget.

### How it works:

1. When a doctor logs into the CIS, the CIS Backend generates a **JWT (JSON Web Token)**.
2. The token must be signed using the **CIS RSA Private Key** (`RS256` algorithm).
3. The payload must contain the doctor's unique ID in the `sub` claim (e.g., `DR-12345`).
4. This token is passed to the CIS Frontend (Dashboard) and stored (e.g., in `localStorage`).
5. The Chatbot UI uses this token in the `Authorization: Bearer <TOKEN>` header for all chat interactions.

---

## 3. Chatbot UI Integration (Frontend)

The mock service includes a reference React implementation (`frontend/src/components/FloatingChatbot.jsx`) demonstrating how to embed the Chatbot widget.

### Integration Steps for the CIS Frontend Team:

1. **Copy the Component**: The `FloatingChatbot.jsx` and `FloatingChatbot.css` are built as pure, reusable React components.
2. **Pass the Props**: Inject the required contextual data into the component:
   ```jsx
   <FloatingChatbot
   	token="eyJhbGciOiJSUzI1Ni... (SSO Token)"
   	doctorName="Dr. Jane Doe, Sp.D.V.E."
   	branchId="11111111-1111-1111-1111-111111111111"
   	apiBaseUrl="https://api.chatbot.aryanoble.com"
   />
   ```
3. **API Flow inside the Component**:
   - **Start Session**: Calls `POST /api/chats/` with the `branch_id`.
   - **Send Message**: Calls `POST /api/chats/{session_id}/messages` using `FormData` (supports text and file attachments).
   - **Receive Message**: Polls `GET /api/chats/{session_id}/messages` to get the AI's response (or uses WebSockets/SSE in production).

---

## API Endpoints Reference

### Chatbot Backend APIs (Target for CIS)

| Method | Endpoint                   | Description                   | Auth Required        |
| :----- | :------------------------- | :---------------------------- | :------------------- |
| `POST` | `/api/webhooks/cis`        | Receive Master Data sync      | `X-Signature` Header |
| `POST` | `/api/chats/`              | Create a new chat session     | Bearer Token (RS256) |
| `POST` | `/api/chats/{id}/messages` | Send message to AI            | Bearer Token (RS256) |
| `GET`  | `/api/chats/{id}/messages` | Get chat history & AI replies | Bearer Token (RS256) |

### Mock CIS Endpoints (For Testing & Simulation)

| Method | Endpoint               | Description                                 |
| :----- | :--------------------- | :------------------------------------------ |
| `POST` | `/auth/login`          | Simulates doctor login, returns RS256 token |
| `POST` | `/trigger/push-doctor` | Manually sync a doctor to the AI backend    |
| `POST` | `/trigger/push-all`    | Manually sync all data to the AI backend    |

---

## Local Setup & Execution

### Running the complete Mock CIS (Backend + Frontend)

```bash
# Starts the FastAPI webhook service and the Vite React Frontend
docker compose up --build mock-cis
```

- **Mock CIS Dashboard (UI)**: `http://localhost:8001/dashboard`
- **Mock CIS API (Swagger)**: `http://localhost:8001/docs`
