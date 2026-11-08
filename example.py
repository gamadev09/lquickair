"""Command-line examples for discovering, sending, and receiving shares."""

import argparse
import asyncio
import contextlib
import sys
from logging import basicConfig

import lquickair
from lquickair import common
from lquickair.mdns.send import trigger_devices


async def send(file: str) -> None:
    """Send one file to the first connectable device discovered."""
    discovery = await lquickair.discover_services()
    discovery.qr_code.print()
    async for device in discovery:
        if device.connectable:
            await device.send(file=file)
            return


async def main(argv: list[str]) -> None:
    """Parse the example mode and run it until completed or interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("send", "receive", "advertise"))
    parser.add_argument("file", nargs="?", help="File to send in send mode")
    arguments = parser.parse_args(argv[1:])
    if arguments.mode == "send":
        if arguments.file is None:
            parser.error("send mode requires a file")
        await send(arguments.file)
    elif arguments.mode == "receive":
        async for request in lquickair.receive(endpoint_id=lquickair.generate_endpoint_id()):
            results = await request.accept()
            print(results)  # noqa: T201 - this example reports received data to the terminal.
    else:
        await trigger_devices()


if __name__ == "__main__":
    basicConfig(level=common.SILLY)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(sys.argv))
