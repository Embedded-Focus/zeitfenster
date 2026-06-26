SERVICE_CREDS   ?= .env
.DEFAULT_GOAL   := help

.PHONY: help install test lint up down logs sops-edit sops-decrypt sops-encrypt sops-updatekeys

install: ## Install dependencies
	uv sync

test: ## Run tests
	uv run pytest

lint: ## Run linter
	uv run ruff check src/ tests/

up: ## Start demo environment
	docker compose up --build -d

down: ## Stop demo environment
	docker compose down

logs: ## Follow demo environment logs
	docker compose logs -f

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

sops-edit: ## Edit a SOPS-encrypted file
	sops edit $(SERVICE_CREDS)

sops-decrypt: ## Decrypt a SOPS file in-place
	sops --decrypt --in-place $(SERVICE_CREDS)

sops-encrypt: ## Encrypt a file in-place with SOPS
	sops --encrypt --in-place $(SERVICE_CREDS)

sops-updatekeys: ## Update SOPS encryption keys
	sops updatekeys --yes $(SERVICE_CREDS)
