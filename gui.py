"""GTK4 desktop frontend. Run with the same Python used to install lquickair."""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import re
from pathlib import Path
import threading

from desktop_settings import Settings, validate_name

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GLib, Gtk


class Backend:
    """Keep asyncio and all protocol objects on one dedicated thread."""

    def __init__(self, emit):
        self.emit = emit
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        self.devices = {}
        self.requests = {}

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.set_exception_handler(
            lambda _loop, context: self.emit('error', str(context.get('exception', context['message'])))
        )
        self.loop.run_forever()

    def submit(self, coroutine):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)

        def completed(result):
            try:
                result.result()
            except (concurrent.futures.CancelledError, asyncio.CancelledError):
                pass
            except ModuleNotFoundError as error:
                self.emit(
                    'error',
                    f"Missing dependency: {error.name}. Close this window and run "
                    "./run-desktop.sh from the project folder to install the desktop environment.",
                )
            except Exception as error:
                logging.exception('lQuickAir operation failed')
                self.emit('error', str(error))
        future.add_done_callback(completed)
        return future

    async def discover(self):
        import lquickair
        from lquickair.send import BluetoothConnectable

        discovery = await lquickair.discover_services()
        self.emit('ready', discovery.facts)
        async for device in discovery:
            if not device.connectable:
                continue
            info = device.endpoint_info
            name = info.name if info and info.name else 'Nearby device'
            medium = 'Bluetooth' if isinstance(device, BluetoothConnectable) else 'Wi-Fi / LAN'
            key = (name, medium)
            self.devices[key] = device
            self.emit('device', key)

    async def send(self, key, files, device_name=None):
        for file in files:
            self.emit('status', f'Sending {Path(file).name} · accept on your phone…')
            if device_name is None:
                await self.devices[key].send(file)
            else:
                await self.devices[key].send(file, device_name=device_name)
        self.emit('sent', 'Send session finished. Check the receiving device for confirmation.')

    async def receive(self, device_name="lQuickAir", output_dir=None):
        import lquickair

        async for request in lquickair.receive(
            output_dir=Path(output_dir) if output_dir else Path.home() / 'Downloads' / 'lquickair',
            device_name=device_name,
        ):
            key = id(request)
            self.requests[key] = request
            self.emit('request', (key, request.sender_name, request.pin, request.names, request.files_only))

    async def respond(self, key, accept):
        from lquickair.results import FileResult, TextResult

        request = self.requests.pop(key)
        if accept:
            self.emit('status', 'Receiving…')
            results = await request.accept()
            summaries = []
            for result in results:
                if isinstance(result, FileResult):
                    summaries.append(f'Saved {result.name}')
                elif isinstance(result, TextResult):
                    self.emit('text', (result.title, result.text))
                    summaries.append('Received text.')
                else:
                    summaries.append(f'Received Wi-Fi credentials for {result.ssid}')
            self.emit('status', '\n'.join(summaries) or 'Transfer ended without receiving files.')
        else:
            await request.reject()
            self.emit('status', 'Incoming transfer declined.')

    async def shutdown(self):
        current = asyncio.current_task()
        tasks = [task for task in asyncio.all_tasks() if task is not current]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def close(self):
        future = asyncio.run_coroutine_threadsafe(self.shutdown(), self.loop)
        future.add_done_callback(lambda _: self.loop.call_soon_threadsafe(self.loop.stop))


class LQuickAir(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.lquickair.Desktop')
        self.settings = Settings()
        self.backend = None
        self.rows = {}
        self.files = []
        self.transfer = None
        self.receiver = None
        self.dialogs = []

    def install_style(self):
        provider = getattr(self, 'style_provider', None)
        is_new_provider = provider is None
        if is_new_provider:
            provider = Gtk.CssProvider()
        css = """
            .lquickair-content {
                background: #f5f7fb; color: #17243b; opacity: 1;
            }
            .lquickair-content label { color: #17243b; opacity: 1; }
            .lquickair-content .muted, .lquickair-content .dim-label { color: #5d6c82; opacity: 1; }
            .lquickair-content menubutton.settings-menu > button {
                background: #ffffff; color: #17243b; border: 1px solid #c6d2e3;
                border-radius: 10px; padding: 10px; min-height: 24px; box-shadow: none;
            }
            .lquickair-content menubutton.settings-menu > button:hover { background: #edf3fc; }
            .lquickair-content .hero-title { font-size: 27px; font-weight: 800; }
            .lquickair-content .section-title { font-size: 15px; font-weight: 700; }
            .lquickair-content .card, .lquickair-content.card {
                background: #ffffff; border: 1px solid #dce4ef;
                border-radius: 16px; padding: 18px;
            }
            .lquickair button.app-button {
                background: #ffffff; color: #17243b; border: 1px solid #c6d2e3;
                border-radius: 10px; min-height: 24px; padding: 10px 16px;
                box-shadow: none; text-shadow: none; opacity: 1;
            }
            .lquickair button.app-button label { color: inherit; }
            .lquickair button.app-button:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
            .lquickair button.app-button:hover { background: #edf3fc; }
            .lquickair button.app-button.suggested-action { background: #2563eb; color: #ffffff; border-color: #2563eb; }
            .lquickair button.app-button.suggested-action:hover { background: #1d4ed8; }
            .lquickair button.app-button:disabled,
            .lquickair button.app-button.suggested-action:disabled { background: #edf1f7; color: #718096; border-color: #dce4ef; }
            .lquickair-content entry {
                background: #ffffff; color: #17243b; border: 1px solid #c6d2e3;
                border-radius: 9px; padding: 8px 10px;
            }
            .lquickair-content entry:focus { border-color: #2563eb; }
            .lquickair-content list { background: #ffffff; color: #17243b; border-radius: 12px; }
            .lquickair-content list row { border-radius: 10px; margin: 3px; }
            .lquickair-content list row:selected { background: #dbeafe; }
            .lquickair-content list row:hover { background: #eff5ff; }
            .lquickair-content .status-bar { background: #eaf1fc; border-radius: 10px; padding: 12px 16px; }
            .lquickair-content textview, .lquickair-content textview text { background: #ffffff; color: #17243b; }
            .lquickair-content switch { background: #b6c3d5; border-radius: 20px; }
            .lquickair-content switch:checked { background: #2563eb; }
            .lquickair-content switch slider { background: #ffffff; border-radius: 20px; }
        """
        if self.settings.theme == 'dark':
            palette = {
                '#f5f7fb': '#111722', '#17243b': '#edf2fa', '#5d6c82': '#a8b6cb',
                '#ffffff': '#1a2332', '#dce4ef': '#303d51', '#c6d2e3': '#465775',
                '#edf3fc': '#354864', '#2563eb': '#8cb9ff', '#1d4ed8': '#adceff',
                '#edf1f7': '#222e40', '#718096': '#8290a6', '#dbeafe': '#304b70',
                '#eff5ff': '#253750', '#eaf1fc': '#192538', '#b6c3d5': '#45536a',
            }
            css = re.sub(r'#[0-9a-f]{6}', lambda match: palette.get(match[0], match[0]), css)
            css += '.lquickair-content switch slider { background: #f1f5fb; }'
        provider.load_from_data(css.encode())
        display = Gdk.Display.get_default()
        if is_new_provider:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1,
            )
        self.style_provider = provider

    @staticmethod
    def label(text, *, muted=False, title=False):
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        if muted:
            label.add_css_class('muted')
        if title:
            label.add_css_class('section-title')
        return label

    @staticmethod
    def card():
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class('card')
        return card

    def do_activate(self):
        if self.props.active_window:
            self.props.active_window.present()
            return
        self.install_style()
        self.window = Gtk.ApplicationWindow(application=self, title='lQuickAir')
        self.window.add_css_class('lquickair')
        self.window.set_opacity(1.0)
        self.window.set_default_size(720, 800)
        self.window.connect('close-request', self.close)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{edge}')(24)
        page = Gtk.ScrolledWindow()
        page.add_css_class('lquickair-content')
        page.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page.set_child(box)
        self.window.set_child(page)

        hero = Gtk.Box(spacing=16)
        introduction = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title = self.label('Share something nearby')
        title.add_css_class('hero-title')
        introduction.append(title)
        introduction.append(self.label('Share files with nearby Android devices.', muted=True))
        introduction.set_hexpand(True)
        hero.append(introduction)
        box.append(hero)
        self.capabilities = self.label('Checking Bluetooth and network support…', muted=True)
        box.append(self.capabilities)

        send_card = self.card()
        send_card.append(self.label('Send files', title=True))
        file_row = Gtk.Box(spacing=12)
        choose = Gtk.Button(label='Choose files…')
        choose.add_css_class('app-button')
        choose.connect('clicked', self.choose_files)
        file_row.append(choose)
        self.selection = Gtk.Label(label='Choose what you want to share', xalign=0, hexpand=True)
        self.selection.set_ellipsize(3)
        self.selection.add_css_class('muted')
        file_row.append(self.selection)
        send_card.append(file_row)
        self.device_heading = self.label('Nearby devices', title=True)
        send_card.append(self.device_heading)
        self.devices = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.devices.connect('row-selected', lambda *_: self.update_send())
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        empty.set_margin_top(20)
        empty.set_margin_bottom(20)
        empty.append(Gtk.Image.new_from_icon_name('network-wireless-symbolic'))
        empty.append(Gtk.Label(label='Looking for nearby devices…'))
        empty.append(Gtk.Label(label='Open Quick Share → Receive on your phone.', wrap=True))
        self.devices.set_placeholder(empty)
        scroll = Gtk.ScrolledWindow(min_content_height=150, max_content_height=260)
        scroll.set_propagate_natural_height(True)
        scroll.set_child(self.devices)
        send_card.append(scroll)
        actions = Gtk.Box(spacing=12)
        self.send_button = Gtk.Button(label='Send to selected device', sensitive=False, hexpand=True)
        self.send_button.add_css_class('app-button')
        self.send_button.add_css_class('suggested-action')
        self.send_button.connect('clicked', self.send_files)
        actions.append(self.send_button)
        self.cancel_button = Gtk.Button(label='Cancel', sensitive=False)
        self.cancel_button.add_css_class('app-button')
        self.cancel_button.connect('clicked', self.cancel_send)
        actions.append(self.cancel_button)
        send_card.append(actions)
        box.append(send_card)

        receive_card = self.card()
        receive_row = Gtk.Box(spacing=12)
        receive_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True)
        receive_copy.append(self.label('Receive files', title=True))
        receive_copy.append(self.label('Allow nearby devices to send to this PC.', muted=True))
        receive_row.append(receive_copy)
        self.receive_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.receive_switch.connect('notify::active', self.toggle_receive)
        receive_row.append(self.receive_switch)
        receive_card.append(receive_row)
        self.receive_location = self.label('', muted=True)
        self.update_receive_location()
        receive_card.append(self.receive_location)
        box.append(receive_card)

        preferences = Gtk.Expander(label='Settings')
        settings = self.card()
        settings.add_css_class('lquickair-content')
        theme_row = Gtk.Box(spacing=12)
        theme_label = self.label('Dark theme', title=True)
        theme_label.set_hexpand(True)
        theme_row.append(theme_label)
        self.theme_selector = Gtk.Switch(
            active=self.settings.theme == 'dark', valign=Gtk.Align.CENTER,
        )
        self.theme_handler = self.theme_selector.connect('notify::active', self.change_theme)
        theme_row.append(self.theme_selector)
        settings.append(theme_row)
        settings.append(self.label('Your PC name', title=True))
        identity_row = Gtk.Box(spacing=12)
        self.name_entry = Gtk.Entry(text=self.settings.name, hexpand=True)
        self.name_entry.set_placeholder_text('Name shown on nearby devices')
        self.name_entry.set_width_chars(14)
        identity_row.append(self.name_entry)
        save_name = Gtk.Button(label='Save')
        save_name.add_css_class('app-button')
        save_name.connect('clicked', self.save_name)
        identity_row.append(save_name)
        settings.append(identity_row)
        settings.append(self.label('Save received files to', title=True))
        folder_row = Gtk.Box(spacing=12)
        self.folder_label = self.label(self.settings.receive_folder, muted=True)
        self.folder_label.set_hexpand(True)
        self.folder_label.set_wrap(False)
        self.folder_label.set_max_width_chars(24)
        self.folder_label.set_ellipsize(2)
        self.folder_label.set_tooltip_text(self.settings.receive_folder)
        folder_row.append(self.folder_label)
        choose_folder = Gtk.Button(label='Change…')
        choose_folder.add_css_class('app-button')
        choose_folder.connect('clicked', self.choose_receive_folder)
        folder_row.append(choose_folder)
        settings.append(folder_row)
        auto_row = Gtk.Box(spacing=12)
        auto_label = self.label('Auto-accept files from remembered names')
        auto_label.set_hexpand(True)
        auto_label.set_max_width_chars(28)
        auto_row.append(auto_label)
        self.auto_switch = Gtk.Switch(active=self.settings.auto_accept, valign=Gtk.Align.CENTER)
        self.auto_handler = self.auto_switch.connect('notify::active', self.save_auto_accept)
        auto_row.append(self.auto_switch)
        settings.append(auto_row)
        settings.append(self.label('Names can be copied. Enable only on a network you trust.', muted=True))
        self.remembered_label = self.label('')
        self.remembered_label.set_max_width_chars(34)
        settings.append(self.remembered_label)
        forget = Gtk.Button(label='Forget remembered devices', halign=Gtk.Align.START)
        forget.add_css_class('app-button')
        forget.connect('clicked', self.forget_devices)
        settings.append(forget)
        self.update_remembered()
        settings.set_margin_top(12)
        preferences.set_child(settings)
        box.append(preferences)

        self.status = self.label('')
        self.status.set_visible(False)
        self.status.connect(
            'notify::label', lambda label, _param: label.set_visible(bool(label.get_label())),
        )
        self.status.set_selectable(True)
        self.status.add_css_class('status-bar')
        box.append(self.status)
        self.window.present()
        self.backend = Backend(self.emit)
        self.backend.submit(self.backend.discover())

    def emit(self, event, value):
        GLib.idle_add(self.handle_event, event, value)

    def handle_event(self, event, value):
        if event == 'device':
            if value not in self.rows:
                row = Gtk.ListBoxRow()
                row.device_key = value
                content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                for edge in ('top', 'bottom', 'start', 'end'):
                    getattr(content, f'set_margin_{edge}')(12)
                content.append(Gtk.Label(label=value[0], xalign=0))
                transport = Gtk.Label(label=value[1], xalign=0)
                transport.add_css_class('dim-label')
                content.append(transport)
                row.set_child(content)
                self.devices.append(row)
                self.rows[value] = row
                self.device_heading.set_text(f'Nearby devices · {len(self.rows)}')
        elif event == 'ready':
            self.capabilities.set_text(
                f'Bluetooth: {"available" if value.bluetooth else "unavailable"} · '
                f'Wi-Fi Direct: {"available" if value.network_manager else "unavailable"}'
            )
        elif event == 'text':
            self.show_received_text(*value)
        elif event == 'request':
            key, sender, pin, names, files_only = value
            if self.settings.should_accept(sender, files_only=files_only):
                self.backend.submit(self.backend.respond(key, True))
                self.status.set_text(f'Automatically accepting files from {sender}.')
                return GLib.SOURCE_REMOVE
            dialog = Gtk.MessageDialog(
                transient_for=self.window, modal=True,
                text=f'Incoming share from {sender}',
                secondary_text=f'{", ".join(names)}\n\nConfirm this code matches your phone: {pin}',
            )
            dialog.add_css_class('lquickair')
            dialog.get_content_area().add_css_class('lquickair-content')
            dialog.set_opacity(1.0)
            dialog.add_button('Decline', Gtk.ResponseType.CANCEL)
            dialog.add_button('Accept', Gtk.ResponseType.ACCEPT)
            for response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.ACCEPT):
                dialog.get_widget_for_response(response).add_css_class('app-button')
            dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT).add_css_class('suggested-action')
            dialog.set_default_response(Gtk.ResponseType.CANCEL)
            remember = Gtk.CheckButton(label='Remember this name for automatic file acceptance')
            remember.set_active(sender in self.settings.remembered_names)
            remember.set_sensitive(files_only)
            dialog.get_message_area().append(remember)
            def respond(dialog, response):
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
                        self.status.set_text(f'Could not save remembered device: {error}')
                    self.update_remembered()
                self.backend.submit(self.backend.respond(key, accepted))
                self.dialogs.remove(dialog)
                dialog.destroy()
            dialog.connect('response', respond)
            self.dialogs.append(dialog)
            dialog.present()
        else:
            self.status.set_text(('Could not complete operation: ' if event == 'error' else '') + str(value))
            if event == 'error':
                self.capabilities.set_text('Check Bluetooth, system dependencies, and the terminal log.')
            if event in ('sent', 'error'):
                self.cancel_button.set_sensitive(False)
                self.update_send()
        return GLib.SOURCE_REMOVE

    def show_received_text(self, title, text):
        popup = Gtk.Window(
            title=title or 'Received text', transient_for=self.window,
            modal=True, destroy_with_parent=True,
        )
        popup.add_css_class('lquickair')
        popup.set_opacity(1.0)
        popup.set_default_size(520, 360)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(content, f'set_margin_{edge}')(20)
        content.add_css_class('lquickair-content')
        popup.set_child(content)
        heading = Gtk.Label(label=title or 'Received text', xalign=0, wrap=True)
        heading.add_css_class('title-2')
        content.append(heading)
        view = Gtk.TextView(editable=False, cursor_visible=False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(text)
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(view)
        content.append(scroll)
        actions = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        close = Gtk.Button(label='Close')
        close.add_css_class('app-button')
        close.connect('clicked', lambda _button: popup.close())
        actions.append(close)
        copy = Gtk.Button(label='Copy')
        copy.add_css_class('app-button')
        copy.add_css_class('suggested-action')
        def copy_text(button):
            popup.get_clipboard().set(text)
            button.set_label('Copied!')
        copy.connect('clicked', copy_text)
        actions.append(copy)
        content.append(actions)
        popup.present()

    def choose_files(self, _button):
        chooser = Gtk.FileChooserNative(title='Choose files to share', transient_for=self.window,
                                        action=Gtk.FileChooserAction.OPEN)
        chooser.set_select_multiple(True)
        def selected(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                model = dialog.get_files()
                self.files = [model.get_item(i).get_path() for i in range(model.get_n_items())]
                self.files = [file for file in self.files if file and Path(file).is_file()]
                self.selection.set_text(', '.join(Path(file).name for file in self.files) or 'No files selected')
                self.update_send()
            dialog.destroy()
        chooser.connect('response', selected)
        chooser.show()

    def update_send(self):
        busy = self.transfer is not None and not self.transfer.done()
        self.send_button.set_sensitive(bool(self.files and self.devices.get_selected_row() and not busy))

    def send_files(self, _button):
        row = self.devices.get_selected_row()
        if row and self.files:
            self.transfer = self.backend.submit(self.backend.send(row.device_key, list(self.files), self.settings.name))
            self.transfer.add_done_callback(lambda _: GLib.idle_add(self.update_send))
            self.send_button.set_sensitive(False)
            self.cancel_button.set_sensitive(True)

    def cancel_send(self, _button):
        if self.transfer:
            self.transfer.cancel()
        self.cancel_button.set_sensitive(False)
        self.status.set_text('Send cancelled.')

    def toggle_receive(self, switch, _param):
        if switch.get_active():
            self.receiver = self.backend.submit(self.backend.receive(self.settings.name, self.settings.receive_folder))
            self.status.set_text(f'Receiving enabled. Select {self.settings.name} on your phone.')
        elif self.receiver:
            self.status.set_text('Receiving disabled.')
            self.receiver.cancel()
            for key in list(self.backend.requests):
                self.backend.submit(self.backend.respond(key, False))
            for dialog in self.dialogs[:]:
                self.dialogs.remove(dialog)
                dialog.destroy()

    def change_theme(self, selector, _param):
        previous = self.settings.theme
        selected_theme = 'dark' if selector.get_active() else 'light'
        if selected_theme == previous:
            return
        self.settings.theme = selected_theme
        try:
            self.settings.save()
        except OSError as error:
            self.settings.theme = previous
            selector.handler_block(self.theme_handler)
            selector.set_active(previous == 'dark')
            selector.handler_unblock(self.theme_handler)
            self.status.set_text(f'Could not save theme: {error}')
            return
        # Apply after the control's notification finishes; avoid restyling a
        # mapped dropdown popup or replacing display-wide providers mid-signal.
        if not getattr(self, '_theme_update_pending', False):
            self._theme_update_pending = True
            GLib.idle_add(self.apply_theme)

    def apply_theme(self):
        self._theme_update_pending = False
        self.install_style()
        return GLib.SOURCE_REMOVE

    def update_receive_location(self):
        self.receive_location.set_text(
            f'Saved to {self.settings.receive_folder} · Network connection required'
        )

    def choose_receive_folder(self, _button):
        from gi.repository import Gio

        chooser = Gtk.FileChooserNative(
            title='Save received files to', transient_for=self.window,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label='Select folder', cancel_label='Cancel',
        )
        chooser.set_current_folder(Gio.File.new_for_path(self.settings.receive_folder))
        def selected(dialog, response):
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
                        self.status.set_text(f'Could not save download folder: {error}')
                    else:
                        self.folder_label.set_text(path)
                        self.folder_label.set_tooltip_text(path)
                        self.update_receive_location()
                        if self.receive_switch.get_active():
                            self.receive_switch.set_active(False)
                            self.status.set_text('Folder saved. Enable receiving again to use it.')
                        else:
                            self.status.set_text('Receive folder saved.')
                else:
                    self.status.set_text('Choose a local folder for received files.')
            dialog.destroy()
        chooser.connect('response', selected)
        chooser.show()

    def save_name(self, _button):
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
            self.status.set_text('Name saved. Enable receiving again to advertise the new name.')
        else:
            self.status.set_text('PC name saved.')

    def save_auto_accept(self, switch, _param):
        previous = self.settings.auto_accept
        self.settings.auto_accept = switch.get_active()
        try:
            self.settings.save()
        except OSError as error:
            self.settings.auto_accept = previous
            switch.handler_block(self.auto_handler)
            switch.set_active(previous)
            switch.handler_unblock(self.auto_handler)
            self.status.set_text(f'Could not save preference: {error}')

    def update_remembered(self):
        names = ', '.join(sorted(self.settings.remembered_names)) or 'None'
        self.remembered_label.set_text(f'Remembered names: {names}')

    def forget_devices(self, _button):
        previous = set(self.settings.remembered_names)
        self.settings.remembered_names.clear()
        try:
            self.settings.save()
        except OSError as error:
            self.settings.remembered_names = previous
            self.status.set_text(f'Could not forget devices: {error}')
        self.update_remembered()

    def close(self, _window):
        if self.backend:
            self.backend.close()
        return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    if not Gtk.init_check() or Gdk.Display.get_default() is None:
        raise SystemExit('Cannot open the display. Run gui.py from your Linux desktop session.')
    LQuickAir().run(None)
