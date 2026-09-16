"""GTK4 profile management workspace."""
from __future__ import annotations

from gi.repository import Gtk

from core.database import Database
from gui.tasks import BackgroundTaskRunner
from manager.device_manager import DeviceManager
from manager.profile_manager import ProfileManager


MODES = ("unrestricted", "controlled", "blocked")


class ProfilesPage(Gtk.Box):
    """Manage device-bound access profiles through GTK4."""

    def __init__(self, database: Database, tasks: BackgroundTaskRunner) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(28)
        self.set_margin_bottom(28)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.profile_manager = ProfileManager(database)
        self.device_manager = DeviceManager(database)
        self.tasks = tasks
        self._busy = False

        heading = Gtk.Label(label="Profiles", xalign=0)
        heading.add_css_class("title-1")
        self.append(heading)
        subtitle = Gtk.Label(
            label="Assign an access mode to a managed device. Profiles are enforced by the policy layer.",
            xalign=0,
            wrap=True,
        )
        subtitle.add_css_class("dim-label")
        self.append(subtitle)

        form = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.device = Gtk.DropDown.new_from_strings(["Loading devices..."])
        self.device.set_hexpand(True)
        self.name_entry = Gtk.Entry(placeholder_text="Profile name")
        self.name_entry.set_hexpand(True)
        self.mode = Gtk.DropDown.new_from_strings(list(MODES))
        self.create_button = Gtk.Button(label="Create profile")
        self.create_button.add_css_class("suggested-action")
        self.create_button.connect("clicked", lambda _button: self.create_profile())
        form.append(self.device)
        form.append(self.name_entry)
        form.append(self.mode)
        form.append(self.create_button)
        self.append(form)

        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.connect("clicked", lambda _button: self.refresh())
        self.append(self.refresh_button)

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
        self.status.set_text("Loading profiles and devices...")
        self.tasks.submit(self._load, self._loaded, self._failed)

    def _load(self):
        return self.profile_manager.list_profiles(), self.device_manager.list_devices()

    def _loaded(self, result) -> None:
        profiles, devices = result
        self._busy = False
        self.refresh_button.set_sensitive(True)
        self.create_button.set_sensitive(True)
        values = [device.name for device in devices] or ["No devices"]
        self.device.set_model(Gtk.StringList.new(values))
        self.device.set_selected(0)
        while (child := self.list_box.get_first_child()) is not None:
            self.list_box.remove(child)
        for profile in profiles:
            self.list_box.append(self._profile_row(profile))
        self.status.set_text(f"{len(profiles)} profiles | {len(devices)} devices")

    def create_profile(self) -> None:
        selected = self.device.get_selected_item()
        device_name = selected.get_string() if selected else ""
        name = self.name_entry.get_text().strip()
        if not device_name or device_name == "No devices" or not name:
            self.status.set_text("Select a device and enter a profile name.")
            return
        mode = MODES[self.mode.get_selected()]
        self.create_button.set_sensitive(False)
        self.status.set_text("Creating profile...")
        self.tasks.submit(
            lambda: self.profile_manager.create_profile(device_name, name, mode),
            self._created,
            self._failed,
        )

    def _created(self, _profile) -> None:
        self.name_entry.set_text("")
        self.create_button.set_sensitive(True)
        self.status.set_text("Profile created.")
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
        device = getattr(profile, "device", None)
        device_name = device.name if device is not None else "Unknown device"
        info = Gtk.Label(
            label=f"Device: {device_name}  |  Mode: {profile.internet_mode}",
            xalign=0,
        )
        info.add_css_class("dim-label")
        row.append(info)
        return row
