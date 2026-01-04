# Makefile for weld-cli
# Run 'make help' for available targets

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Directories
SRC_DIR := src/weld
TESTS_DIR := tests
VENV := .venv
PYTHON := $(VENV)/bin/python
UV := uv

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m

##@ Setup

.PHONY: install
install: ## Install dependencies and set up virtual environment
	@echo -e "$(BLUE)Installing dependencies...$(NC)"
	$(UV) sync
	@echo -e "$(GREEN)Done!$(NC)"

.PHONY: install-dev
install-dev: ## Install development dependencies
	@echo -e "$(BLUE)Installing dev dependencies...$(NC)"
	$(UV) sync --group dev
	@echo -e "$(GREEN)Done!$(NC)"

.PHONY: pre-commit-install
pre-commit-install: ## Install pre-commit hooks
	@echo -e "$(BLUE)Installing pre-commit hooks...$(NC)"
	$(VENV)/bin/pre-commit install
	@echo -e "$(GREEN)Done!$(NC)"

.PHONY: setup
setup: install-dev pre-commit-install ## Complete development setup (install + hooks)
	@echo -e "$(GREEN)Development environment ready!$(NC)"

##@ Testing

.PHONY: test
test: ## Run unit tests
	@echo -e "$(BLUE)Running tests...$(NC)"
	$(VENV)/bin/pytest $(TESTS_DIR) -v

.PHONY: test-unit
test-unit: ## Run only unit tests (marked with @pytest.mark.unit)
	@echo -e "$(BLUE)Running unit tests...$(NC)"
	$(VENV)/bin/pytest $(TESTS_DIR) -v -m unit

.PHONY: test-cli
test-cli: ## Run CLI integration tests (marked with @pytest.mark.cli)
	@echo -e "$(BLUE)Running CLI tests...$(NC)"
	$(VENV)/bin/pytest $(TESTS_DIR) -v -m cli

.PHONY: test-slow
test-slow: ## Run slow tests (marked with @pytest.mark.slow)
	@echo -e "$(BLUE)Running slow tests...$(NC)"
	$(VENV)/bin/pytest $(TESTS_DIR) -v -m slow

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	@echo -e "$(BLUE)Running tests with coverage...$(NC)"
	$(VENV)/bin/pytest $(TESTS_DIR) --cov=$(SRC_DIR) --cov-report=term-missing --cov-report=html

.PHONY: test-cov-html
test-cov-html: test-cov ## Run tests with coverage and open HTML report
	@echo -e "$(BLUE)Opening coverage report...$(NC)"
	@xdg-open htmlcov/index.html 2>/dev/null || open htmlcov/index.html 2>/dev/null || echo "Open htmlcov/index.html manually"

.PHONY: test-e2e
test-e2e: ## Run end-to-end tests
	@echo -e "$(BLUE)Running E2E tests...$(NC)"
	bash $(TESTS_DIR)/e2e_test.sh

.PHONY: test-all
test-all: test test-e2e ## Run all tests (unit + e2e)

##@ Code Quality

.PHONY: lint
lint: ## Run ruff linter
	@echo -e "$(BLUE)Running ruff linter...$(NC)"
	$(VENV)/bin/ruff check $(SRC_DIR) $(TESTS_DIR)

.PHONY: lint-fix
lint-fix: ## Run ruff linter with auto-fix
	@echo -e "$(BLUE)Running ruff linter with auto-fix...$(NC)"
	$(VENV)/bin/ruff check $(SRC_DIR) $(TESTS_DIR) --fix

.PHONY: format
format: ## Format code with ruff
	@echo -e "$(BLUE)Formatting code...$(NC)"
	$(VENV)/bin/ruff format $(SRC_DIR) $(TESTS_DIR)

.PHONY: format-check
format-check: ## Check code formatting without changes
	@echo -e "$(BLUE)Checking code formatting...$(NC)"
	$(VENV)/bin/ruff format $(SRC_DIR) $(TESTS_DIR) --check

.PHONY: typecheck
typecheck: ## Run pyright type checker
	@echo -e "$(BLUE)Running type checker...$(NC)"
	$(VENV)/bin/pyright $(SRC_DIR) $(TESTS_DIR)

.PHONY: pre-commit
pre-commit: ## Run all pre-commit hooks on all files
	@echo -e "$(BLUE)Running pre-commit hooks...$(NC)"
	$(VENV)/bin/pre-commit run --all-files

##@ Security

.PHONY: audit
audit: ## Run pip-audit for dependency vulnerabilities
	@echo -e "$(BLUE)Auditing dependencies...$(NC)"
	$(VENV)/bin/pip-audit

.PHONY: secrets
secrets: ## Scan for secrets in codebase
	@echo -e "$(BLUE)Scanning for secrets...$(NC)"
	$(VENV)/bin/detect-secrets scan --all-files

.PHONY: security
security: audit secrets ## Run all security checks

##@ Quality Gates

.PHONY: check
check: lint format-check typecheck ## Run all code quality checks (lint + format + types)

.PHONY: ci
ci: check test-cov security ## Run full CI pipeline (quality + tests + security)

.PHONY: quality
quality: check test security ## Alias for full quality suite

##@ Build & Package

.PHONY: build
build: ## Build the package
	@echo -e "$(BLUE)Building package...$(NC)"
	$(UV) build
	@echo -e "$(GREEN)Build complete! Check dist/$(NC)"

.PHONY: clean
clean: ## Clean build artifacts and caches
	@echo -e "$(BLUE)Cleaning...$(NC)"
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo -e "$(GREEN)Clean!$(NC)"

.PHONY: clean-all
clean-all: clean ## Clean everything including venv
	@echo -e "$(YELLOW)Removing virtual environment...$(NC)"
	rm -rf $(VENV)
	@echo -e "$(GREEN)Fully clean!$(NC)"

##@ Development

.PHONY: run
run: ## Run weld CLI (pass args with ARGS="...")
	$(PYTHON) -m weld $(ARGS)

.PHONY: shell
shell: ## Start Python shell with weld imported
	$(PYTHON) -c "from weld import *; import code; code.interact(local=dict(globals(), **locals()))"

.PHONY: watch
watch: ## Run tests in watch mode (requires pytest-watch)
	$(VENV)/bin/ptw -- -v

##@ Help

.PHONY: help
help: ## Display this help message
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(BLUE)%-15s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
	@echo ""

.PHONY: targets
targets: ## List all targets without descriptions
	@grep -E '^[a-zA-Z_-]+:' $(MAKEFILE_LIST) | cut -d: -f1 | sort | uniq
