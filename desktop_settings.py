"""Persistent desktop preferences, independent of GTK and protocol imports."""
import json
import os
from pathlib import Path
import socket


def validate_name(name):
    name = name.strip()
    if not name or len(name.encode('utf-8')) > 255 or any(ord(c) < 32 for c in name):
        raise ValueError('Use a device name of 1–255 UTF-8 bytes, without control characters.')
    return name


class Settings:
    def __init__(self, path=None):
        self.path = path or Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'lquickair' / 'desktop.json'
        self.name = socket.gethostname()[:60] or 'Linux PC'
        self.theme = "light"
        self.receive_folder = str(Path.home() / 'Downloads' / 'lquickair')
        self.auto_accept = False
        self.remembered_names = set()
        source = self.path
        if path is None and not source.exists():
            legacy = source.parent.parent / 'pyquickshare' / 'desktop.json'
            if legacy.exists():
                source = legacy
        try:
            data = json.loads(source.read_text())
            self.name = validate_name(data.get('name', self.name))
            self.theme = data.get('theme', 'light') if data.get('theme') in ('light', 'dark') else 'light'
            folder = data.get('receive_folder')
            if isinstance(folder, str) and folder and Path(folder).is_absolute():
                self.receive_folder = folder
            self.auto_accept = data.get('auto_accept') is True
            self.remembered_names = {name for name in data.get('remembered_names', []) if isinstance(name, str) and name}
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({
            'name': validate_name(self.name),
            'auto_accept': self.auto_accept,
            'theme': self.theme,
            'receive_folder': self.receive_folder,
            'remembered_names': sorted(self.remembered_names),
        }, indent=2) + '\n')
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def should_accept(self, sender, *, files_only):
        return self.auto_accept and files_only and sender in self.remembered_names
