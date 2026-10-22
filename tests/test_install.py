from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from install import Installer


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="signal rail ")
        self.root = Path(self.tmp.name)
        self.home_patch = patch("pathlib.Path.home", return_value=self.root)
        self.home_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_STATE_HOME": str(self.root / "state")})
        self.env_patch.start()
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()

    def tearDown(self):
        self.out.__exit__(None, None, None)
        self.env_patch.stop()
        self.home_patch.stop()
        self.tmp.cleanup()

    def test_clean_install_without_hyde_or_waybar(self):
        installer = Installer()
        installer.install()
        self.assertTrue(installer.bin.stat().st_mode & 0o111)
        self.assertTrue((self.root / "data/applications/io.github.signalrail.Bluetooth.desktop").exists())
        self.assertFalse((self.root / "config/hypr").exists())
        self.assertFalse((self.root / "config/waybar").exists())
        self.assertFalse((self.root / "config/autostart").exists())
        self.assertIn("'", installer.bin.read_text())  # executable path with spaces is shell-quoted
        unit = (self.root / "config/systemd/user/signal-rail.service").read_text()
        self.assertNotIn("GDK_BACKEND=wayland", unit)
        Installer().uninstall()
        self.assertFalse(installer.bin.exists())
        self.assertFalse((self.root / "data/signal-rail/signal_rail.py").exists())

    def test_update_preserves_settings_and_uninstall_preserves_edits(self):
        first = Installer()
        first.install(True)
        config = self.root / "config/signal-rail/config.json"
        config.write_text('{"theme":"ice"}\n')
        Installer().install()
        self.assertEqual(config.read_text(), '{"theme":"ice"}\n')
        Installer().uninstall()
        self.assertTrue(config.exists())
        self.assertFalse((self.root / "config/autostart/io.github.signalrail.Bluetooth.desktop").exists())

    def test_restore_preexisting_launcher(self):
        file = self.root / ".local/bin/signal-rail"
        file.parent.mkdir(parents=True)
        file.write_text("original launcher\n")
        Installer().install()
        Installer().install()
        Installer().uninstall()
        self.assertEqual(file.read_text(), "original launcher\n")
