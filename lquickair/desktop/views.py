"""Window layout and section builders; application callbacks own behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .gtk import Gtk, Pango
from .widgets import card, label, set_margins

if TYPE_CHECKING:
    from .application import LQuickAir


def build_window(app: LQuickAir) -> None:
    app.window = Gtk.ApplicationWindow(application=app, title="lQuickAir")
    app.window.add_css_class("lquickair")
    app.window.set_opacity(1.0)
    app.window.set_default_size(720, 800)
    app.window.connect("close-request", app.close)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    set_margins(box, 24)
    page = Gtk.ScrolledWindow()
    page.add_css_class("lquickair-content")
    page.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    page.set_child(box)
    app.window.set_child(page)

    hero = Gtk.Box(spacing=16)
    introduction = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    title = label("Share something nearby")
    title.add_css_class("hero-title")
    introduction.append(title)
    introduction.append(label("Share files with nearby Android devices.", muted=True))
    introduction.set_hexpand(True)
    hero.append(introduction)
    box.append(hero)
    app.capabilities = label("Checking Bluetooth and network support…", muted=True)
    box.append(app.capabilities)

    box.append(build_send_section(app: LQuickAir))
    box.append(build_receive_section(app: LQuickAir))
    box.append(build_settings_section(app: LQuickAir))
    app.status = label("")
    app.status.set_visible(False)
    app.status.connect(
        "notify::label",
        lambda label, _param: label.set_visible(bool(label.get_label())),
    )
    app.status.set_selectable(True)
    app.status.add_css_class("status-bar")
    box.append(app.status)


def build_send_section(app: LQuickAir) -> Gtk.Widget:
    send_card = card()
    send_card.append(label("Send files", title=True))
    file_row = Gtk.Box(spacing=12)
    choose = Gtk.Button(label="Choose files…")
    choose.add_css_class("app-button")
    choose.connect("clicked", app.choose_files)
    file_row.append(choose)
    app.selection = Gtk.Label(label="Choose what you want to share", xalign=0, hexpand=True)
    app.selection.set_ellipsize(Pango.EllipsizeMode.END)
    app.selection.add_css_class("muted")
    file_row.append(app.selection)
    send_card.append(file_row)
    app.device_heading = label("Nearby devices", title=True)
    send_card.append(app.device_heading)
    app.devices = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
    app.devices.connect("row-selected", lambda *_: app.update_send())
    empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    empty.set_margin_top(20)
    empty.set_margin_bottom(20)
    empty.append(Gtk.Image.new_from_icon_name("network-wireless-symbolic"))
    empty.append(Gtk.Label(label="Looking for nearby devices…"))
    empty.append(Gtk.Label(label="Open Quick Share → Receive on your phone.", wrap=True))
    app.devices.set_placeholder(empty)
    scroll = Gtk.ScrolledWindow(min_content_height=150, max_content_height=260)
    scroll.set_propagate_natural_height(True)
    scroll.set_child(app.devices)
    send_card.append(scroll)
    actions = Gtk.Box(spacing=12)
    app.send_button = Gtk.Button(label="Send to selected device", sensitive=False, hexpand=True)
    app.send_button.add_css_class("app-button")
    app.send_button.add_css_class("suggested-action")
    app.send_button.connect("clicked", app.send_files)
    actions.append(app.send_button)
    app.cancel_button = Gtk.Button(label="Cancel", sensitive=False)
    app.cancel_button.add_css_class("app-button")
    app.cancel_button.connect("clicked", app.cancel_send)
    actions.append(app.cancel_button)
    send_card.append(actions)
    return send_card


def build_receive_section(app: LQuickAir) -> Gtk.Widget:
    receive_card = card()
    receive_row = Gtk.Box(spacing=12)
    receive_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True)
    receive_copy.append(label("Receive files", title=True))
    receive_copy.append(label("Allow nearby devices to send to this PC.", muted=True))
    receive_row.append(receive_copy)
    app.receive_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
    app.receive_switch.connect("notify::active", app.toggle_receive)
    receive_row.append(app.receive_switch)
    receive_card.append(receive_row)
    app.receive_location = label("", muted=True)
    app.update_receive_location()
    receive_card.append(app.receive_location)
    return receive_card


def build_settings_section(app: LQuickAir) -> Gtk.Widget:
    preferences = Gtk.Expander(label="Settings")
    settings = card()
    settings.add_css_class("lquickair-content")
    theme_row = Gtk.Box(spacing=12)
    theme_label = label("Dark theme", title=True)
    theme_label.set_hexpand(True)
    theme_row.append(theme_label)
    app.theme_selector = Gtk.Switch(
        active=app.settings.theme == "dark",
        valign=Gtk.Align.CENTER,
    )
    app.theme_handler = app.theme_selector.connect("notify::active", app.change_theme)
    theme_row.append(app.theme_selector)
    settings.append(theme_row)
    settings.append(build_identity_preferences(app))
    settings.append(build_receive_folder_preferences(app))
    settings.append(build_acceptance_preferences(app))
    settings.set_margin_top(12)
    preferences.set_child(settings)
    return preferences


def build_identity_preferences(app: LQuickAir) -> Gtk.Box:
    settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    settings.append(label("Your PC name", title=True))
    identity_row = Gtk.Box(spacing=12)
    app.name_entry = Gtk.Entry(text=app.settings.name, hexpand=True)
    app.name_entry.set_placeholder_text("Name shown on nearby devices")
    app.name_entry.set_width_chars(14)
    identity_row.append(app.name_entry)
    save_name = Gtk.Button(label="Save")
    save_name.add_css_class("app-button")
    save_name.connect("clicked", app.save_name)
    identity_row.append(save_name)
    settings.append(identity_row)
    return settings


def build_receive_folder_preferences(app: LQuickAir) -> Gtk.Box:
    settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    settings.append(label("Save received files to", title=True))
    folder_row = Gtk.Box(spacing=12)
    app.folder_label = label(app.settings.receive_folder, muted=True)
    app.folder_label.set_hexpand(True)
    app.folder_label.set_wrap(False)
    app.folder_label.set_max_width_chars(24)
    app.folder_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    app.folder_label.set_tooltip_text(app.settings.receive_folder)
    folder_row.append(app.folder_label)
    choose_folder = Gtk.Button(label="Change…")
    choose_folder.add_css_class("app-button")
    choose_folder.connect("clicked", app.choose_receive_folder)
    folder_row.append(choose_folder)
    settings.append(folder_row)
    return settings


def build_acceptance_preferences(app: LQuickAir) -> Gtk.Box:
    settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    auto_row = Gtk.Box(spacing=12)
    auto_label = label("Auto-accept files from remembered names")
    auto_label.set_hexpand(True)
    auto_label.set_max_width_chars(28)
    auto_row.append(auto_label)
    app.auto_switch = Gtk.Switch(active=app.settings.auto_accept, valign=Gtk.Align.CENTER)
    app.auto_handler = app.auto_switch.connect("notify::active", app.save_auto_accept)
    auto_row.append(app.auto_switch)
    settings.append(auto_row)
    settings.append(label("Names can be copied. Enable only on a network you trust.", muted=True))
    app.remembered_label = label("")
    app.remembered_label.set_max_width_chars(34)
    settings.append(app.remembered_label)
    forget = Gtk.Button(label="Forget remembered devices", halign=Gtk.Align.START)
    forget.add_css_class("app-button")
    forget.connect("clicked", app.forget_devices)
    settings.append(forget)
    app.update_remembered()
    return settings
