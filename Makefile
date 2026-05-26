.PHONY: dev-backend dev-frontend install test lint format migrate docker-up docker-down

# ── Dev ───────────────────────────────────────────────────────────────────────
dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# Run both in parallel (requires make 4.x or use two terminals)
dev:
	make -j2 dev-backend dev-frontend

# ── Install ───────────────────────────────────────────────────────────────────
install:
	cd backend && uv sync && uv run pre-commit install
	cd frontend && npm install

# ── Test ──────────────────────────────────────────────────────────────────────
test:
	cd backend && uv run pytest tests/ -v --cov=app --cov=ai_pipeline --cov-report=term-missing

test-unit:
	cd backend && uv run pytest tests/unit/ -v

test-integration:
	cd backend && uv run pytest tests/integration/ -v

# ── Lint & Format ─────────────────────────────────────────────────────────────
lint:
	cd backend && uv run ruff check . && uv run mypy app/ ai_pipeline/
	cd frontend && npm run lint

format:
	cd backend && uv run ruff format . && uv run ruff check --fix .

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	cd backend && uv run alembic upgrade head

migrate-create:
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

migrate-down:
	cd backend && uv run alembic downgrade -1

# ── Docker ────────────────────────────────────────────────────────────────────
docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-rebuild:
	docker compose up -d --build
