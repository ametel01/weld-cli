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

.PHONY: upgrade
upgrade: ## Upgrade all dependencies to latest versions
	@echo -e "$(BLUE)Upgrading dependencies...$(NC)"
	$(UV) lock --upgrade
	$(UV) sync
	@echo -e "$(GREEN)All dependencies upgraded!$(NC)"

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

##@ Documentation

.PHONY: docs
docs: ## Serve documentation locally with hot-reload
	@echo -e "$(BLUE)Starting docs server...$(NC)"
	$(VENV)/bin/mkdocs serve

.PHONY: docs-build
docs-build: ## Build documentation for deployment
	@echo -e "$(BLUE)Building documentation...$(NC)"
	$(VENV)/bin/mkdocs build --strict
	@echo -e "$(GREEN)Docs built to site/$(NC)"

.PHONY: docs-deploy
docs-deploy: ## Deploy documentation to GitHub Pages
	@echo -e "$(BLUE)Deploying to GitHub Pages...$(NC)"
	$(VENV)/bin/mkdocs gh-deploy --force
	@echo -e "$(GREEN)Deployed!$(NC)"

.PHONY: docs-version
docs-version: ## Deploy versioned docs (usage: make docs-version VERSION=0.4.0)
ifndef VERSION
	@echo -e "$(YELLOW)Usage: make docs-version VERSION=x.y.z$(NC)"
	@echo ""
	@echo "This will deploy versioned documentation using mike"
	@echo ""
	@echo "Example:"
	@echo "  make docs-version VERSION=0.4.0"
	@exit 1
else
	@echo -e "$(BLUE)Deploying docs version $(VERSION)...$(NC)"
	$(VENV)/bin/mike deploy --push $(VERSION)
	@echo -e "$(GREEN)Version $(VERSION) deployed!$(NC)"
endif

.PHONY: docs-install
docs-install: ## Install documentation dependencies
	@echo -e "$(BLUE)Installing docs dependencies...$(NC)"
	$(UV) sync --group docs
	@echo -e "$(GREEN)Done!$(NC)"

##@ Build & Package

.PHONY: build
build: ## Build the package
	@echo -e "$(BLUE)Building package...$(NC)"
	$(UV) build
	@echo -e "$(GREEN)Build complete! Check dist/$(NC)"

.PHONY: bin-install
bin-install: ## Install weld globally as a CLI tool (with telegram support)
	@echo -e "$(BLUE)Installing weld globally...$(NC)"
	$(UV) tool uninstall weld 2>/dev/null || true
	$(UV) tool install --force ".[telegram]"
	@echo -e "$(GREEN)weld installed! Run 'weld --help' to verify.$(NC)"

.PHONY: bin-uninstall
bin-uninstall: ## Uninstall weld global CLI tool and clean cache
	@echo -e "$(BLUE)Uninstalling weld...$(NC)"
	$(UV) tool uninstall weld 2>/dev/null || true
	@WELD_BIN=$$(which weld 2>/dev/null); \
	if [ -n "$$WELD_BIN" ]; then \
		echo -e "$(YELLOW)Removing binary at $$WELD_BIN...$(NC)"; \
		rm -f "$$WELD_BIN"; \
	fi
	$(UV) cache clean --force
	@echo -e "$(GREEN)weld uninstalled and cache cleaned.$(NC)"

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
run: ## Run weld CLI (e.g., make run ARGS="list" or make run ARGS="--help")
	-@$(PYTHON) -m weld $(ARGS)

.PHONY: shell
shell: ## Start Python shell with weld imported
	$(PYTHON) -c "from weld import *; import code; code.interact(local=dict(globals(), **locals()))"

.PHONY: watch
watch: ## Run tests in watch mode (requires pytest-watch)
	$(VENV)/bin/ptw -- -v

.PHONY: venv
venv: ## Print command to activate virtual environment
	@echo "Run this command to activate the virtual environment:"
	@echo ""
	@echo "  source $(VENV)/bin/activate"
	@echo ""
	@echo "Or use: eval \$$(make venv-eval)"

.PHONY: venv-eval
venv-eval: ## Output activation command for eval (use: eval $$(make venv-eval))
	@echo "source $(VENV)/bin/activate"

##@ Versioning

# Get current version from pyproject.toml
CURRENT_VERSION := $(shell grep -E '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')

.PHONY: version
version: ## Show current package version
	@echo "Current version: $(CURRENT_VERSION)"

.PHONY: bump
bump: ## Bump version (usage: make bump PART=patch|minor|major)
ifndef PART
	@echo -e "$(YELLOW)Usage: make bump PART=patch|minor|major$(NC)"
	@echo ""
	@echo "Current version: $(CURRENT_VERSION)"
	@echo ""
	@echo "Examples:"
	@echo "  make bump PART=patch  # 0.1.0 -> 0.1.1"
	@echo "  make bump PART=minor  # 0.1.0 -> 0.2.0"
	@echo "  make bump PART=major  # 0.1.0 -> 1.0.0"
	@exit 1
else
	@echo -e "$(BLUE)Bumping $(PART) version...$(NC)"
	@MAJOR=$$(echo $(CURRENT_VERSION) | cut -d. -f1); \
	MINOR=$$(echo $(CURRENT_VERSION) | cut -d. -f2); \
	PATCH=$$(echo $(CURRENT_VERSION) | cut -d. -f3); \
	case "$(PART)" in \
		major) MAJOR=$$((MAJOR + 1)); MINOR=0; PATCH=0 ;; \
		minor) MINOR=$$((MINOR + 1)); PATCH=0 ;; \
		patch) PATCH=$$((PATCH + 1)) ;; \
		*) echo -e "$(YELLOW)Invalid PART: $(PART). Use patch, minor, or major$(NC)"; exit 1 ;; \
	esac; \
	NEW_VERSION="$$MAJOR.$$MINOR.$$PATCH"; \
	echo "$(CURRENT_VERSION) -> $$NEW_VERSION"; \
	sed -i "s/^version = \"$(CURRENT_VERSION)\"/version = \"$$NEW_VERSION\"/" pyproject.toml; \
	sed -i "s/^__version__ = \"$(CURRENT_VERSION)\"/__version__ = \"$$NEW_VERSION\"/" src/weld/__init__.py; \
	echo -e "$(GREEN)Updated version to $$NEW_VERSION$(NC)"; \
	echo ""; \
	$(UV) sync; \
	echo ""; \
	echo "Files modified:"; \
	echo "  - pyproject.toml"; \
	echo "  - src/weld/__init__.py"; \
	echo ""; \
	echo "Don't forget to commit: git commit -am \"Bump version to $$NEW_VERSION\""
endif

.PHONY: bump-patch
bump-patch: ## Bump patch version (0.1.0 -> 0.1.1)
	@$(MAKE) bump PART=patch

.PHONY: bump-minor
bump-minor: ## Bump minor version (0.1.0 -> 0.2.0)
	@$(MAKE) bump PART=minor

.PHONY: bump-major
bump-major: ## Bump major version (0.1.0 -> 1.0.0)
	@$(MAKE) bump PART=major

.PHONY: release
release: ## Create GitHub release from CHANGELOG (usage: make release VERSION=0.2.0)
ifndef VERSION
	@echo -e "$(YELLOW)Usage: make release VERSION=x.y.z$(NC)"
	@echo ""
	@echo "This will create a GitHub release for tag v\$$VERSION"
	@echo "using the corresponding section from CHANGELOG.md"
	@echo ""
	@echo "Example:"
	@echo "  make release VERSION=0.2.0"
	@exit 1
else
	@echo -e "$(BLUE)Creating release v$(VERSION)...$(NC)"
	@if ! grep -q "## \[$(VERSION)\]" CHANGELOG.md; then \
		echo -e "$(YELLOW)Error: Version $(VERSION) not found in CHANGELOG.md$(NC)"; \
		exit 1; \
	fi
	gh release create v$(VERSION) \
		--title "v$(VERSION)" \
		--notes "$$(awk '/^## \[$(VERSION)\]/{flag=1; next} /^## \[/{flag=0} flag' CHANGELOG.md)"
	@echo -e "$(GREEN)Release v$(VERSION) created!$(NC)"
endif

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
