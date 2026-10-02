"""Native GTK light/dark appearance with optional GNOME system preference."""
from __future__ import annotations

from gi.repository import Gdk, Gio, Gtk
from core.appearance import prefers_dark

APP_CSS = """
@define-color window_bg_color @theme_bg_color;
@define-color card_bg_color @theme_base_color;
@define-color view_fg_color @theme_fg_color;
@define-color borders alpha(@theme_fg_color, 0.22);
@define-color accent_bg_color @theme_selected_bg_color;
@define-color accent_color @theme_selected_bg_color;
@define-color success_color mix(@theme_fg_color, #238636, 0.65);
@define-color warning_color mix(@theme_fg_color, #b26b00, 0.65);
@define-color error_color mix(@theme_fg_color, #c01c28, 0.65);

.title-1 { font-size: 24px; font-weight: 700; }
.title-2 { font-size: 20px; font-weight: 600; }
.title-3 { font-size: 16px; font-weight: 600; }
.heading, .caption-heading { font-weight: 600; }
window {
    background: @window_bg_color;
}

.navigation-sidebar {
    padding: 18px 10px;
    background: alpha(@card_bg_color, 0.92);
    border-right: 1px solid alpha(@borders, 0.65);
}

.navigation-sidebar > row {
    min-height: 42px;
    margin: 2px 0;
    border-radius: 9px;
    padding: 0 10px;
}

.navigation-sidebar > row:selected {
    background: alpha(@accent_bg_color, 0.20);
    color: @accent_color;
}

.navigation-sidebar > row:hover:not(:selected) {
    background: alpha(@view_fg_color, 0.06);
}

.sidebar-brand {
    font-size: 20px;
    font-weight: 700;
    margin: 4px 10px 14px;
}

.page-shell {
    background: @window_bg_color;
}

.card {
    border-radius: 12px;
    border: 1px solid alpha(@borders, 0.70);
    background: alpha(@card_bg_color, 0.82);
    padding: 2px;
}

.metric-card {
    min-height: 112px;
}

.status-ok {
    color: @success_color;
}

.status-warning {
    color: @warning_color;
}

.status-error {
    color: @error_color;
}

.mono-value {
    font-family: monospace;
}
"""


class ThemeController:
    def __init__(self) -> None:
        self.mode = "system"
        self.settings = Gtk.Settings.get_default()
        self._native_dark = bool(self.settings.get_property("gtk-application-prefer-dark-theme")) if self.settings else False
        self.desktop = None
        self._desktop_handler = None
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup("org.gnome.desktop.interface", True) if source else None
        if schema and schema.has_key("color-scheme"):
            self.desktop = Gio.Settings.new_full(schema, None, None)
            self._desktop_handler = self.desktop.connect("changed::color-scheme", self._system_changed)
        display = Gdk.Display.get_default()
        if display is not None:
            self.provider = Gtk.CssProvider()
            self.provider.load_from_data(APP_CSS.encode("utf-8"))
            Gtk.StyleContext.add_provider_for_display(display, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _system_dark(self) -> bool:
        if self.desktop:
            value = self.desktop.get_string("color-scheme")
            if value in {"prefer-dark", "prefer-light"}:
                return value == "prefer-dark"
        return self._native_dark

    def apply(self, theme: str) -> None:
        dark = prefers_dark(theme, self._system_dark())
        self.mode = theme
        if self.settings is not None:
            self.settings.set_property("gtk-application-prefer-dark-theme", dark)

    def _system_changed(self, *_args) -> None:
        if self.mode == "system":
            self.apply("system")

    def cleanup(self) -> None:
        if self.desktop is not None and self._desktop_handler is not None:
            self.desktop.disconnect(self._desktop_handler)
            self._desktop_handler = None
