"""Wire-level device identity regression checks."""
import asyncio
import unittest

from lquickair.common import Type, to_url64
from lquickair.facts import Facts
from lquickair.mdns.receive import make_n, parse_endpoint_info
from lquickair.protos import offline_wire_formats
from lquickair.send import SendConnection


class DeviceIdentityTests(unittest.TestCase):
    def test_device_type_and_unicode_name_round_trip(self):
        for device_type in (Type.phone, Type.tablet, Type.laptop):
            raw = make_n(visible=True, type=device_type, name='Linux café'.encode())
            decoded = parse_endpoint_info(to_url64(raw).encode())
            self.assertEqual(decoded.type, device_type)
            self.assertEqual(decoded.name, 'Linux café')
            self.assertTrue(decoded.visible)

    def test_hidden_device_has_no_public_name(self):
        raw = make_n(visible=False, type=Type.laptop, name=b'Private PC')
        decoded = parse_endpoint_info(to_url64(raw).encode())
        self.assertFalse(decoded.visible)
        self.assertIsNone(decoded.name)
        self.assertEqual(decoded.type, Type.laptop)

    def test_outgoing_handshake_uses_configured_pc_name(self):
        messages = []
        connection = object.__new__(SendConnection)

        async def capture(data):
            messages.append(data)
        connection.send_bytes = capture
        asyncio.run(connection.send_connection_request(
            b'ABCD', facts=Facts(False, False, False), device_name='My desktop',
        ))
        request = offline_wire_formats.OfflineFrame().parse(messages[0]).v1.connection_request
        info = parse_endpoint_info(to_url64(request.endpoint_info).encode())
        self.assertEqual(request.endpoint_name, 'My desktop')
        self.assertEqual(info.name, 'My desktop')
        self.assertEqual(info.type, Type.laptop)
