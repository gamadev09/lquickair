"""Small reusable GTK widget factories shared by views and dialogs."""

from .gtk import Gtk


def label(text: str, *, muted: bool = False, title: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0, wrap=True)
    if muted:
        label.add_css_class("muted")
    if title:
        label.add_css_class("section-title")
    return label


def card() -> Gtk.Box:
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    card.add_css_class("card")
    return card


def set_margins(widget: Gtk.Widget, margin: int) -> None:
    """Apply equal spacing on all four sides."""
    widget.set_margin_top(margin)
    widget.set_margin_bottom(margin)
    widget.set_margin_start(margin)
    widget.set_margin_end(margin)
