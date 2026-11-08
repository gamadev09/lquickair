# ruff: noqa: PGH003
# the mDNS part of Quick Share
from __future__ import annotations

import asyncio
import io
import os
import random
import socket
from contextlib import closing, suppress
from logging import getLogger
from typing import NamedTuple

import dbus_next
import ifaddr
from zeroconf import IPVersion
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

from ..common import NETWORK_BASE_PATH, InterfaceInfo, Type, from_url64, to_url64
from ..dbus.firewalld import temporarily_open_port

logger = getLogger(__name__)
MAX_DEVICE_NAME_BYTES = 255


def get_interfaces() -> list[str]:
    """i list the local network interfaces eligible for discovery."""
    interfaces: list[str] = []
    for ifa in NETWORK_BASE_PATH.iterdir():
        carrier = ifa.joinpath("carrier")
        with suppress(OSError):
            if (
                "/devices/virtual/net/" not in ifa.resolve().as_posix()
                and carrier.exists()
                and carrier.read_text().strip() == "1"
            ):
                interfaces.append(ifa.name)
    return interfaces


class IPV4Runner:
    def __init__(self) -> None:
        """i initialize the ipv4runner state and its required resources."""
        self.aiozc: AsyncZeroconf | None = None

    async def register_services(self, infos: list[AsyncServiceInfo]) -> None:
        """i register the receiver advertisements with the discovery service."""
        self.aiozc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        tasks = [self.aiozc.async_register_service(info) for info in infos]  # type: ignore
        background_tasks = await asyncio.gather(*tasks)  # type: ignore
        await asyncio.gather(*background_tasks)  # type: ignore
        logger.debug("Registered %d services", len(infos))

        await asyncio.Event().wait()

    async def unregister_services(self, infos: list[AsyncServiceInfo]) -> None:
        """i remove the receiver advertisements from the discovery service."""
        assert self.aiozc is not None  # noqa: S101 - escape hatch for the type checker
        tasks = [self.aiozc.async_unregister_service(info) for info in infos]  # type: ignore
        background_tasks = await asyncio.gather(*tasks)  # type: ignore
        await asyncio.gather(*background_tasks)  # type: ignore
        await self.aiozc.async_close()


def make_service_name(endpoint_id: bytes) -> bytearray:
    """i encode the endpoint identifier into the discovery service name."""
    array = bytearray()

    array.append(0x23)  # PCP
    logger.debug("endpoint_id: %s", endpoint_id)
    array.extend(endpoint_id)
    array.extend((0xFC, 0x9F, 0x5E))  # Service ID
    array.extend((0x00, 0x00))  # ¯\_(ツ)_/¯

    return array


class EndpointInfo(NamedTuple):
    visible: bool
    type: Type
    name: str | None
    records: dict[int, bytes]


def parse_endpoint_info(n: bytes) -> EndpointInfo:
    """i decode the advertised visibility, device type, name, and extra records."""
    decoded = from_url64(n.decode("utf-8"))
    buffer = io.BytesIO(decoded)
    flags = buffer.read(1)[0]
    visible = ((flags >> 4) & 1) == 0
    device_type = Type(flags >> 1 & 0b00000111)

    buffer.read(2)  # skip 2 bytes of "salt"
    buffer.read(14)  # skip 14 bytes of "encrypted metadata key"

    name = None

    if visible:
        name_length = buffer.read(1)[0]  # length byte
        name = buffer.read(name_length).decode("utf-8")  # name bytes

    records: dict[int, bytes] = {}
    while buffer.tell() < buffer.getbuffer().nbytes:
        type_ = buffer.read(1)[0]
        length = buffer.read(1)[0]
        value = buffer.read(length)
        records[type_] = value

    return EndpointInfo(visible, device_type, name, records)


def make_n(*, visible: bool, type: Type, name: bytes) -> bytearray:
    """i encode the endpoint information used by nearby discovery."""
    n = bytearray()

    # n record:
    # one byte: flags (3) visibility (1) type (3) empty (1)
    # 16 zero bytes
    # one byte: length of name
    # name, utf-8 encoded

    if not name or len(name) > MAX_DEVICE_NAME_BYTES:
        message = "Device name must contain 1-255 UTF-8 bytes"
        raise ValueError(message)
    n.append((0 if visible else 0x10) | (type.value << 1))
    # add 16 0 bytes
    n.extend([random.randint(1, 8) for _ in range(16)])  # noqa: S311 - random is fine here
    if visible:
        n.append(len(name))
        n.extend(name)
    return n


async def make_service(
    *,
    visible: bool,
    type_: Type,
    name: bytes,
    endpoint_id: bytes,
    interface_info: InterfaceInfo,
) -> AsyncServiceInfo:
    """i describe the visible receiver as a discoverable network service."""
    _name = to_url64(make_service_name(endpoint_id))
    n = make_n(visible=visible, type=type_, name=name)

    return AsyncServiceInfo(
        "_FC9F5ED42C8A._tcp.local.",
        f"{_name}._FC9F5ED42C8A._tcp.local.",
        port=interface_info.port,
        parsed_addresses=interface_info.ips,
        properties={"n": to_url64(n)},
    )


async def get_interface_info() -> InterfaceInfo:
    """i select the listening addresses and an available receiving port."""
    ips: list[str] = []

    ip = os.environ.get("LQUICKAIR_IP") or os.environ.get("QUICKSHARE_IP")
    used_interfaces: set[str] = set()

    if ip is None:
        interfaces = get_interfaces()
        for adapter in ifaddr.get_adapters():
            if adapter.name not in interfaces:
                continue

            used_interfaces.add(adapter.name)
            ips.extend(str(ip.ip) for ip in adapter.ips if isinstance(ip.ip, str))

        logger.debug("LQUICKAIR_IP not set, using: %s", ", ".join(ips))
    else:
        ips.append(ip)

    with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
        sock.bind(("0.0.0.0", 0))  # noqa: S104 - we only care about the port
        _, port = sock.getsockname()

    try:
        for interface in used_interfaces:
            await temporarily_open_port(interface, port)
    except dbus_next.errors.DBusError as e:
        if e.text == "The name is not activatable":
            logger.exception(
                "Failed to open port %d. Are you using firewalld? "
                "You may need to manually open the port on your firewall.",
                port,
            )
    except Exception:
        logger.exception("Failed to open port %d. Are you using firewalld?", port)

    logger.debug("Using port %d", port)

    return InterfaceInfo(ips=ips, port=port)
