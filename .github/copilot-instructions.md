# AI Interview Intelligence System — Copilot Instructions

This file is automatically loaded into every GitHub Copilot Chat session for this repo.
Read it fully before responding to any request.

---

## Project Overview

You are helping build an **AI-Powered Adaptive Interview Intelligence System** — a
full-stack web application that:
- Parses candidate PDF resumes into a structured skill graph
- Analyzes job descriptions to map role requirements
- Generates adaptive, resume-grounded interview questions (not generic ones)
- Detects skill depth via adaptive follow-up questions
- Detects resume bluffing via operational verification questions
- Produces a structured evaluation report with hire/no-hire recommendation

---

## Your Behavior Rules (CRITICAL — follow these always)

### 1. Always Ask Before Acting
- Before writing any file: show the file path and first 20 lines, ask "Should I create this?"
- Before running any terminal command: show the exact command, ask "Should I run this?"
- Before installing any package: show the package name and reason, ask "OK to install?"
- Before any git operation: show the exact git command, ask "Should I run this?"

### 2. One Thing at a Time
- Never write multiple files at once without asking which to start with
- Complete and confirm each file before moving to the next
- At the end of every feature, suggest a commit message and ask "Ready to commit?"

### 3. Never Do Things On Your Own
- Do NOT silently create files
- Do NOT run commands without explicit approval
- Do NOT assume answers — ask the developer directly
- If unclear about a requirement, ask. Make the question specific, not open-ended.

### 4. Surface Tradeoffs
- When there are multiple valid approaches, present them with pros/cons
- Recommend one clearly, but let the developer choose

---

## Tech Stack (strictly follow this)

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui, Zustand |
| Backend | FastAPI (Python 3.11), SQLAlchemy async, Alembic, Pydantic v2 |
| Package manager | **uv** for Python (NOT pip, NOT poetry), npm for Node |
| Primary LLM | Groq API — model: `llama-3.1-70b-versatile` |
| Evaluation LLM | Google Gemini 1.5 Flash (1M context for full session) |
| Database | Supabase (PostgreSQL via asyncpg) |
| Auth | Supabase Auth + JWT verification in FastAPI |
| File storage | Supabase Storage |
| PDF parsing | PyMuPDF (fitz) |
| Deployment | Vercel (frontend) + Render (backend) — both free tier |
| CI/CD | GitHub Actions |
| Linting | ruff + mypy (Python), ESLint (TypeScript) |
| Testing | pytest + pytest-asyncio (backend), React Testing Library (frontend) |

---

## Architecture — Layered Pattern (never break this)

```
HTTP Request
    ↓
Router     (app/routers/)      — input validation, calls ONE service method, returns HTTP response
    ↓
Service    (app/services/)     — business logic, orchestrates repos + AI pipeline, raises domain errors
    ↓
Repository (app/repositories/) — all database queries, returns domain models
    ↓
Model      (app/models/)       — SQLAlchemy ORM definitions only
```

**Rules:**
- Routers never import SQLAlchemy or write SQL
- Services never import FastAPI or write SQL
- Repositories never contain business logic
- AI pipeline modules (ai_pipeline/) are called only from services, never from routers

---

## Code Quality Standards

### Python
- Type annotations on every function signature (no bare `Any`)
- Pydantic v2 models for all request/response schemas
- Every AI LLM call must have Pydantic schema validation on output
- Use `async/await` throughout — never blocking I/O
- `ruff` for linting and formatting, `mypy --strict` for types

### TypeScript / Next.js
- No `any` type — ever
- Server components by default; add `"use client"` only when needed
- All API calls go through `lib/api.ts` (typed axios client)
- Zustand for client-side state management

### Git
- Conventional Commits format: `feat(scope): description`
- Scopes: `backend | frontend | ai | db | auth | docker | ci | deps`
- Never commit `.env` files — always use `.env.example`
- Branch per feature: `feature/<name>`, `fix/<name>`, `chore/<name>`

---

## Project Directory Structure

```
interview-intelligence/
├── .github/
│   ├── copilot-instructions.md   ← you are here
│   ├── prompts/                  ← use these with Copilot Chat
│   └── workflows/
├── frontend/                     (Next.js 14)
├── backend/                      (FastAPI)
│   ├── app/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── models/
│   │   └── schemas/
│   └── ai_pipeline/
├── docker-compose.yml
└── .env.example
```

---

## How to Use the Prompt Files

In VS Code GitHub Copilot Chat, attach a prompt file:
1. Click the **paperclip (attach)** icon in Copilot Chat
2. Select **"Prompt..."**
3. Choose the relevant prompt file from `.github/prompts/`

Or type in chat: `#file:.github/prompts/00-orchestrator.prompt.md`

| Prompt File | Use When |
|---|---|
| `00-orchestrator.prompt.md` | Starting or resuming the build — always start here |
| `01-scaffold.prompt.md` | Project doesn't exist yet — first-time setup |
| `02-backend.prompt.md` | Writing FastAPI code (routers, services, repositories) |
| `03-ai-pipeline.prompt.md` | Implementing AI/LLM modules |
| `04-frontend.prompt.md` | Writing Next.js pages and components |
| `05-cicd.prompt.md` | GitHub Actions, Docker, linting setup |
| `06-git.prompt.md` | Committing changes, branch management |
| `07-tests.prompt.md` | Writing pytest or React Testing Library tests |

---

## Environment Variables Reference

```bash
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=

# Database
DATABASE_URL=postgresql+asyncpg://...

# AI
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-70b-versatile
GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-flash

# Storage
STORAGE_BUCKET=resumes

# Backend
BACKEND_CORS_ORIGINS=http://localhost:3000
ENVIRONMENT=development

# Frontend
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Never hardcode these values. Always read from environment variables.
