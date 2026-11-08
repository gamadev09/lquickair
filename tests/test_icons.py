"""Icon resources and desktop integration without a running display."""
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from lquickair.desktop.gtk import Gio
from lquickair.desktop.icons import (
    APPLICATION_ID, asset_path, install_desktop_entry, notification_icon,
)


class IconTests(unittest.TestCase):
    def test_both_exported_svg_assets_are_packaged(self):
        self.assertEqual(ET.parse(asset_path()).getroot().get('viewBox'), '0 0 1080 1080')
        self.assertEqual(ET.parse(asset_path(symbolic=True)).getroot().get('viewBox'), '0 0 24 24')
        self.assertNotIn(b'<image', asset_path(symbolic=True).read_bytes())

    def test_notification_embeds_the_grayscale_svg(self):
        icon = notification_icon()
        self.assertIsInstance(icon, Gio.BytesIcon)
        self.assertEqual(icon.get_bytes().get_data(), asset_path(symbolic=True).read_bytes())

    def test_desktop_entry_and_icons_install_to_selected_data_home(self):
        with tempfile.TemporaryDirectory() as directory:
            data_home = Path(directory)
            install_desktop_entry(data_home)
            entry = data_home / 'applications' / f'{APPLICATION_ID}.desktop'
            info = Gio.DesktopAppInfo.new_from_filename(str(entry))
            self.assertIsNotNone(info)
            self.assertEqual(info.get_name(), 'lQuickAir')
            self.assertIn('-m lquickair.desktop', info.get_commandline())
            for symbolic in (False, True):
                source = asset_path(symbolic=symbolic)
                installed = data_home / 'icons/hicolor/scalable/apps' / source.name
                self.assertEqual(installed.read_bytes(), source.read_bytes())
            before = entry.stat().st_mtime_ns
            install_desktop_entry(data_home)
            self.assertEqual(entry.stat().st_mtime_ns, before)
