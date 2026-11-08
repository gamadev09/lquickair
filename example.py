import asyncio
import contextlib
import sys
from logging import DEBUG, basicConfig

import lquickair
import lquickair.common
from lquickair.mdns.send import trigger_devices

basicConfig(level=lquickair.common.SILLY)


async def send(file: str) -> None:
    discovery = await lquickair.discover_services()
    discovery.qr_code.print()

    async for device in discovery:
        if device.connectable:
            return await device.send(file=file)

    return None



async def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print("Usage: example.py <mode> [args...]")
        return

    if argv[1] == "send":
        if len(argv) < 3:
            print("Usage: example.py send <file>")
            return
        await send(argv[2])
    elif argv[1] == "receive":
        # if you want to appear like different devices, you can change the endpoint_id like this:
        # asnyc for request in lquickair.receive(endpoint_id=b"1234"):
        # (the endpoint_id must be 4 bytes long, you can use lquickair.generate_enpoint_id())

        async for request in lquickair.receive(endpoint_id=lquickair.generate_endpoint_id()):
            results = await request.accept()
            print(results)
    elif argv[1] == "advertise":
        lquickair.common.create_task(trigger_devices())

    else:
        print("Unknown mode:", argv[1])

async def wrapper():
    try:
        await main(sys.argv)
    finally:
        await lquickair.common.clear_tasks()

if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(wrapper())
