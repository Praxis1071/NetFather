"""Shared GTK4 page primitives."""
from __future__ import annotations

from gi.repository import Gtk


class BasePage(Gtk.Box):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        if subtitle:
            label = Gtk.Label(label=subtitle, xalign=0, wrap=True)
            label.add_css_class("dim-label")
            self.append(label)

    def cleanup(self) -> None:
        """Release page-owned subscriptions, timers, and background hooks."""
        return None


def section(title: str, child: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    heading = Gtk.Label(label=title, xalign=0)
    heading.add_css_class("heading")
    box.append(heading)
    box.append(child)
    return box
