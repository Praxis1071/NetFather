"""Application metadata and credits; all explanatory text is translatable."""
from gi.repository import Gtk

from core.i18n import tr
from core.version import VERSION


class AboutPage(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(14)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        for edge in ("top", "bottom", "start", "end"):
            getattr(card, f"set_margin_{edge}")(12)
        title = Gtk.Label(label="NetFather", xalign=0)
        title.add_css_class("title-2")
        card.append(title)
        card.append(Gtk.Label(label=tr("Version {version}", version=VERSION), xalign=0))
        card.append(Gtk.Label(label=tr("Local-network discovery, monitoring, profiles, scheduling and access management for Linux."), xalign=0, wrap=True))
        card.append(self._heading(tr("Developer")))
        card.append(Gtk.Label(label="Praxis1071", xalign=0))
        card.append(self._link("https://github.com/Praxis1071", tr("Developer GitHub profile")))
        card.append(self._heading(tr("Contributors")))
        card.append(Gtk.Label(label="Cavanşir Qurbanzadə (YoungLion)", xalign=0))
        card.append(self._link("https://github.com/Cavanshirpro", tr("Cavanşir's GitHub profile")))
        card.append(Gtk.Label(label=tr("Theme, language support and discovery/presence improvements."), xalign=0, wrap=True))
        card.append(self._heading(tr("Project and license")))
        card.append(self._link("https://github.com/Praxis1071/NetFather", tr("NetFather repository")))
        card.append(Gtk.Label(label="GPL-3.0-or-later", xalign=0))
        self.append(card)

    @staticmethod
    def _heading(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("heading")
        label.set_margin_top(8)
        return label

    @staticmethod
    def _link(uri: str, text: str) -> Gtk.LinkButton:
        link = Gtk.LinkButton(uri=uri, label=text)
        link.set_halign(Gtk.Align.START)
        return link
