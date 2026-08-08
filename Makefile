.PHONY: sync lint test migration-dry-run build check

sync:
	uv sync --frozen

lint:
	uv run --frozen ruff check src tests scripts
	uv run --frozen ruff format --check src tests scripts

test:
	uv run --frozen pytest

migration-dry-run:
	uv run --frozen python scripts/migration_dry_run.py

build:
	docker build --iidfile .image-id -t pls:local .

check: lint test migration-dry-run

