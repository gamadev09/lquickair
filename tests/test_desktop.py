"""Hardware-independent checks for the desktop's asyncio worker."""
import asyncio
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from gui import Backend


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        # This executor blocks AF_UNIX send(), including asyncio's wakeup pipe.
        # A test-only timer wakes the selector so thread scheduling can be checked.
        original_run = Backend.run
        def run_with_timer(worker):
            def tick():
                worker.loop.call_later(0.01, tick)
            worker.loop.call_soon(tick)
            original_run(worker)
        with patch.object(Backend, 'run', run_with_timer):
            self.backend = Backend(lambda *event: self.events.append(event))

    def tearDown(self):
        self.backend.close()
        self.backend.thread.join(timeout=3)
        self.assertFalse(self.backend.thread.is_alive())

    def test_files_are_sent_sequentially_on_worker(self):
        calls = []

        async def send(file):
            calls.append((file, threading.get_ident()))
            await asyncio.sleep(0)

        self.backend.devices[('Phone', 'Bluetooth')] = SimpleNamespace(send=send)
        future = self.backend.submit(
            self.backend.send(('Phone', 'Bluetooth'), ['one.txt', 'two.txt'])
        )
        future.result(timeout=3)
        self.assertEqual([file for file, _ in calls], ['one.txt', 'two.txt'])
        self.assertTrue(all(ident != threading.get_ident() for _, ident in calls))
        self.assertEqual(self.events[-1][0], 'sent')

    def test_cancel_stops_operation_without_finished_event(self):
        started = threading.Event()
        stopped = threading.Event()

        async def send(file):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        self.backend.devices['phone'] = SimpleNamespace(send=send)
        future = self.backend.submit(self.backend.send('phone', ['one.txt']))
        self.assertTrue(started.wait(timeout=3))
        future.cancel()
        self.assertTrue(stopped.wait(timeout=3))
        self.assertNotIn('sent', [event[0] for event in self.events])

    def test_errors_reach_ui(self):
        delivered = threading.Event()
        self.backend.emit = lambda *event: (self.events.append(event), delivered.set())

        async def fail():
            raise OSError('Bluetooth disconnected')

        with patch('gui.logging.exception'):
            future = self.backend.submit(fail())
            with self.assertRaises(OSError):
                future.result(timeout=3)
            self.assertTrue(delivered.wait(timeout=3))
        self.assertEqual(self.events, [('error', 'Bluetooth disconnected')])


if __name__ == '__main__':
    unittest.main()
