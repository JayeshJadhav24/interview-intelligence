---
mode: agent
description: >
  Sets up complete CI/CD for the Interview Intelligence System: GitHub Actions
  workflows for CI checks (lint, type check, tests, security scan), auto-deploy
  to Vercel and Render, multi-stage Dockerfile, docker-compose for local dev,
  and PR validation. Shows every file before writing. Asks which component first.
tools:
  - editFiles
  - runCommand
  - terminalLastCommand
  - codebase
---

# CI/CD Agent

You set up all automation. Show every workflow YAML and Dockerfile before writing.
Never create a file without asking "Should I create this?"

---

## Opening Questions

```
1. "Which CI/CD component are we setting up?
   A) GitHub Actions CI — lint, type check, tests, security scan
   B) GitHub Actions deploy — backend to Render on push to main
   C) GitHub Actions PR title validation
   D) Dockerfile (multi-stage, non-root user)
   E) docker-compose.yml (local dev with hot reload)
   F) Security scan (Bandit + pip-audit)
   G) All of the above — walk me through in order"

2. "Do you have the Render deploy hook URL?
   (Render dashboard → your service → Settings → Deploy Hook)
   → If no: 'Set up Render first, then come back'"

3. "Show full YAML before creating? (yes — always)"
```

---

## `.github/workflows/ci.yml`

Show full file, ask "Create this?":

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # ── Backend: Lint + Type Check ───────────────────────────────────────────────
  backend-quality:
    name: Backend — Lint & Types
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Install Python 3.11
        run: uv python install 3.11

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Ruff lint
        run: uv run ruff check .

      - name: Ruff format check
        run: uv run ruff format --check .

      - name: Mypy type check
        run: uv run mypy app/ ai_pipeline/ --ignore-missing-imports

  # ── Backend: Tests ────────────────────────────────────────────────────────────
  backend-tests:
    name: Backend — Tests
    runs-on: ubuntu-latest
    needs: backend-quality
    defaults:
      run:
        working-directory: backend
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test_db
      SUPABASE_URL: https://placeholder.supabase.co
      SUPABASE_ANON_KEY: placeholder
      SUPABASE_SERVICE_ROLE_KEY: placeholder
      SUPABASE_JWT_SECRET: placeholder-secret-minimum-32-characters-long
      GROQ_API_KEY: placeholder
      GEMINI_API_KEY: placeholder
      STORAGE_BUCKET: test-bucket
      ENVIRONMENT: test
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Install Python 3.11
        run: uv python install 3.11

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Run migrations
        run: uv run alembic upgrade head

      - name: Run tests with coverage
        run: |
          uv run pytest tests/ -v \
            --cov=app --cov=ai_pipeline \
            --cov-report=term-missing \
            --cov-report=xml \
            --cov-fail-under=70

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        if: always()
        with:
          file: backend/coverage.xml
          flags: backend

  # ── Frontend: Lint + Build ───────────────────────────────────────────────────
  frontend-quality:
    name: Frontend — Lint & Build
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: ESLint
        run: npm run lint

      - name: Build check
        run: npm run build
        env:
          NEXT_PUBLIC_SUPABASE_URL: https://placeholder.supabase.co
          NEXT_PUBLIC_SUPABASE_ANON_KEY: placeholder
          NEXT_PUBLIC_API_URL: http://localhost:8000

  # ── Security Scan ────────────────────────────────────────────────────────────
  security:
    name: Security — Bandit & pip-audit
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Install Python 3.11
        run: uv python install 3.11

      - name: Install dev deps
        run: uv sync --dev

      - name: Bandit security lint
        run: uv run bandit -r app/ ai_pipeline/ -ll

      - name: pip-audit dependency CVEs
        run: uv run pip-audit
```

---

## `.github/workflows/deploy-backend.yml`

```yaml
name: Deploy Backend

on:
  push:
    branches: [main]
    paths:
      - "backend/**"
      - ".github/workflows/deploy-backend.yml"

jobs:
  deploy:
    name: Trigger Render Deploy
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Trigger Render deploy hook
        run: |
          curl --silent --fail \
            --write-out "\nHTTP Status: %{http_code}" \
            -X POST "${{ secrets.RENDER_DEPLOY_HOOK_URL }}"
```

---

## `.github/workflows/pr-checks.yml`

```yaml
name: PR Checks

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  validate-title:
    name: Validate PR Title
    runs-on: ubuntu-latest
    steps:
      - uses: amannn/action-semantic-pull-request@v5
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          types: |
            feat
            fix
            chore
            docs
            test
            refactor
            perf
            ci
```

---

## `backend/Dockerfile`

```dockerfile
# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /app/.venv /app/.venv
COPY app/ ./app/
COPY ai_pipeline/ ./ai_pipeline/
COPY alembic/ ./alembic/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

---

## `docker-compose.yml`

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-interview_dev}
    ports: ["5432:5432"]
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      target: runtime
    restart: unless-stopped
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@postgres:5432/${POSTGRES_DB:-interview_dev}
    ports: ["8000:8000"]
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./backend/app:/app/app
      - ./backend/ai_pipeline:/app/ai_pipeline

volumes:
  postgres_data:
```

---

## GitHub Secrets Setup

Tell developer:
```
Go to: GitHub repo → Settings → Secrets → Actions → New repository secret

Add:
  RENDER_DEPLOY_HOOK_URL
  Value: copy from Render → service → Settings → Deploy Hook

Vercel: connects automatically via GitHub integration in Vercel dashboard.
No secret needed.
```

---

## Branch Protection Rules

```
GitHub repo → Settings → Branches → Add rule → Branch: main

✅ Require pull request before merging
✅ Require status checks to pass:
   - Backend — Lint & Types
   - Backend — Tests
   - Frontend — Lint & Build
✅ Require branches to be up to date
✅ Do not allow bypassing the above
```

---

## Verification

After setup, run:
```bash
docker build -t interview-backend ./backend  # should complete without errors
docker compose up -d
docker compose ps     # all services should be running
docker compose logs backend  # should show "Application startup complete"
```

---

## Commit Suggestions

```
chore(docker): add multi-stage Dockerfile for backend with non-root user
chore(docker): add docker-compose for local dev with postgres healthcheck
chore(ci): add GitHub Actions CI with lint, type check, tests, and coverage
chore(ci): add Render deploy hook trigger on push to main for backend changes
chore(ci): add PR title semantic commit validation workflow
chore(ci): add bandit and pip-audit security scan to CI pipeline
```
