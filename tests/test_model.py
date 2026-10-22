import tempfile
from pathlib import Path
import unittest
from model import Device, connection_events, contrast, load_settings, read_palette, valid_pin


class ModelTests(unittest.TestCase):
    def test_initial_and_discovery_do_not_notify(self):
        self.assertEqual(connection_events({}, {"a": Device("a", "Keyboard", connected=True)}), [])

    def test_connection_changes_and_removed_device(self):
        off = Device("a", "Keyboard")
        on = Device("a", "Keyboard", connected=True)
        self.assertEqual(connection_events({"a": off}, {"a": on}), [(on, True)])
        self.assertEqual(connection_events({"a": on}, {"a": off}), [(off, False)])
        self.assertEqual(connection_events({"a": on}, {}), [(on, False)])
        self.assertEqual(connection_events({"a": on}, {"a": on}), [])

    def test_theme_modes_and_readability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "waybar").mkdir()
            file = root / "waybar/theme.css"
            file.write_text("@define-color main-bg #f5f5f5;\n@define-color main-fg #eeeeee;\n@define-color wb-act-bg #ccddee;")
            p = read_palette(root)
            self.assertEqual(p["bg"], "#f5f5f5")
            self.assertEqual(p["accent"], "#ccddee")
            self.assertGreaterEqual(contrast(p["fg"], p["bg"]), 4.5)
            self.assertGreaterEqual(contrast(p["accent_text"], p["bg"]), 4.5)
            self.assertGreaterEqual(contrast(p["on_accent"], p["accent"]), 4.5)
            file.write_text("@define-color main-bg #110524;\n@define-color wb-act-bg #50C878;")
            self.assertEqual(read_palette(root)["accent"], "#50C878")
            file.unlink()
            self.assertTrue(read_palette(root)["bg"].startswith("#"))

    def test_hypr_palette_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hypr/themes").mkdir(parents=True)
            (root / "hypr/themes/colors.conf").write_text("$wallbash_pry1 = 123456\n$wallbash_2xa7 = aabbcc\n")
            self.assertEqual(read_palette(root)["bg"], "#123456")
            self.assertEqual(read_palette(root)["accent"], "#aabbcc")

    def test_pin_validation(self):
        for pin in ("000001", "0", "999999"):
            self.assertTrue(valid_pin(pin, True))
        for pin in ("", "1234567", "12a", "١٢٣", "-1"):
            self.assertFalse(valid_pin(pin, True))
        self.assertTrue(valid_pin("aBc123", False))
        self.assertFalse(valid_pin("bad\ncode", False))

    def test_custom_palette_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "signal-rail").mkdir()
            external = root / "signal-rail/palette.json"
            external.write_text('{"accent":"#00aaff","bg":"#111111"}')
            settings = {"theme": "custom", "palette_file": "palette.json", "palette": {"fg":"#ffffff"}}
            self.assertEqual(read_palette(root, settings)["accent"], "#00aaff")
            replacement = external.with_suffix(".new")
            replacement.write_text('{"accent":"#ff5500"}')
            replacement.replace(external)
            self.assertEqual(read_palette(root, settings)["accent"], "#ff5500")
            external.write_text('{"bg":"red; injected css", "accent":123}')
            self.assertEqual(read_palette(root, settings)["bg"], "#11161c")

    def test_presets_ignore_hyde_and_system_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "waybar").mkdir()
            (root / "waybar/theme.css").write_text("@define-color wb-act-bg #ff0000;")
            self.assertEqual(read_palette(root, {"theme":"ice"})["accent"], "#7AD8F0")
            self.assertEqual(read_palette(root, {"theme":"system"}, {"accent":"#123456"})["accent"], "#123456")

    def test_invalid_settings_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "signal-rail").mkdir()
            file = root / "signal-rail/config.json"
            for data in ('[]', 'null', '{"theme":[],"notification_seconds":true}', '{broken'):
                file.write_text(data)
                self.assertEqual(load_settings(root)["theme"], "auto")
                self.assertEqual(load_settings(root)["notification_seconds"], 8)


if __name__ == "__main__":
    unittest.main()
