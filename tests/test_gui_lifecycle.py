"""Regression tests for GTK page timer and cleanup lifecycles.

These AST-based tests intentionally do not import GTK, so they also run in
minimal CI environments where PyGObject is unavailable.
"""
from __future__ import annotations

import ast
from pathlib import Path


GUI_DIR = Path(__file__).resolve().parents[1] / "gui"
TIMER_FUNCTIONS = {"timeout_add", "timeout_add_seconds", "timeout_add_full"}


def _page_classes(path: Path) -> list[ast.ClassDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def test_glib_timer_callbacks_exist_on_the_owning_class() -> None:
    """Every self-bound GLib timer callback must resolve to a class method."""
    checked = 0
    for path in sorted(GUI_DIR.glob("*_page.py")):
        for cls in _page_classes(path):
            methods = {
                node.name
                for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for node in ast.walk(cls):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr in TIMER_FUNCTIONS
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "GLib"
                ):
                    continue
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Attribute)
                        and isinstance(arg.value, ast.Name)
                        and arg.value.id == "self"
                    ):
                        assert arg.attr in methods, (
                            f"{path.relative_to(GUI_DIR.parent)}:"
                            f"{getattr(node, 'lineno', '?')} references missing "
                            f"timer callback {cls.name}.{arg.attr}"
                        )
                        checked += 1
    assert checked > 0, "Expected to inspect at least one GLib timer callback"


def test_page_cleanup_methods_do_not_return_timer_continuation_values() -> None:
    """cleanup() must stop resources, not return GLib timer continuation flags."""
    for path in sorted(GUI_DIR.glob("*_page.py")):
        for cls in _page_classes(path):
            for node in cls.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name != "cleanup":
                    continue
                for child in ast.walk(node):
                    if not isinstance(child, ast.Return) or child.value is None:
                        continue
                    value = child.value
                    if (
                        isinstance(value, ast.Attribute)
                        and isinstance(value.value, ast.Name)
                        and value.value.id == "GLib"
                        and value.attr in {"SOURCE_CONTINUE", "SOURCE_REMOVE"}
                    ):
                        raise AssertionError(
                            f"{path.relative_to(GUI_DIR.parent)}:{child.lineno}: "
                            "cleanup() must not return GLib timer source flags"
                        )



def test_pages_with_glib_timers_implement_cleanup() -> None:
    """A page that creates GLib timers must release them on window close."""
    for path in sorted(GUI_DIR.glob("*_page.py")):
        for cls in _page_classes(path):
            has_timer = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in TIMER_FUNCTIONS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "GLib"
                for node in ast.walk(cls)
            )
            if has_timer:
                methods = {
                    node.name
                    for node in cls.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                assert "cleanup" in methods, (
                    f"{path.relative_to(GUI_DIR.parent)}: "
                    f"{cls.name} creates a GLib timer but has no cleanup()"
                )
