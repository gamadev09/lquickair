"""Run protocol coroutines on a dedicated asyncio thread, without GTK dependencies."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, TypeVar

import lquickair
from lquickair.results import FileResult, TextResult
from lquickair.send import BluetoothConnectable

from .settings import default_receive_folder

logger = logging.getLogger(__name__)

TaskResult = TypeVar("TaskResult")
EventSink = Callable[[str, Any], None]
DeviceKey = tuple[str, str]


class TransferWorker:
    """Keep asyncio and all protocol objects on one dedicated thread."""

    def __init__(self, emit: EventSink) -> None:
        self.emit = emit
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.devices = {}
        self.requests = {}
        self.thread.start()

    def run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.set_exception_handler(
            lambda _loop, context: self.emit(
                "error",
                str(context.get("exception") or context.get("message", "Unknown protocol error")),
            )
        )
        self.loop.run_forever()

    def submit(
        self,
        coroutine: Coroutine[Any, Any, TaskResult],
    ) -> concurrent.futures.Future[TaskResult]:
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)

        def completed(result: concurrent.futures.Future[TaskResult]) -> None:
            try:
                result.result()
            except (concurrent.futures.CancelledError, asyncio.CancelledError):
                pass
            except ModuleNotFoundError as error:
                self.emit(
                    "error",
                    f"Missing dependency: {error.name}. Close this window and run "
                    "./run-desktop.sh from the project folder to install the desktop environment.",
                )
            except Exception as error:
                logger.exception("lQuickAir operation failed")
                self.emit("error", str(error))

        future.add_done_callback(completed)
        return future

    async def discover(self) -> None:

        discovery = await lquickair.discover_services()
        self.emit("ready", discovery.facts)
        async for device in discovery:
            if not device.connectable:
                continue
            info = device.endpoint_info
            name = info.name if info and info.name else "Nearby device"
            medium = "Bluetooth" if isinstance(device, BluetoothConnectable) else "Wi-Fi / LAN"
            key = (name, medium)
            self.devices[key] = device
            self.emit("device", key)

    async def send(
        self,
        key: DeviceKey,
        files: Sequence[str],
        device_name: str | None = None,
    ) -> None:
        for file in files:
            self.emit("status", f"Sending {Path(file).name} · accept on your phone…")
            if device_name is None:
                await self.devices[key].send(file)
            else:
                await self.devices[key].send(file, device_name=device_name)
        self.emit("sent", "Send session finished. Check the receiving device for confirmation.")

    async def receive(
        self,
        device_name: str = "lQuickAir",
        output_dir: str | None = None,
    ) -> None:

        async for request in lquickair.receive(
            output_dir=Path(output_dir) if output_dir else default_receive_folder(),
            device_name=device_name,
        ):
            key = id(request)
            self.requests[key] = request
            self.emit(
                "request",
                (key, request.sender_name, request.pin, request.names, request.files_only),
            )

    async def respond(self, key: int, *, accept: bool) -> None:

        request = self.requests.pop(key)
        if accept:
            self.emit("status", "Receiving…")
            results = await request.accept()
            summaries = []
            for result in results:
                if isinstance(result, FileResult):
                    summaries.append(f"Saved {result.name}")
                elif isinstance(result, TextResult):
                    self.emit("text", (result.title, result.text))
                    summaries.append("Received text.")
                else:
                    summaries.append(f"Received Wi-Fi credentials for {result.ssid}")
            summary = "\n".join(summaries) or "Transfer ended without receiving files."
            self.emit("status", summary)
            if results:
                self.emit("received", summary)
        else:
            await request.reject()
            self.emit("status", "Incoming transfer declined.")

    async def shutdown(self) -> None:
        current = asyncio.current_task()
        tasks = [task for task in asyncio.all_tasks() if task is not current]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def close(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self.shutdown(), self.loop)
        future.add_done_callback(lambda _: self.loop.call_soon_threadsafe(self.loop.stop))
