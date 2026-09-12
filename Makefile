.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest
RUFF    := $(VENV)/bin/ruff
MYPY    := $(VENV)/bin/mypy
LOCUST  := $(VENV)/bin/locust
ALEMBIC := $(VENV)/bin/alembic

# Each service package lives under its own directory, so tests and local runs
# need all four on the path.
export PYTHONPATH := services/ticket-receiver:services/rag-engine:services/agent:services/dispatcher

SERVICES := ticket-receiver rag-engine agent dispatcher

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------

.PHONY: setup
setup: ## Create the virtualenv and install everything (Python 3.11)
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt
	$(PIP) install -e libs/support_common
	@test -f .env || cp .env.example .env
	@echo "Done. Next: make infra && make kb"

.PHONY: env
env: ## Copy .env.example to .env if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env")

# --- Infrastructure ----------------------------------------------------------

.PHONY: infra
infra: ## Start Postgres and Redis only
	docker compose up -d postgres redis
	@echo "Postgres on $$(docker compose port postgres 5432), Redis on $$(docker compose port redis 6379)"

.PHONY: up
up: ## Build and start the whole stack
	docker compose up -d --build

.PHONY: down
down: ## Stop the stack (keeps volumes)
	docker compose down

.PHONY: clean
clean: ## Stop the stack and delete all data
	docker compose down -v
	rm -rf data/chroma

.PHONY: logs
logs: ## Follow the logs of every service
	docker compose logs -f --tail=100

.PHONY: ps
ps: ## Show container status
	docker compose ps

# --- Data --------------------------------------------------------------------

.PHONY: kb
kb: ## Generate the knowledge base and index it into the vector store
	$(PY) scripts/generate_kb.py
	$(PY) scripts/seed_kb.py --reset

.PHONY: kb-generate
kb-generate: ## Regenerate the markdown corpus only (no indexing)
	$(PY) scripts/generate_kb.py

.PHONY: kb-check
kb-check: ## Index and run a sample query against the index
	$(PY) scripts/seed_kb.py --check "how do I reset my password"

.PHONY: schema
schema: ## Regenerate database/schema.sql from the ORM models
	$(PY) scripts/export_schema.py

.PHONY: migrate
migrate: ## Apply database migrations
	$(ALEMBIC) -c database/alembic.ini upgrade head

.PHONY: migration
migration: ## Create a migration from model changes (make migration m="add x")
	$(ALEMBIC) -c database/alembic.ini revision --autogenerate -m "$(m)"

.PHONY: seed
seed: ## Create the schema and insert sample tickets
	$(PY) scripts/seed_db.py --tickets 20

# --- Running locally ---------------------------------------------------------

.PHONY: run-receiver
run-receiver: ## Run the ticket receiver with reload (port 8001)
	$(VENV)/bin/uvicorn ticket_receiver.main:app --reload --port 8001

.PHONY: run-rag
run-rag: ## Run the RAG engine with reload (port 8002)
	$(VENV)/bin/uvicorn rag_engine.main:app --reload --port 8002

.PHONY: run-agent
run-agent: ## Run the agent with reload (port 8003)
	$(VENV)/bin/uvicorn agent_service.main:app --reload --port 8003

.PHONY: run-dispatcher
run-dispatcher: ## Run the dispatcher with reload (port 8004)
	$(VENV)/bin/uvicorn dispatcher.main:app --reload --port 8004

.PHONY: ollama
ollama: ## Check Ollama and pull the configured model
	@ollama list >/dev/null 2>&1 || (echo "Ollama is not running - start it with 'ollama serve'" && exit 1)
	@model=$$(grep -E '^OLLAMA_MODEL=' .env 2>/dev/null | cut -d= -f2); \
	 model=$${model:-qwen3:8b}; \
	 echo "Ensuring $$model is available"; ollama pull $$model

# --- Quality -----------------------------------------------------------------

.PHONY: test
test: ## Run every test
	$(PYTEST) -q

.PHONY: test-unit
test-unit: ## Run unit tests only (no infrastructure needed)
	$(PYTEST) tests/unit -q

.PHONY: test-integration
test-integration: ## Run integration tests (needs Postgres)
	$(PYTEST) tests/integration -q

.PHONY: cov
cov: ## Run tests with a coverage report
	$(PYTEST) --cov --cov-report=term-missing --cov-report=html -q
	@echo "HTML report: htmlcov/index.html"

.PHONY: lint
lint: ## Lint and type check
	$(RUFF) check .
	$(RUFF) format --check .
	$(MYPY) libs/support_common/support_common services scripts

.PHONY: fmt
fmt: ## Auto-format and fix what can be fixed
	$(RUFF) check --fix .
	$(RUFF) format .

.PHONY: check
check: lint test ## Lint and test - run this before pushing

# --- Evaluation and load -----------------------------------------------------

.PHONY: eval
eval: ## Measure auto-resolution rate against the labelled ticket set
	$(PY) scripts/evaluate.py

.PHONY: eval-quick
eval-quick: ## Evaluate the first five tickets only
	$(PY) scripts/evaluate.py --limit 5

.PHONY: load
load: ## Load-test ticket ingest (500 users, 3 minutes)
	$(LOCUST) -f tests/load/locustfile.py --host http://localhost:8001 \
	  --tags ingest --users 500 --spawn-rate 50 --run-time 3m --headless --only-summary

.PHONY: load-search
load-search: ## Load-test the RAG engine (200 users, 3 minutes)
	$(LOCUST) -f tests/load/locustfile.py --host http://localhost:8002 \
	  --tags search --users 200 --spawn-rate 20 --run-time 3m --headless --only-summary

.PHONY: monitoring
monitoring: ## Start Prometheus and Grafana (localhost:9090 and :3000)
	docker compose --profile monitoring up -d
	@echo "Prometheus http://localhost:9090   Grafana http://localhost:3000"

# --- Demo --------------------------------------------------------------------

.PHONY: demo
demo: ## Submit one ticket through the running stack and show the result
	@./scripts/demo.sh
