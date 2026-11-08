"""Regression checks for theme updates without mapped dropdowns/provider churn."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gui import LQuickAir, Gtk


class ThemeSwitchTests(unittest.TestCase):
    def test_provider_is_reused_across_theme_changes(self):
        app = SimpleNamespace(settings=SimpleNamespace(theme='light'))
        errors = []
        load = Gtk.CssProvider.load_from_data

        def validate(provider, data):
            provider.connect('parsing-error', lambda _p, _section, error: errors.append(str(error)))
            return load(provider, data)

        with patch.object(Gtk.StyleContext, 'add_provider_for_display') as add, patch.object(
            Gtk.CssProvider, 'load_from_data', validate,
        ):
            LQuickAir.install_style(app)
            original = app.style_provider
            for theme in ('dark', 'light', 'dark'):
                app.settings.theme = theme
                LQuickAir.install_style(app)
                self.assertIs(app.style_provider, original)
            self.assertEqual(add.call_count, 1)
        self.assertEqual(errors, [])

    def test_theme_update_is_deferred_and_coalesced(self):
        app = SimpleNamespace(settings=SimpleNamespace(theme='light', save=lambda: None))
        app.apply_theme = lambda: None
        with patch('gui.GLib.idle_add') as idle:
            LQuickAir.change_theme(app, SimpleNamespace(get_active=lambda: True), None)
            LQuickAir.change_theme(app, SimpleNamespace(get_active=lambda: False), None)
            self.assertEqual(idle.call_count, 1)
            self.assertEqual(app.settings.theme, 'light')
