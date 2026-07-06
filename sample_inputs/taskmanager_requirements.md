# Product Requirements — QuickTask API
**Version:** 1.0  
**Date:** 2026-07-03  
**Author:** Product Team  
**Target Platform:** Google Cloud Platform (GCP)

---

## 1. Executive Summary

QuickTask is a lightweight, cloud-native REST API that lets individuals and small teams manage their daily tasks. Users can register, log in, create tasks with priorities and due dates, assign them to team members, and track completion. The system must be reliable, fast, and deployable on GCP with minimal operational overhead.

---

## 2. Business Goals

- Provide a dead-simple task management backend that any frontend (web, mobile, CLI) can consume.
- Target audience: solo developers and small teams (2–15 people).
- Monetisation: free tier (up to 3 users, 100 tasks/month); paid tier ($9/month, unlimited).
- MVP must be live within 6 weeks of development start.

---

## 3. Stakeholders

| Role             | Name / Team       | Interest                                      |
|------------------|-------------------|-----------------------------------------------|
| Product Owner    | Sakthi            | Feature scope, launch timeline                |
| Backend Dev Team | Engineering       | Architecture, code quality, deployment        |
| End Users        | Individual / SMBs | Reliable API, fast response times             |
| DevOps           | Platform Team     | GCP infra, CI/CD, monitoring                  |
| Security         | InfoSec           | Auth, data privacy, GDPR compliance           |

---

## 4. Functional Requirements

### 4.1 User Management

- **FR-001** Users can register with email + password.
- **FR-002** Passwords must be hashed (bcrypt, min cost 12).
- **FR-003** Users authenticate via JWT (access token 15 min, refresh token 7 days).
- **FR-004** Users can update their display name and email.
- **FR-005** Users can delete their own account (soft delete; data retained 30 days).

### 4.2 Task Management (CRUD)

- **FR-006** Authenticated users can create a task with: title (required), description (optional), priority (LOW / MEDIUM / HIGH / URGENT), due_date (optional ISO-8601), tags (string list, max 10).
- **FR-007** Users can list their own tasks with filters: status, priority, tag, due_date range; supports cursor-based pagination (default page size 20, max 100).
- **FR-008** Users can retrieve a single task by ID.
- **FR-009** Users can update any field of their own task.
- **FR-010** Users can mark a task complete / incomplete (toggles `completed_at` timestamp).
- **FR-011** Users can delete their own task (soft delete).

### 4.3 Team & Assignment

- **FR-012** A user can create a Workspace (max 1 workspace on free tier, unlimited on paid).
- **FR-013** Workspace owner can invite members by email; invitee receives an invitation link (valid 48 h).
- **FR-014** Within a workspace, tasks can be assigned to any member.
- **FR-015** Assigned users see assigned tasks in their "My Tasks" list.
- **FR-016** Workspace owner can remove members.

### 4.4 Comments

- **FR-017** Users can add comments to any task in their workspace.
- **FR-018** Comments support plain text, max 2,000 characters.
- **FR-019** Comment authors can edit / delete their own comments.

### 4.5 Notifications (v1 — email only)

- **FR-020** Email notification when a task is assigned to a user.
- **FR-021** Email reminder 24 hours before task due_date (if due_date is set).
- **FR-022** Email when a comment is added to a task the user owns or is assigned to.

### 4.6 Admin

- **FR-023** Admin endpoint to list all users (paginated).
- **FR-024** Admin can deactivate / reactivate any user account.
- **FR-025** Admin can view aggregate usage stats: total users, tasks created per day (last 30 days), active workspaces.

---

## 5. Non-Functional Requirements

| ID      | Category        | Requirement                                                                 |
|---------|-----------------|-----------------------------------------------------------------------------|
| NFR-001 | Performance     | p95 API latency < 200 ms under 200 concurrent users                         |
| NFR-002 | Availability    | 99.9 % uptime SLA (excluding planned maintenance)                           |
| NFR-003 | Scalability     | Horizontally scalable; support up to 10,000 registered users at launch      |
| NFR-004 | Security        | OWASP Top-10 mitigated; all data encrypted in transit (TLS 1.2+) and at rest|
| NFR-005 | Compliance      | GDPR-compliant: right to erasure, data export, consent logging               |
| NFR-006 | Maintainability | >80 % test coverage; all public APIs documented via OpenAPI 3.0              |
| NFR-007 | Observability   | Structured JSON logs, Prometheus metrics, distributed tracing (OpenTelemetry)|
| NFR-008 | Deployability   | Fully containerised (Docker); deploy to GCP Cloud Run via CI/CD              |
| NFR-009 | Data Retention  | Soft-deleted records purged after 30 days via scheduled job                  |
| NFR-010 | Rate Limiting   | 60 req/min per user (free tier); 600 req/min (paid tier)                    |

---

## 6. System Constraints

- **Language & Framework:** Python 3.12, FastAPI
- **Database:** PostgreSQL 15 (Cloud SQL on GCP)
- **Cache:** Redis (Memorystore on GCP) for JWT blocklist and rate-limit counters
- **Email:** SendGrid (free tier — 100 emails/day)
- **Container Registry:** Google Artifact Registry
- **Deployment:** GCP Cloud Run (serverless containers)
- **CI/CD:** GitHub Actions
- **IaC:** Terraform (Google provider)
- **Secret Management:** Google Secret Manager

---

## 7. Data Model (high-level)

```
users           (id, email, password_hash, display_name, tier, is_active, created_at, deleted_at)
workspaces      (id, name, owner_id, created_at)
workspace_members (workspace_id, user_id, role[owner/member], joined_at)
invitations     (id, workspace_id, email, token, expires_at, accepted_at)
tasks           (id, workspace_id, creator_id, assignee_id, title, description, priority,
                 status[open/completed], due_date, completed_at, tags[], created_at, updated_at, deleted_at)
comments        (id, task_id, author_id, body, created_at, updated_at, deleted_at)
notifications   (id, user_id, type, payload_json, sent_at, error)
usage_events    (id, user_id, event_type, created_at)
```

---

## 8. API Overview (key endpoints)

```
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout

GET    /users/me
PATCH  /users/me
DELETE /users/me

POST   /workspaces
GET    /workspaces/{id}
POST   /workspaces/{id}/invite
DELETE /workspaces/{id}/members/{user_id}

POST   /tasks
GET    /tasks          (filterable, paginated)
GET    /tasks/{id}
PATCH  /tasks/{id}
DELETE /tasks/{id}
POST   /tasks/{id}/complete
DELETE /tasks/{id}/complete

POST   /tasks/{id}/comments
PATCH  /tasks/{task_id}/comments/{comment_id}
DELETE /tasks/{task_id}/comments/{comment_id}

GET    /admin/users
PATCH  /admin/users/{id}/status
GET    /admin/stats
```

---

## 9. Acceptance Criteria

- All CRUD endpoints return correct HTTP status codes (200/201/204/400/401/403/404/422).
- JWT expiry and refresh flow tested end-to-end.
- Rate limiting enforced and returns HTTP 429 with `Retry-After` header.
- Password reset flow (email link, 1-hour TTL) working.
- Soft-delete: deleted tasks do not appear in list responses.
- All endpoints covered by integration tests using TestClient.
- Load test with Locust: 200 VUs, 5-minute ramp — p95 < 200 ms, error rate < 0.1 %.
- Terraform plan produces a valid GCP Cloud Run + Cloud SQL + Memorystore topology with no errors.
- GitHub Actions pipeline: lint → test → build → push to Artifact Registry → deploy to Cloud Run (staging), with manual gate for production.

---

## 10. Out of Scope (v1)

- Mobile push notifications
- File attachments on tasks
- Recurring tasks / task templates
- Third-party OAuth (Google / GitHub SSO) — planned for v1.1
- Real-time websocket updates — planned for v2
