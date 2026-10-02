"""NetFather GTK4 Linux desktop application."""

__all__ = ["NetFatherApplication", "main"]


def __getattr__(name: str):
    """Keep state and translation consumers independent of GTK imports."""
    if name in __all__:
        from gui.app import NetFatherApplication, main

        return {"NetFatherApplication": NetFatherApplication, "main": main}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
