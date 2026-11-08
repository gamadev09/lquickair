"""Dialogs for received content."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .gtk import Gtk
from .widgets import set_margins

if TYPE_CHECKING:
    from .application import LQuickAir


def show_received_text(app: LQuickAir, title: str, text: str) -> None:
    """i display received text in a scrollable popup with a copy action."""
    popup = Gtk.Window(
        title=title or "Received text",
        transient_for=app.window,
        modal=True,
        destroy_with_parent=True,
    )
    popup.add_css_class("lquickair")
    popup.set_opacity(1.0)
    popup.set_default_size(520, 360)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    set_margins(content, 20)
    content.add_css_class("lquickair-content")
    popup.set_child(content)
    heading = Gtk.Label(label=title or "Received text", xalign=0, wrap=True)
    heading.add_css_class("title-2")
    content.append(heading)
    view = Gtk.TextView(editable=False, cursor_visible=False)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_buffer().set_text(text)
    scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
    scroll.set_child(view)
    content.append(scroll)
    actions = Gtk.Box(spacing=12, halign=Gtk.Align.END)
    close = Gtk.Button(label="Close")
    close.add_css_class("app-button")
    close.connect("clicked", lambda _button: popup.close())
    actions.append(close)
    copy = Gtk.Button(label="Copy")
    copy.add_css_class("app-button")
    copy.add_css_class("suggested-action")

    def copy_text(button: Gtk.Button) -> None:
        """i copy the received text to the clipboard and confirm the action."""
        popup.get_clipboard().set(text)
        button.set_label("Copied!")

    copy.connect("clicked", copy_text)
    actions.append(copy)
    content.append(actions)
    popup.present()
