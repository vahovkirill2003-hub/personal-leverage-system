"""Compile the full forward-only Alembic chain without touching a database."""

import io
from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    output = io.StringIO()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    if "0005_schema_v03_errata" not in sql:
        raise SystemExit("migration dry-run did not reach the TB-04a head")


if __name__ == "__main__":
    main()
