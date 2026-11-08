"""Packaged artwork and Linux desktop icon registration."""

from __future__ import annotations

import os
import sys
from importlib.resources import files
from pathlib import Path

from .gtk import Gdk, Gio, GLib, Gtk

APPLICATION_ID = "io.github.lquickair.Desktop"


def asset_path(*, symbolic: bool = False) -> Path:
    """Locate the exported vector artwork in the installed package."""
    suffix = "-symbolic" if symbolic else ""
    return Path(str(files(__package__).joinpath("assets", f"{APPLICATION_ID}{suffix}.svg")))


def register_window_icon() -> None:
    """Make the packaged icon available without relying on an installed icon theme."""
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    theme.add_search_path(str(asset_path().parent))
    Gtk.Window.set_default_icon_name(APPLICATION_ID)


def notification_icon() -> Gio.Icon:
    """Embed the grayscale artwork so notification delivery needs no source path."""
    return Gio.BytesIcon.new(GLib.Bytes.new(asset_path(symbolic=True).read_bytes()))


def install_desktop_entry(data_home: Path | None = None) -> None:
    """Register this Python installation with the user's application launcher."""
    if data_home is None:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    for symbolic in (False, True):
        source = asset_path(symbolic=symbolic)
        destination = data_home / "icons" / "hicolor" / "scalable" / "apps" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        contents = source.read_bytes()
        if not destination.exists() or destination.read_bytes() != contents:
            destination.write_bytes(contents)

    # Desktop-entry Exec has its own quoting rules; this is not a shell command.
    executable = "".join("\\" + char if char in '\\"`$' else char for char in sys.executable)
    entry = (
        "[Desktop Entry]\nType=Application\nName=lQuickAir\n"
        "Comment=Send and receive files with nearby devices\n"
        f'Exec="{executable}" -m lquickair.desktop\n'
        f"Icon={APPLICATION_ID}\nStartupWMClass={APPLICATION_ID}\n"
        "Terminal=false\nCategories=Network;FileTransfer;\nStartupNotify=true\n"
    )
    destination = data_home / "applications" / f"{APPLICATION_ID}.desktop"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_text(encoding="utf-8") != entry:
        destination.write_text(entry, encoding="utf-8")
