"""Worker process entrypoint."""

from pls.processes.runtime import run_forever


def main() -> None:
    """Run the worker process."""
    run_forever()


if __name__ == "__main__":
    main()
