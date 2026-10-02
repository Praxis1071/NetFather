"""Preferences workspace, separate from window composition."""
from __future__ import annotations

from gi.repository import Gtk
from core.config import Config, save_config
from core.i18n import LANGUAGE_NAMES, tr
from core.privileges import detect_privileges
from gui.about_page import AboutPage


class SettingsPage(Gtk.Box):
    def __init__(self, config: Config, app: Gtk.Application) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.append(self._settings_page(config))

    def _appearance_card(self, config: Config) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("card")
        card.append(self._section_title(tr("Appearance and language")))
        status = Gtk.Label(xalign=0, wrap=True)
        status.add_css_class("dim-label")
        choices = (
            ("theme", tr('Theme'), config.ui.theme, (("system", tr("Follow system")), ("light", tr("Light")), ("dark", tr("Dark")))),
            ("language", tr('Language'), config.ui.language, (("system", tr("System language")), *LANGUAGE_NAMES.items())),
        )
        updating = False

        def changed(combo, field):
            nonlocal updating
            if updating:
                return
            value = combo.get_active_id()
            if not value or value == getattr(config.ui, field):
                return
            previous = getattr(config.ui, field)
            setattr(config.ui, field, value)
            try:
                save_config(config)
            except (OSError, ValueError) as exc:
                setattr(config.ui, field, previous)
                updating = True
                try:
                    combo.set_active_id(previous)
                finally:
                    updating = False
                status.set_text(tr("Unable to save preferences: {error}", error=exc))
                return
            if field == "theme":
                self.app.theme.apply(value)
                status.set_text(tr("Theme applied and saved."))
            else:
                status.set_text(tr("Language saved. Restart NetFather to apply it; your open forms are preserved."))

        for field, title, selected, options in choices:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            label = Gtk.Label(label=title, xalign=0, wrap=True)
            label.set_hexpand(True)
            row.append(label)
            combo = Gtk.ComboBoxText()
            for key, name in options:
                combo.append(key, name)
            combo.set_active_id(selected)
            combo.connect("changed", changed, field)
            row.append(combo)
            card.append(row)
        card.append(Gtk.Label(label=tr("Theme changes apply immediately. Language changes apply on the next launch."), xalign=0, wrap=True))
        card.append(status)
        return card

    def _settings_page(self, config: Config) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        page.set_margin_top(28)
        page.set_margin_bottom(28)
        page.set_margin_start(32)
        page.set_margin_end(32)
        title = Gtk.Label(label=tr('Settings'), xalign=0)
        title.add_css_class("title-1")
        page.append(title)
        subtitle = Gtk.Label(label=tr('Configure NetFather and learn more about the application.'), xalign=0, wrap=True)
        subtitle.add_css_class("dim-label")
        page.append(subtitle)
        switcher = Gtk.StackSwitcher()
        switcher.set_halign(Gtk.Align.START)
        switcher.add_css_class("linked")
        page.append(switcher)
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        stack.set_transition_duration(160)
        switcher.set_stack(stack)
        page.append(stack)
        general = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        general.set_margin_top(14)
        general.append(self._section_title(tr('General')))
        general_text = Gtk.Label(label=tr('NetFather continuously watches the Linux neighbor table when live presence monitoring is enabled. Changes trigger a debounced discovery reconciliation so device state stays current without keeping a packet sniffer running.'), xalign=0, wrap=True)
        general_text.add_css_class("dim-label")
        general.append(general_text)
        general.append(self._appearance_card(config))
        general.append(self._live_presence_card(config))
        general.append(self._privilege_card())
        stack.add_titled(general, "general", tr('General'))
        stack.add_titled(AboutPage(), "about", tr('About'))
        stack.set_visible_child_name("general")
        return page

    def _live_presence_card(self, config: Config) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        title = Gtk.Label(label=tr('Live network presence'), xalign=0)
        title.add_css_class("title-2")
        card.append(title)
        description = Gtk.Label(label=tr('Uses Linux neighbor-table notifications as the fast path and periodic hybrid discovery as a safety net. It does not require root and does not run a continuous packet capture.'), xalign=0, wrap=True)
        description.add_css_class("dim-label")
        card.append(description)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        label = Gtk.Label(label=tr('Monitor network presence automatically'), xalign=0)
        label.set_hexpand(True)
        row.append(label)
        enabled = Gtk.Switch()
        enabled.set_active(config.discovery.live_presence_enabled)
        row.append(enabled)
        card.append(row)
        interval_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        interval_label = Gtk.Label(label=tr('Safety discovery interval (seconds)'), xalign=0)
        interval_label.set_hexpand(True)
        interval_row.append(interval_label)
        interval = Gtk.SpinButton.new_with_range(3, 300, 1)
        interval.set_value(config.discovery.live_presence_interval_seconds)
        interval_row.append(interval)
        card.append(interval_row)
        status = Gtk.Label(xalign=0, wrap=True)
        status.add_css_class("dim-label")
        card.append(status)
        updating = False

        def apply_settings(_widget: Gtk.Widget) -> None:
            nonlocal updating
            if updating:
                return
            previous_enabled = config.discovery.live_presence_enabled
            previous_interval = config.discovery.live_presence_interval_seconds
            config.discovery.live_presence_enabled = enabled.get_active()
            config.discovery.live_presence_interval_seconds = int(interval.get_value())
            try:
                save_config(config)
            except (OSError, ValueError) as exc:
                config.discovery.live_presence_enabled = previous_enabled
                config.discovery.live_presence_interval_seconds = previous_interval
                updating = True
                try:
                    enabled.set_active(previous_enabled)
                    interval.set_value(previous_interval)
                finally:
                    updating = False
                status.set_text(tr("Unable to save preferences: {error}", error=exc))
                return
            app = self.app
            service = getattr(app, "live_presence", None)
            if service is not None:
                service.interval_seconds = max(3, config.discovery.live_presence_interval_seconds)
                if config.discovery.live_presence_enabled:
                    service.start()
                    status.set_text(tr('Live presence monitoring is enabled.'))
                else:
                    service.stop()
                    status.set_text(tr('Live presence monitoring is disabled.'))
        enabled.connect("notify::active", lambda *_args: apply_settings(enabled))
        interval.connect("value-changed", apply_settings)
        status.set_text(tr('Enabled') if enabled.get_active() else tr('Disabled'))
        return card

    @staticmethod
    def _privilege_card() -> Gtk.Widget:
        status = detect_privileges()
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        card.set_margin_top(4)
        title = Gtk.Label(label=tr('Network capabilities'), xalign=0)
        title.add_css_class("title-2")
        card.append(title)
        description = Gtk.Label(label=tr('NetFather keeps the GTK interface unprivileged. Elevated access is exposed as a capability for operations that genuinely require it.'), xalign=0, wrap=True)
        description.add_css_class("dim-label")
        card.append(description)
        summary = Gtk.Label(label=tr(status.summary), xalign=0)
        summary.add_css_class("status-ok" if status.can_run_privileged_operations else "status-warning")
        card.append(summary)
        for label, available in (("pkexec", status.pkexec_available), ("nftables", status.nft_available), ("iproute2", status.ip_available), ("NetworkManager", status.network_manager_available)):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            marker = Gtk.Label(label=tr('Available') if available else tr('Unavailable'), xalign=0)
            marker.add_css_class("status-ok" if available else "status-warning")
            name = Gtk.Label(label=label, xalign=0)
            name.set_hexpand(True)
            row.append(name)
            row.append(marker)
            card.append(row)
        note = Gtk.Label(label=tr('Privileged actions will use a narrow system service and polkit authorization instead of relaunching the whole GUI as root.'), xalign=0, wrap=True)
        note.add_css_class("dim-label")
        card.append(note)
        return card

    @staticmethod
    def _section_title(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("title-2")
        return label
