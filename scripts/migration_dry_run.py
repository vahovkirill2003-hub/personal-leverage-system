"""TB-01 migration dry-run placeholder.

Real Alembic migrations are introduced by TB-04. Until then CI verifies that
the repository contains the migrations boundary and that it is import-safe.
"""

from pathlib import Path


def main() -> None:
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    if not migrations_dir.is_dir():
        raise SystemExit("migrations directory is missing")


if __name__ == "__main__":
    main()
