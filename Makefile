.PHONY: sync lint test migration-dry-run build dev-up dev-down check

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

dev-up:
	docker compose up --build --detach --wait

dev-down:
	docker compose down --volumes --remove-orphans

check: lint test migration-dry-run
