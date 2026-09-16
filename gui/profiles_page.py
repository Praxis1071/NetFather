"""GTK4 profile management workspace."""
from __future__ import annotations

from gi.repository import Gtk

from core.database import Database
from gui.tasks import BackgroundTaskRunner
from manager.profile_manager import ProfileManager


class ProfilesPage(Gtk.Box):
    """Manage device access profiles through the GTK4 application."""

    def __init__(self, database: Database, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.database = database
        self.tasks = tasks
        self.manager = ProfileManager(database)
        self._busy = False

        heading = Gtk.Label(label="Profiles", xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        subtitle = Gtk.Label(
            label="Create reusable access policies and assign them to managed devices.",
            xalign=0,
            wrap=True,
        )
        subtitle.add_css_class("dim-label")
        self.append(subtitle)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.connect("clicked", lambda _button: self.refresh())
        toolbar.append(self.refresh_button)
        self.name_entry = Gtk.Entry(placeholder_text="New profile name")
        self.name_entry.set_hexpand(True)
        toolbar.append(self.name_entry)
        self.mode = Gtk.DropDown.new_from_strings(["unrestricted", "controlled", "blocked"])
        toolbar.append(self.mode)
        self.create_button = Gtk.Button(label="Create profile")
        self.create_button.add_css_class("suggested-action")
        self.create_button.connect("clicked", lambda _button: self.create_profile())
        toolbar.append(self.create_button)
        self.append(toolbar)

        self.status = Gtk.Label(label="Ready", xalign=0, wrap=True)
        self.append(self.status)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_vexpand(True)
        self.list_box.add_css_class("boxed-list")
        self.append(self.list_box)
        self.refresh()

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.refresh_button.set_sensitive(False)
        self.create_button.set_sensitive(False)
        self.status.set_text("Loading profiles...")
        self.tasks.submit(self._load, self._loaded, self._failed)

    def _load(self):
        return self.manager.list_profiles()

    def _loaded(self, profiles) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.create_button.set_sensitive(True)
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)
        for profile in profiles:
            self.list_box.append(self._profile_row(profile))
        self.status.set_text(f"{len(profiles)} profiles")

    def create_profile(self) -> None:
        name = self.name_entry.get_text().strip()
        if not name:
            self.status.set_text("Enter a profile name first.")
            return
        mode = ["unrestricted", "controlled", "blocked"][self.mode.get_selected()]
        self.create_button.set_sensitive(False)
        self.status.set_text("Creating profile...")
        self.tasks.submit(
            lambda: self.manager.create_profile(name, mode=mode),
            self._created,
            self._failed,
        )

    def _created(self, _profile) -> None:
        self.name_entry.set_text("")
        self.status.set_text("Profile created.")
        self.create_button.set_sensitive(True)
        self.refresh()

    def _failed(self, error: BaseException) -> None:
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.create_button.set_sensitive(True)
        self.status.set_text(str(error))

    @staticmethod
    def _profile_row(profile) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row.set_margin_top(12)
        row.set_margin_bottom(12)
        row.set_margin_start(14)
        row.set_margin_end(14)
        title = Gtk.Label(label=profile.name, xalign=0)
        title.add_css_class("heading")
        row.append(title)
        devices = len(profile.devices) if hasattr(profile, "devices") else 0
        info = Gtk.Label(
            label=f"Mode: {profile.mode}  |  Devices: {devices}",
            xalign=0,
        )
        info.add_css_class("dim-label")
        row.append(info)
        return row
