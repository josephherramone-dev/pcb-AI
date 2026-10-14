# Convenience targets for local development. See README.md for details.
.PHONY: up down backend frontend worker test test-backend test-frontend lint e2e migrate

up:            ## full stack in Docker
	docker compose up --build

down:
	docker compose down

backend:       ## API on :8000 (SQLite, in-process jobs by default)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

worker:        ## Celery EDA worker (JOB_BACKEND=celery)
	cd backend && .venv/bin/celery -A app.jobs.celery_app worker --loglevel=INFO

frontend:      ## Next.js dev server on :3000
	cd frontend && npm run dev

migrate:
	cd backend && .venv/bin/alembic upgrade head

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest

test-frontend:
	cd frontend && npm run typecheck && npm test

lint:
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npm run lint

e2e:           ## requires the stack running on :3000
	cd frontend && npx playwright test
