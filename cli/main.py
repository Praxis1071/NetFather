"""NetFather CLI çalıştırma noktası."""

from __future__ import annotations

from cli.commands import app


def run() -> None:
    """Typer uygulamasını başlatır."""
    app()


if __name__ == "__main__":
    run()
