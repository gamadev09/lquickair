# lQuickAir

![Ruff logo](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/teaishealthy/teaishealthy/refs/heads/main/ruff-badge.json&style=flat-square)


An independent Linux app compatible with Android Quick Share, with a GTK4 interface and an asynchronous Python backend.

Based on [pyquickshare](https://github.com/teaishealthy/pyquickshare). Not affiliated with Google or Samsung.

## System requirements

lquickair makes no assumptions about the underlying system and will gracefully degrade if features are missing.
All services are accessed over D-Bus (with the exception of some Bluetooth operations).
For full functionality, the following are needed:

- **Bluetooth:** BlueZ with a Bluetooth Classic adapter
- **Nudging nearby devices:** BLE support*
- **Wi-Fi Direct:** NetworkManager with a Wi-Fi adapter

lquickair collets `facts` about the system to determine which features are available and which transports can be used. Check the logging output for details.

*BlueZ must be running in dual mode: set `ControllerMode = dual` in `/etc/bluetooth/main.conf` and restart the Bluetooth service (`systemctl restart bluetooth`).

### Firewalls

As Quick Share uses a direct connection between devices, it is necessary to allow incoming connections on the advertised port. firewalld is supported out of the box (but not required).

lquickair temporarily reconfigures `firewalld` (if available) to accept an incoming connection on it's advertised port.
This is done by adding a temporary rule to the currently "active" zone.
This rule is automatically removed by `firewalld` after 5 minutes.

Communication with `firewalld` is done over D-Bus, `polkit` may prompt for authentication.

## Installation

Depending on your Linux distribution, you may need to install some development packages to build the C++ extension module:

| Distro          | Package                                                             |
| --------------- | ------------------------------------------------------------------- |
| Debian / Ubuntu | `python3-dev` `libbluetooth-dev` `cmake` `pkgconf`                 |
| Arch            | `python` `bluez` `cmake` `pkgconf`                                 |
| Fedora / RHEL   | `python3-devel` `bluez-libs-devel` `cmake` `pkgconf-pkg-config`    |
| Alpine          | `python3-dev` `bluez-dev` `cmake` `pkgconf`                        |


Now you can install lquickair using pip:

```bash
pip install .

# or, to install with extras (QR code support)
pip install ".[extras]"
```

## Features

Receive is fully implemented, namely WiFi credentials, files, and text. Sending only supports files, but support for sending text and WiFi credentials is planned.

### Transfer
Quick Share supports two "bare" transports: WiFi/LAN and Bluetooth Classic. Bluetooth Classic *can* transfer files, but can also be used to trigger an upgrade to a faster medium (e.g. WiFi Direct or Hotspot).

lquickair supports both transports for discovery and transfer. It also supports upgrading to WiFi Direct (and WiFi/LAN).

### Discovery
lquickair uses mDNS to discover other devices on the local network. BLE is only used to trigger advertisment at the moment ("nudging" or "Fast Init").

## Usage

**example.py** is a basic example of how to use lquickair.
It provides a command line interface to send and receive files using Quick Share:

```bash
uv run example.py receive
```

```bash
uv run example.py send <file>
```

## Development

Make sure you installed the system dependencies mentioned in the installation section. Now sync with:

```bash
uv sync --dev --all-extras
```

## Notes and Acknowledgements

- The code in [`lquickair/protos`](lquickair/protos/) is generated from protobuf sources licensed under Apache 2.0.
As a derivative work, these generated files remain under the original Apache 2.0 license.
A copy of the original license can be found in the [`lquickair/protos`](lquickair/protos/) directory.

- This project would not have been possible without the amazing reverse engineering work done by [grishka](https://github.com/grishka/) on the Quick Share protocol.
Check out [NearDrop](https://github.com/grishka/NearDrop/), a similar project for Mac OS.


## Desktop interface (GTK4)

The desktop frontend is in `gui.py`. It provides device selection with Bluetooth
or LAN labels, a file picker, send cancellation, and incoming requests with a
verification code and accept/decline buttons. Multiple selected files are sent
one at a time. Received files go to `~/Downloads/lquickair`; existing files are
preserved by adding a numeric suffix.

### Desktop setup (Debian 13 / Ubuntu with GLib 2.80 or newer)

Install the system libraries once:

```bash
sudo apt update
sudo apt install python3-venv python3-dev build-essential cmake pkgconf \
  libbluetooth-dev libcairo2-dev libgirepository-2.0-dev gir1.2-gtk-4.0 libmagic1
```

Then launch from this checkout:

```bash
./run-desktop.sh
```

The launcher installs uv in a local `.bootstrap` environment if needed, selects
Python 3.10 as required by this project, and installs the backend, its compiled
Bluetooth extension, and the `desktop` extra (PyGObject) into `.venv`.
The first run requires internet access. Subsequent runs use the same command.
Do not launch with the system `python3 gui.py` unless that interpreter has all
backend dependencies and GTK bindings installed.

Select files, open **Quick Share → Receive** on Android, select the device and
transport in the list, and click **Send files**. Enable **Receive from nearby
devices** to accept incoming shares. Check the verification code against the
phone before accepting. Keep the app open during a transfer.

Current limitations:

- Bluetooth entries use the backend's Bluetooth sender; the backend may negotiate
  an upgrade to Wi-Fi. The label describes the discovered connection, not a live
  measurement of the active transport.
- This checkout's receiver listens over LAN, so Bluetooth-only receiving is not
  implemented by this UI.
- The backend does not expose byte-progress or a reliable delivery result. The UI
  shows operation status and asks you to confirm delivery on the phone.
- Discovery currently adds devices without expiry. If a device disappears, reopen
  the app to clear its entry.

Backend errors appear in the window, with details logged to the terminal.

### PC name and remembered senders

The desktop advertises itself as a laptop/PC. Set **PC name** and click **Save
name** to change its public name for discovery and outgoing transfers. If
receiving was enabled, enable it again after saving to advertise the new name.

To skip future file approval prompts, first receive from a device, verify the
code, check **Remember this name for automatic file acceptance**, and accept.
Then enable **Auto-accept files from remembered names**. The switch defaults to
off. Text and Wi-Fi credentials always require approval. **Forget remembered
devices** clears the list.

This is name-based matching, not authenticated device trust: the current backend
skips persistent paired-key verification, and another sender can copy a remembered
name. Enable the convenience option only where that is acceptable. Preferences
are stored in `$XDG_CONFIG_HOME/lquickair/desktop.json`, normally
`~/.config/lquickair/desktop.json`.


### Renamed from pyquickshare

The application is **lQuickAir**; the distribution and import package are `lquickair`. Run
`./run-desktop.sh` after updating to rebuild the renamed Bluetooth extension.
Existing preferences and remembered sender names are loaded from the legacy
`~/.config/pyquickshare/desktop.json` when no new settings file exists. Saving a
preference writes the new `lquickair` configuration. Existing receive-folder
choices are preserved; new installations default to `~/Downloads/lquickair`.

Use `LQUICKAIR_IP` to override the listening IP. The older `QUICKSHARE_IP`
environment variable is still accepted for compatibility.
