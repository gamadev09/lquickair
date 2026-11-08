"""Protocol backend abstraction — unencrypted and encrypted byte channels."""

from __future__ import annotations

import abc
import struct
from logging import getLogger
from typing import TYPE_CHECKING

from .common import SILLY, Keychain, decrypt_to_bytes, encrypt_bytes, read

if TYPE_CHECKING:
    import asyncio

__all__ = ("ConnectionBackend", "EncryptedBackend", "UnencryptedBackend")

logger = getLogger(__name__)


class ConnectionBackend(abc.ABC):
    @abc.abstractmethod
    async def send(self, data: bytes) -> None:
        """i frame and send the message through this transport backend."""

    @abc.abstractmethod
    async def recv(self) -> bytes:
        """i receive and decode one framed message from the current transport."""

    @property
    @abc.abstractmethod
    def reader(self) -> asyncio.StreamReader:
        """i expose the incoming stream for the current transport."""
        ...

    @property
    @abc.abstractmethod
    def writer(self) -> asyncio.StreamWriter:
        """i expose the outgoing stream for the current transport."""
        ...


class UnencryptedBackend(ConnectionBackend):
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """i initialize the unencryptedbackend state and its required resources."""
        self._reader = reader
        self._writer = writer

    async def send(self, data: bytes) -> None:
        """i frame and send the message through this transport backend."""
        logger.log(SILLY, " > %d", len(data))
        self._writer.write(struct.pack(">I", len(data)))
        self._writer.write(data)
        await self._writer.drain()

    async def recv(self) -> bytes:
        """i receive and decode one framed message from the current transport."""
        payload = await read(self._reader)
        logger.log(SILLY, " < %d", len(payload))
        return payload

    @property
    def reader(self) -> asyncio.StreamReader:
        """i expose the incoming stream for the current transport."""
        return self._reader

    @property
    def writer(self) -> asyncio.StreamWriter:
        """i expose the outgoing stream for the current transport."""
        return self._writer


class EncryptedBackend(ConnectionBackend):
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        keychain: Keychain,
        *,
        sequence_number: int = 0,
    ) -> None:
        """i initialize the encryptedbackend state and its required resources."""
        self._reader = reader
        self._writer = writer
        self._keychain = keychain
        self._sequence_number = sequence_number

    @property
    def auth_string(self) -> bytes:
        """i expose the session authentication bytes used for verification."""
        return self._keychain.auth_string

    @property
    def keychain(self) -> Keychain:
        """i expose the keys associated with this encrypted channel."""
        return self._keychain

    async def send(self, data: bytes) -> None:
        """i frame and send the message through this transport backend."""
        self._sequence_number += 1
        encrypted = encrypt_bytes(data, self._keychain, self._sequence_number)

        logger.log(
            SILLY,
            "#> p=%d c=%d",
            len(data),
            len(encrypted),
        )

        self._writer.write(struct.pack(">I", len(encrypted)))
        self._writer.write(encrypted)
        await self._writer.drain()

    async def recv(self) -> bytes:
        """i receive and decode one framed message from the current transport."""
        raw = await read(self._reader)
        decrypted = decrypt_to_bytes(raw, self._keychain)
        logger.log(
            SILLY,
            "#< p=%d c=%d",
            len(decrypted),
            len(raw),
        )
        return decrypted

    @property
    def reader(self) -> asyncio.StreamReader:
        """i expose the incoming stream for the current transport."""
        return self._reader

    @property
    def writer(self) -> asyncio.StreamWriter:
        """i expose the outgoing stream for the current transport."""
        return self._writer

    def replace(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """i replace the underlying streams after a transport upgrade."""
        self._reader = reader
        self._writer = writer
