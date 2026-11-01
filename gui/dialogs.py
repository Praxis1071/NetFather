"""Shared explicit confirmations and accessible form fields."""
from gi.repository import Adw, Gtk
from core.i18n import tr


def confirm(parent, heading, body, action, callback):
    dialog = Adw.MessageDialog.new(parent, heading, body)
    dialog.add_response("cancel", tr("Cancel"))
    dialog.add_response("confirm", action)
    dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")
    dialog.connect("response", lambda _dialog, response: callback() if response == "confirm" else None)
    dialog.present()


def field(label, widget):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    heading = Gtk.Label(label=label, xalign=0)
    heading.set_mnemonic_widget(widget)
    widget.set_tooltip_text(label)
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])
    box.append(heading)
    box.append(widget)
    return box
