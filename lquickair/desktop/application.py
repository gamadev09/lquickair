"""GTK application lifecycle, event dispatch, and user actions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .dialogs import show_received_text
from .gtk import Gdk, Gio, GLib, Gtk
from .icons import (
    APPLICATION_ID,
    install_desktop_entry,
    notification_icon,
    register_window_icon,
)
from .settings import Settings, validate_name
from .theme import install_style
from .views import build_window
from .widgets import set_margins
from .worker import TransferWorker


class LQuickAir(Gtk.Application):
    """Own desktop state and route UI actions to the transfer worker."""

    def __init__(self) -> None:
        """i initialize the lquickair state and its required resources."""
        super().__init__(application_id=APPLICATION_ID)
        self.settings = Settings()
        self.backend = None
        self.rows = {}
        self.files = []
        self.transfer = None
        self.receiver = None
        self.dialogs = []

    def do_activate(self) -> None:
        """i present the window and start discovery when the application opens."""
        if self.props.active_window:
            self.props.active_window.present()
            return
        self.install_style()
        register_window_icon()
        build_window(self)
        self.window.present()
        self.backend = TransferWorker(self.emit)
        self.backend.submit(self.backend.discover())

    def close(self, _window: Gtk.Window) -> bool:
        """i stop the active operations before closing the application."""
        if self.backend:
            self.backend.close()
        return False

    def emit(self, event: str, value: Any) -> None:
        """i queue a worker event for processing on the gtk main thread."""
        GLib.idle_add(self.handle_event, event, value)

    def handle_event(self, event: str, value: Any) -> bool:
        """i dispatch worker events on the gtk main thread."""
        if event == "device":
            self.add_device(value)
        elif event == "ready":
            self.show_capabilities(value)
        elif event == "text":
            self.show_received_text(*value)
        elif event == "request":
            self.notify("Incoming share", f"{value[1]} wants to share with you.", "incoming-share")
            self.show_share_request(value)
        elif event == "received":
            self.notify("Share received", str(value), "received-share")
        else:
            self.show_operation_status(event, value)
        return GLib.SOURCE_REMOVE

    def notify(self, title: str, body: str, identifier: str) -> None:
        """i show the desktop notification only when the main window is unfocused."""
        if self.window.is_active():
            return
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(notification_icon())
        self.send_notification(identifier, notification)

    def add_device(self, value: tuple[str, str]) -> None:
        """i add a newly discovered recipient without duplicating its transport entry."""
        if value not in self.rows:
            row = Gtk.ListBoxRow()
            row.device_key = value
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            set_margins(content, 12)
            content.append(Gtk.Label(label=value[0], xalign=0))
            transport = Gtk.Label(label=value[1], xalign=0)
            transport.add_css_class("dim-label")
            content.append(transport)
            row.set_child(content)
            self.devices.append(row)
            self.rows[value] = row
            self.device_heading.set_text(f"Nearby devices · {len(self.rows)}")

    def show_capabilities(self, value: Any) -> None:
        """i display the bluetooth and network features reported by the worker."""
        self.capabilities.set_text(
            f"Bluetooth: {'available' if value.bluetooth else 'unavailable'} · "
            f"Wi-Fi Direct: {'available' if value.network_manager else 'unavailable'}"
        )

    def show_share_request(self, value: Any) -> None:
        """i request approval unless the remembered-name file policy permits acceptance."""
        key, sender, pin, names, files_only = value
        if self.settings.should_accept(sender, files_only=files_only):
            self.backend.submit(self.backend.respond(key, accept=True))
            self.status.set_text(f"Automatically accepting files from {sender}.")
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            text=f"Incoming share from {sender}",
            secondary_text=f"{', '.join(names)}\n\nConfirm this code matches your phone: {pin}",
        )
        dialog.add_css_class("lquickair")
        dialog.get_content_area().add_css_class("lquickair-content")
        dialog.set_opacity(1.0)
        dialog.add_button("Decline", Gtk.ResponseType.CANCEL)
        dialog.add_button("Accept", Gtk.ResponseType.ACCEPT)
        for response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.ACCEPT):
            dialog.get_widget_for_response(response).add_css_class("app-button")
        dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT).add_css_class("suggested-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        remember = Gtk.CheckButton(label="Remember this name for automatic file acceptance")
        remember.set_active(sender in self.settings.remembered_names)
        remember.set_sensitive(files_only)
        dialog.get_message_area().append(remember)

        def respond(dialog: Gtk.MessageDialog, response: int) -> None:
            """i apply the consent decision and report the received results."""
            accepted = response == Gtk.ResponseType.ACCEPT
            if accepted and files_only:
                previous = set(self.settings.remembered_names)
                if remember.get_active():
                    self.settings.remembered_names.add(sender)
                else:
                    self.settings.remembered_names.discard(sender)
                try:
                    self.settings.save()
                except OSError as error:
                    self.settings.remembered_names = previous
                    self.status.set_text(f"Could not save remembered device: {error}")
                self.update_remembered()
            self.backend.submit(self.backend.respond(key, accept=accepted))
            self.dialogs.remove(dialog)
            dialog.destroy()

        dialog.connect("response", respond)
        self.dialogs.append(dialog)
        dialog.present()

    def show_operation_status(self, event: str, value: Any) -> None:
        """i display the operation result and restore the transfer controls."""
        self.status.set_text(
            ("Could not complete operation: " if event == "error" else "") + str(value)
        )
        if event == "error":
            self.capabilities.set_text(
                "Check Bluetooth, system dependencies, and the terminal log."
            )
        if event in ("sent", "error"):
            self.cancel_button.set_sensitive(False)
            self.update_send()

    def choose_files(self, _button: Gtk.Button) -> None:
        """i open the file picker and retain the selected local files."""
        chooser = Gtk.FileChooserNative(
            title="Choose files to share",
            transient_for=self.window,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.set_select_multiple(True)

        def selected(dialog: Gtk.FileChooserNative, response: int) -> None:
            """i apply the local picker selection and close the picker."""
            if response == Gtk.ResponseType.ACCEPT:
                model = dialog.get_files()
                self.files = [model.get_item(i).get_path() for i in range(model.get_n_items())]
                self.files = [file for file in self.files if file and Path(file).is_file()]
                self.selection.set_text(
                    ", ".join(Path(file).name for file in self.files) or "No files selected"
                )
                self.update_send()
            dialog.destroy()

        chooser.connect("response", selected)
        chooser.show()

    def update_send(self) -> None:
        """i enable sending only when files and a recipient are selected and no send is active."""
        busy = self.transfer is not None and not self.transfer.done()
        self.send_button.set_sensitive(
            bool(self.files and self.devices.get_selected_row() and not busy)
        )

    def send_files(self, _button: Gtk.Button) -> None:
        """i submit the selected files and recipient to the transfer worker."""
        row = self.devices.get_selected_row()
        if row and self.files:
            self.transfer = self.backend.submit(
                self.backend.send(row.device_key, list(self.files), self.settings.name)
            )
            self.transfer.add_done_callback(lambda _: GLib.idle_add(self.update_send))
            self.send_button.set_sensitive(False)
            self.cancel_button.set_sensitive(True)

    def cancel_send(self, _button: Gtk.Button) -> None:
        """i cancel the active send and update the transfer controls."""
        if self.transfer:
            self.transfer.cancel()
        self.cancel_button.set_sensitive(False)
        self.status.set_text("Send cancelled.")

    def toggle_receive(self, switch: Gtk.Switch, _param: object) -> None:
        """i start or stop receiving according to the switch state."""
        if switch.get_active():
            self.receiver = self.backend.submit(
                self.backend.receive(self.settings.name, self.settings.receive_folder)
            )
            self.status.set_text(f"Receiving enabled. Select {self.settings.name} on your phone.")
        elif self.receiver:
            self.status.set_text("Receiving disabled.")
            self.receiver.cancel()
            for key in list(self.backend.requests):
                self.backend.submit(self.backend.respond(key, accept=False))
            for dialog in self.dialogs[:]:
                self.dialogs.remove(dialog)
                dialog.destroy()

    def show_received_text(self, title: str, text: str) -> None:
        """i display received text in a scrollable popup with a copy action."""
        show_received_text(self, title, text)

    def change_theme(self, selector: Gtk.Switch, _param: object) -> None:
        """i save the selected appearance and defer its application until the signal finishes."""
        previous = self.settings.theme
        selected_theme = "dark" if selector.get_active() else "light"
        if selected_theme == previous:
            return
        self.settings.theme = selected_theme
        try:
            self.settings.save()
        except OSError as error:
            self.settings.theme = previous
            selector.handler_block(self.theme_handler)
            selector.set_active(previous == "dark")
            selector.handler_unblock(self.theme_handler)
            self.status.set_text(f"Could not save theme: {error}")
            return
        # Apply after the control's notification finishes; avoid restyling a
        # mapped dropdown popup or replacing display-wide providers mid-signal.
        if not getattr(self, "_theme_update_pending", False):
            self._theme_update_pending = True
            GLib.idle_add(self.apply_theme)

    def apply_theme(self) -> bool:
        """i apply the latest queued appearance once on the main loop."""
        self._theme_update_pending = False
        self.install_style()
        return GLib.SOURCE_REMOVE

    def install_style(self) -> None:
        """i apply the selected appearance while reusing the existing style provider."""
        install_style(self)

    def update_receive_location(self) -> None:
        """i display the folder used for incoming files."""
        self.receive_location.set_text(
            f"Saved to {self.settings.receive_folder} · Network connection required"
        )

    def choose_receive_folder(self, _button: Gtk.Button) -> None:
        """i open the folder picker and save the selected destination."""
        chooser = Gtk.FileChooserNative(
            title="Save received files to",
            transient_for=self.window,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label="Select folder",
            cancel_label="Cancel",
        )
        chooser.set_current_folder(Gio.File.new_for_path(self.settings.receive_folder))

        def selected(dialog: Gtk.FileChooserNative, response: int) -> None:
            """i apply the local picker selection and close the picker."""
            if response == Gtk.ResponseType.ACCEPT:
                folder = dialog.get_file()
                path = folder.get_path() if folder else None
                if path:
                    previous = self.settings.receive_folder
                    try:
                        self.settings.receive_folder = path
                        self.settings.save()
                    except OSError as error:
                        self.settings.receive_folder = previous
                        self.status.set_text(f"Could not save download folder: {error}")
                    else:
                        self.folder_label.set_text(path)
                        self.folder_label.set_tooltip_text(path)
                        self.update_receive_location()
                        if self.receive_switch.get_active():
                            self.receive_switch.set_active(False)
                            self.status.set_text("Folder saved. Enable receiving again to use it.")
                        else:
                            self.status.set_text("Receive folder saved.")
                else:
                    self.status.set_text("Choose a local folder for received files.")
            dialog.destroy()

        chooser.connect("response", selected)
        chooser.show()

    def save_name(self, _button: Gtk.Button) -> None:
        """i validate and save the public name advertised to nearby devices."""
        previous = self.settings.name
        try:
            self.settings.name = validate_name(self.name_entry.get_text())
            self.settings.save()
        except (ValueError, OSError) as error:
            self.settings.name = previous
            self.status.set_text(str(error))
            return
        self.name_entry.set_text(self.settings.name)
        if self.receive_switch.get_active():
            self.receive_switch.set_active(False)
            self.status.set_text("Name saved. Enable receiving again to advertise the new name.")
        else:
            self.status.set_text("PC name saved.")

    def save_auto_accept(self, switch: Gtk.Switch, _param: object) -> None:
        """i save the explicit automatic-acceptance preference and restore it on failure."""
        previous = self.settings.auto_accept
        self.settings.auto_accept = switch.get_active()
        try:
            self.settings.save()
        except OSError as error:
            self.settings.auto_accept = previous
            switch.handler_block(self.auto_handler)
            switch.set_active(previous)
            switch.handler_unblock(self.auto_handler)
            self.status.set_text(f"Could not save preference: {error}")

    def update_remembered(self) -> None:
        """i display the names currently remembered for file acceptance."""
        names = ", ".join(sorted(self.settings.remembered_names)) or "None"
        self.remembered_label.set_text(f"Remembered names: {names}")

    def forget_devices(self, _button: Gtk.Button) -> None:
        """i clear remembered names and restore them if saving fails."""
        previous = set(self.settings.remembered_names)
        self.settings.remembered_names.clear()
        try:
            self.settings.save()
        except OSError as error:
            self.settings.remembered_names = previous
            self.status.set_text(f"Could not forget devices: {error}")
        self.update_remembered()


def main() -> int:
    """i start the desktop app from a desktop session."""
    logging.basicConfig(level=logging.INFO)
    if not Gtk.init_check() or Gdk.Display.get_default() is None:
        message = "Cannot open the display. Run lQuickAir from your Linux desktop session."
        raise SystemExit(message)
    try:
        install_desktop_entry()
    except OSError:
        logging.getLogger(__name__).warning(
            "Could not register the desktop launcher", exc_info=True
        )
    return LQuickAir().run(None)
