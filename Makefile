# InfraKit developer task runner. Run `make` (or `make help`) to list targets.
# These wrap the same commands documented in CLAUDE.md and CONTRIBUTING.md so
# contributors and CI share one source of truth.

.DEFAULT_GOAL := help
.PHONY: help setup hooks test lint lint-md check build e2e clean

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies into a local venv (uv sync)
	uv sync --extra test

hooks: ## Enable the repo git hooks (.githooks/pre-commit, pre-push)
	git config core.hooksPath .githooks
	@echo "✅ git hooks enabled — pre-commit lints, pre-push runs tests"

test: ## Run the full pytest suite (offline, no network)
	uv run pytest

lint: ## Lint the Python source with ruff
	uvx ruff check src/

lint-md: ## Lint Markdown with markdownlint-cli2 (what CI enforces)
	npx markdownlint-cli2 "**/*.md"

check: lint lint-md test ## Run every gate CI runs: ruff + markdownlint + pytest

build: ## Build the wheel and sdist (templates force-included)
	uv build

e2e: build ## Offline end-to-end init smoke test (mirrors RELEASING.md)
	@rm -rf .e2e-demo
	uv run infrakit init .e2e-demo --ai claude --iac terraform --script sh --no-git --ignore-agent-tools
	@test -f .e2e-demo/.claude/commands/infrakit:setup.md && echo "✅ e2e: init rendered commands" || (echo "❌ e2e: missing rendered command" && exit 1)
	@rm -rf .e2e-demo

clean: ## Remove build artifacts and caches
	rm -rf dist build *.egg-info .pytest_cache .e2e-demo
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
