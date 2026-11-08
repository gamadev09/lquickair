"""Persistent preferences and the explicit remembered-name acceptance policy."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

MAX_DEVICE_NAME_BYTES = 255
CONTROL_CHARACTER_LIMIT = 32


def default_receive_folder() -> Path:
    """Return the destination used before the user chooses another folder."""
    return Path.home() / "Downloads" / "lquickair"


def validate_name(name: str) -> str:
    """Validate the UTF-8 name length used by the discovery protocol."""
    name = name.strip()
    contains_control_character = any(ord(character) < CONTROL_CHARACTER_LIMIT for character in name)
    if not name or len(name.encode("utf-8")) > MAX_DEVICE_NAME_BYTES or contains_control_character:
        message = "Use a device name of 1-255 UTF-8 bytes, without control characters."
        raise ValueError(message)
    return name


class Settings:
    """Load user preferences, falling back to the upstream app's legacy location."""

    def __init__(self, path: Path | None = None) -> None:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.path = path if path is not None else config_home / "lquickair" / "desktop.json"
        self.name = socket.gethostname()[:60] or "Linux PC"
        self.theme = "light"
        self.receive_folder = str(default_receive_folder())
        self.auto_accept = False
        self.remembered_names: set[str] = set()

        source = self.path
        if path is None and not source.exists():
            legacy = config_home / "pyquickshare" / "desktop.json"
            if legacy.exists():
                source = legacy
        self._load(source)

    def _load(self, source: Path) -> None:
        """Keep defaults when the file or its contents cannot be read."""
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            name = validate_name(data.get("name", self.name))
        except (OSError, ValueError, TypeError, AttributeError):
            return

        self.name = name
        theme = data.get("theme")
        self.theme = theme if theme in ("light", "dark") else "light"
        folder = data.get("receive_folder")
        if isinstance(folder, str) and folder and Path(folder).is_absolute():
            self.receive_folder = folder
        self.auto_accept = data.get("auto_accept") is True
        names = data.get("remembered_names", [])
        if isinstance(names, list):
            self.remembered_names = {name for name in names if isinstance(name, str) and name}

    def save(self) -> None:
        """Replace the settings file atomically and keep it private to the user."""
        data = {
            "name": validate_name(self.name),
            "auto_accept": self.auto_accept,
            "theme": self.theme,
            "receive_folder": self.receive_folder,
            "remembered_names": sorted(self.remembered_names),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def should_accept(self, sender: str, *, files_only: bool) -> bool:
        """Match remembered names only for files and only after explicit opt-in."""
        return self.auto_accept and files_only and sender in self.remembered_names
