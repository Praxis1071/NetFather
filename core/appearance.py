"""Theme preference decisions without importing GTK."""
THEMES = ("system", "light", "dark")


def prefers_dark(theme: str, system_dark: bool) -> bool:
    if theme not in THEMES:
        raise ValueError(f"Unsupported theme: {theme}")
    return system_dark if theme == "system" else theme == "dark"
