#!/bin/sh
# Keep GTK and the backend installed into the same supported Python environment.
set -eu
cd -- "$(dirname -- "$0")"

if command -v uv >/dev/null 2>&1; then
    desktop_uv=$(command -v uv)
else
    if [ ! -x .bootstrap/bin/uv ]; then
        if [ ! -x .bootstrap/bin/python ]; then
            python3 -m venv .bootstrap || {
                echo 'Install python3-venv first; see the Desktop setup section in README.md.' >&2
                exit 1
            }
        fi
        .bootstrap/bin/python -m pip install uv
    fi
    desktop_uv="$PWD/.bootstrap/bin/uv"
fi

# uv resolves the Python 3.10 requirement and builds the Bluetooth extension.
# PyGObject is installed into that same environment via the desktop extra.
"$desktop_uv" sync --python 3.10 --extra desktop
exec "$desktop_uv" run --python 3.10 --extra desktop python -m lquickair.desktop
