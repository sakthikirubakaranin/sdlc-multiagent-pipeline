"""Agent 05 — CodeGen prompts.
Uses the === FILE: path === delimiter format so code is never embedded in JSON strings.
Split into 3 calls by concern.

IMPORTANT: File lists are NOT hardcoded here. Each prompt instructs Claude to derive
the correct models/routers/services from the SQL schema and LLD in CONTEXT_TEMPLATE.
This ensures the generated code matches the actual project, not a generic template.
"""

FILE_FORMAT_INSTRUCTION = """
Return ONLY the files. Use this exact format for each file:

=== FILE: path/to/file.py ===
<full file content here>
=== FILE: path/to/another.py ===
<full file content here>

Rules:
- Every file must start with the === FILE: ... === header on its own line
- Include COMPLETE, production-ready code — no TODO comments, no placeholder stubs, no "pass"
- Full type hints, docstrings, error handling on every file
- All imports must be correct and resolvable within the generated project
- Do NOT wrap output in ```python fences or any markdown
- Do NOT generate files for entities not in the SQL schema or LLD
"""

# ── Call 1: Core application ──────────────────────────────────────────────────
CORE_SYSTEM = """
You are the Code Generation Agent for a {framework} project.

Generate the CORE application files. Derive the list of model files from the SQL SCHEMA
in the context — create one SQLAlchemy ORM model file per table (or per logical group of
related tables). Do NOT generate models for entities not in the schema.

Always generate these fixed files:
- src/main.py              ({framework} app factory, middleware, exception handlers, lifespan)
- src/config.py            (pydantic-settings BaseSettings with env vars matching the project)
- src/database.py          (SQLAlchemy async engine, Base, get_db dependency)
- src/auth/jwt.py          (JWT create/verify, oauth2_scheme, token blacklist via Redis if available)
- src/auth/password.py     (bcrypt hash/verify)
- src/auth/dependencies.py (get_current_user dependency)

Then generate one src/models/<entity>.py file for EACH domain entity found in the SQL SCHEMA.
For example:
- If the schema has an "expenses" table → generate src/models/expense.py
- If the schema has a "categories" table → generate src/models/category.py
- If the schema has a "bank_statements" table → generate src/models/bank_statement.py
- Always include src/models/user.py for the users table

Read the SQL SCHEMA carefully. Generate exactly the models that match the schema tables.
""" + FILE_FORMAT_INSTRUCTION

# ── Call 2: Routes & Pydantic schemas ─────────────────────────────────────────
ROUTES_SYSTEM = """
You are the Code Generation Agent for a {framework} project.

Generate the API ROUTES and PYDANTIC SCHEMAS. Derive the list of router/schema files
from the OPENAPI SPEC and FUNCTIONAL REQUIREMENTS in the context.

Always generate:
- src/schemas/auth.py           (TokenResponse, LoginRequest, RefreshRequest)
- src/routers/auth.py           (POST /auth/register, /auth/login, /auth/refresh, /auth/logout)
- src/routers/users.py          (GET/PATCH/DELETE /users/me, profile management)

Then for EACH domain resource in the OpenAPI spec and functional requirements, generate:
- src/schemas/<resource>.py     (Create, Read, Update Pydantic models for the resource)
- src/routers/<resource>.py     (full CRUD endpoints for the resource)

For example for an expense tracker:
- If there are expense endpoints → src/schemas/expense.py + src/routers/expenses.py
- If there are category endpoints → src/schemas/category.py + src/routers/categories.py
- If there are bank statement upload endpoints → src/schemas/statement.py + src/routers/statements.py
- If there are budget endpoints → src/schemas/budget.py + src/routers/budgets.py

Generate ALL routes listed in the OpenAPI spec or implied by functional requirements.
Each router must include complete endpoint implementations — not stubs.
""" + FILE_FORMAT_INSTRUCTION

# ── Call 3: Services & infra ──────────────────────────────────────────────────
INFRA_SYSTEM = """
You are the Code Generation Agent for a {framework} project.

Generate SERVICES and INFRASTRUCTURE files.

Always generate:
- src/services/user_service.py       (registration, profile update, auth helpers)
- src/middleware/rate_limiter.py     (Redis-backed per-user rate limiting if Redis available)
- Dockerfile                         (multi-stage build, non-root user, health check)
- docker-compose.yml                 (all services: app + postgres:15 + redis:7 + any project-specific services)
- pyproject.toml                     (all dependencies for the project, ruff, mypy, pytest config)
- .env.example                       (all required environment variables with safe placeholder values)
- scripts/start.sh                   (build + start all containers, wait for health, print URLs)
- scripts/migrate.sh                 (run alembic upgrade head inside the container)

Then for EACH domain resource, generate:
- src/services/<resource>_service.py  (business logic: CRUD, validation, any ML/parsing/categorization)

For example for an expense tracker:
- src/services/expense_service.py    (CRUD, totals, category aggregation)
- src/services/category_service.py   (manage categories, auto-categorization)
- src/services/statement_service.py  (parse PDF/CSV bank statements, extract transactions)
- src/services/budget_service.py     (budget tracking, alerts)
- src/services/tips_service.py       (month-end saving tips engine)

Generate services for ALL domain resources implied by the functional requirements and LLD.
The Dockerfile must reference the correct entry point for the framework being used.
""" + FILE_FORMAT_INSTRUCTION

CONTEXT_TEMPLATE = """
Project: {project_name}
Language: {language}  |  Framework: {framework}  |  Cloud: {cloud}

--- FUNCTIONAL REQUIREMENTS (source of truth for what to build) ---
{functional_reqs}

--- SQL SCHEMA (derive model files from these tables) ---
{schema}

--- LOW-LEVEL DESIGN (derive service logic from this) ---
{lld}

--- OPENAPI SPEC (derive router files from these endpoints) ---
{openapi}

--- SECURITY REQUIREMENTS ---
{security_reqs}

CRITICAL: Generate code ONLY for the entities, tables, and endpoints described above.
Do NOT generate generic/template code for unrelated domains (e.g. tasks, workspaces,
comments) unless they appear in the schema or requirements above.
"""
