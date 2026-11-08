# type: ignore  # noqa: PGH003
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method
from dbus_next.signature import Variant

SERVICE_UUID = "0000fe2c-0000-1000-8000-00805f9b34fb"

__all__ = ("_FastInitAdvertisement",)

# ruff: disable[F722, N802, F821]


class _FastInitAdvertisement(ServiceInterface):
    """Minimal org.bluez.LEAdvertisement1 implementation."""

    def __init__(self, payload: bytes) -> None:
        """i initialize the _fastinitadvertisement state and its required resources."""
        super().__init__("org.bluez.LEAdvertisement1")
        self._payload = payload
        self._txpower = 0

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":  # type: ignore[override]
        """i expose the bluetooth advertisement type expected by bluez."""
        return "broadcast"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceData(self) -> "a{sv}":
        """i expose the nearby sharing service data advertised to bluez."""
        return {SERVICE_UUID: Variant("ay", self._payload)}

    @dbus_property(access=PropertyAccess.READWRITE)
    def TxPower(self) -> "n":  # type: ignore[override]
        """i read or update the transmit-power setting requested by bluez."""
        return self._txpower

    @TxPower.setter
    def TxPower(self, value: "n") -> None:  # type: ignore[override]
        """i read or update the transmit-power setting requested by bluez."""
        self._txpower = value

    @method()
    async def Release(self) -> None:
        """i acknowledge that bluez has released the advertisement."""
        bluetooth.debug("Fast Init advertisement released by BlueZ")


# ruff: enable[F722, N802, F821]
