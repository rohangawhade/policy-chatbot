.PHONY: help install install-backend install-frontend dev dev-backend dev-frontend \
	test test-backend lint lint-backend lint-frontend format format-backend format-frontend \
	typecheck migrate up up-staging up-prod down build seed download-gov-docs pre-commit-install

BACKEND_VENV := backend/.venv/Scripts

help:
	@echo "make install         Install backend + frontend dependencies"
	@echo "make dev             Run backend and frontend dev servers (two terminals)"
	@echo "make dev-backend     Run the FastAPI dev server (uvicorn --reload)"
	@echo "make dev-frontend    Run the Vite dev server"
	@echo "make test            Run backend tests"
	@echo "make lint            Lint backend + frontend"
	@echo "make format          Auto-format backend + frontend"
	@echo "make typecheck       mypy (backend) + tsc --noEmit (frontend)"
	@echo "make migrate         Apply Alembic migrations"
	@echo "make up              docker compose up (all services, dev profile)"
	@echo "make up-staging      docker compose up -d (staging profile, needs .env.staging)"
	@echo "make up-prod         docker compose up -d (production profile, needs .env.production)"
	@echo "make down            docker compose down"
	@echo "make build           docker compose build"
	@echo "make seed            Seed employers/employees/policies + trigger ingestion"
	@echo "make download-gov-docs   Download real government benefits PDFs into data/gov_pdfs/"
	@echo "make pre-commit-install   Install git hooks"

install: install-backend install-frontend

install-backend:
	python -m venv backend/.venv
	$(BACKEND_VENV)/pip.exe install --upgrade pip
	$(BACKEND_VENV)/pip.exe install -e "backend[dev]"

install-frontend:
	cd frontend && npm install

dev:
	@echo "Run 'make dev-backend' and 'make dev-frontend' in separate terminals."

dev-backend:
	cd backend/src && ../.venv/Scripts/uvicorn.exe main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test: test-backend

test-backend:
	cd backend && .venv/Scripts/pytest.exe

lint: lint-backend lint-frontend

lint-backend:
	cd backend && .venv/Scripts/ruff.exe check .
	cd backend && .venv/Scripts/ruff.exe format --check .

lint-frontend:
	cd frontend && npm run lint

format: format-backend format-frontend

format-backend:
	cd backend && .venv/Scripts/ruff.exe check --fix .
	cd backend && .venv/Scripts/ruff.exe format .

format-frontend:
	cd frontend && npm run format

typecheck:
	cd backend && .venv/Scripts/mypy.exe --strict src
	cd frontend && npx tsc --noEmit

migrate:
	cd backend && .venv/Scripts/alembic.exe upgrade head

up:
	docker compose up

up-staging:
	docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d

up-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

down:
	docker compose down

build:
	docker compose build

seed:
	cd backend && .venv/Scripts/python.exe scripts/seed_data.py

download-gov-docs:
	cd backend && .venv/Scripts/python.exe scripts/download_gov_docs.py

pre-commit-install:
	backend/.venv/Scripts/pre-commit.exe install --hook-type pre-commit --hook-type commit-msg
