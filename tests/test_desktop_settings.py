"""Desktop preferences and explicit auto-accept policy."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lquickair.desktop.settings import Settings, validate_name


class SettingsTests(unittest.TestCase):
    def test_preferences_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "desktop.json"
            settings = Settings(path)
            settings.name = "My Linux PC"
            settings.auto_accept = True
            settings.remembered_names.add("My Pixel")
            settings.save()
            restored = Settings(path)
            self.assertEqual(restored.name, "My Linux PC")
            self.assertTrue(restored.should_accept("My Pixel", files_only=True))
            self.assertFalse(restored.should_accept("Another phone", files_only=True))
            self.assertFalse(restored.should_accept("My Pixel", files_only=False))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            restored.auto_accept = False
            self.assertFalse(restored.should_accept("My Pixel", files_only=True))

    def test_name_validation_counts_utf8_bytes(self):
        self.assertEqual(validate_name("  My PC  "), "My PC")
        for name in ("", "   ", "PC\nname", "é" * 128):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_name(name)

    def test_corrupt_settings_keep_auto_accept_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "desktop.json"
            path.write_text("not json")
            self.assertFalse(Settings(path).auto_accept)

    def test_legacy_preferences_migrate_without_changing_download_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = Path(directory) / "pyquickshare" / "desktop.json"
            old = Settings(legacy)
            old.name = "My PC"
            old.theme = "dark"
            old.receive_folder = "/tmp/my-received-files"
            old.auto_accept = True
            old.remembered_names.add("My phone")
            old.save()
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory}):
                migrated = Settings()
                self.assertEqual(migrated.name, "My PC")
                self.assertEqual(migrated.theme, "dark")
                self.assertEqual(migrated.receive_folder, old.receive_folder)
                self.assertTrue(migrated.should_accept("My phone", files_only=True))
                migrated.save()
                self.assertEqual(migrated.path.parent.name, "lquickair")
                self.assertTrue(legacy.exists())
                self.assertEqual(Settings().name, "My PC")
