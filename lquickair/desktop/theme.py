"""Build theme CSS and reuse the installed GTK provider during theme changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import re
from importlib.resources import files

from .gtk import Gdk, Gtk

if TYPE_CHECKING:
    from .application import LQuickAir

DARK_PALETTE = {
    "#f5f7fb": "#111722",
    "#17243b": "#edf2fa",
    "#5d6c82": "#a8b6cb",
    "#ffffff": "#1a2332",
    "#dce4ef": "#303d51",
    "#c6d2e3": "#465775",
    "#edf3fc": "#354864",
    "#2563eb": "#8cb9ff",
    "#1d4ed8": "#adceff",
    "#edf1f7": "#222e40",
    "#718096": "#8290a6",
    "#dbeafe": "#304b70",
    "#eff5ff": "#253750",
    "#eaf1fc": "#192538",
    "#b6c3d5": "#45536a",
}


def stylesheet(theme: str) -> str:
    """Return the scoped stylesheet for the selected appearance."""
    css = files(__package__).joinpath("style.css").read_text(encoding="utf-8")
    if theme == "dark":
        css = re.sub(r"#[0-9a-f]{6}", lambda match: DARK_PALETTE.get(match[0], match[0]), css)
        css += ".lquickair-content switch slider { background: #f1f5fb; }"
    return css


def install_style(app: LQuickAir) -> None:
    """Load the selected theme without replacing an existing display provider."""
    provider = getattr(app: LQuickAir, "style_provider", None)
    is_new_provider = provider is None
    if is_new_provider:
        provider = Gtk.CssProvider()
    provider.load_from_data(stylesheet(app.settings.theme).encode())
    if is_new_provider:
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER + 1,
        )
    app.style_provider = provider
