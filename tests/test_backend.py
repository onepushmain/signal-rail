import unittest
from backend import BlueZ, DEVICE, ADAPTER
from model import Device


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.backend = BlueZ.__new__(BlueZ)
        b = self.backend
        b.devices = {"dev": Device("dev", "Keyboard", paired=True)}
        b.pending, b.failures = {}, {}
        b.scan_path = None
        b.scan_starting = b.scan_wanted = False
        b.scan_timer = 0
        b.changed = lambda: None
        b.schedule_refresh = lambda: None
        self.errors = []
        b.error = lambda *args: self.errors.append(args)
        self.calls = []
        b.call = lambda *args, **kwargs: self.calls.append((args, kwargs))

    def test_close_while_scan_starting_releases_own_session(self):
        b = self.backend
        b.start_scan("adapter")
        self.assertTrue(b.scan_starting)
        b.stop_scan()
        self.calls[0][1]["done"](None)
        self.assertIsNone(b.scan_path)
        self.assertEqual(self.calls[-1][0], ("adapter", ADAPTER, "StopDiscovery"))

    def test_no_stop_for_another_clients_scan(self):
        self.backend.stop_scan()
        self.assertEqual(self.calls, [])

    def test_cancel_connect_ignores_late_completion(self):
        b = self.backend
        b.connect_device("dev")
        done = self.calls[0][1]["done"]
        b.disconnect_device("dev")
        done("Canceled")
        self.assertEqual(b.pending, {})
        self.assertEqual(self.errors, [])
        self.assertEqual(self.calls[-1][0], ("dev", DEVICE, "Disconnect"))

    def test_pair_cancel_does_not_trust_or_connect_late(self):
        b = self.backend
        b.devices["dev"].paired = False
        b.connect_device("dev")
        done = self.calls[0][1]["done"]
        b.disconnect_device("dev")
        done(None)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1][0], ("dev", DEVICE, "CancelPairing"))

    def test_error_clears_busy_and_allows_retry(self):
        b = self.backend
        b.connect_device("dev")
        self.calls[0][1]["done"]("Not available")
        self.assertNotIn("dev", b.pending)
        self.assertIn("dev", b.failures)
        b.connect_device("dev")
        self.assertIn("dev", b.pending)
        self.assertNotIn("dev", b.failures)


if __name__ == "__main__":
    unittest.main()
