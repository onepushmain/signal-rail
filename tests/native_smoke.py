"""Run on the desktop. Uses only simulated devices; no BlueZ mutation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signal_rail import App, Gtk, GLib, Gio

app = App(demo=True, force_window="--window" in sys.argv)
app.set_application_id("io.github.signalrail.Test")
result = []


def check():
    try:
        app.settings["notification_seconds"] = 0
        app.show_panel()
        if "--window" in sys.argv:
            assert not app.layer_shell
        app.device_event(app.backend.devices["keyboard"], True)
        app.device_event(app.backend.devices["speaker"], False)
        before = {p: d.connected for p, d in app.backend.devices.items()}
        toast = app.toasts[0]
        toast._right_click.emit("pressed", 1, 10.0, 10.0)
        assert len(app.toasts) == 1
        assert before == {p: d.connected for p, d in app.backend.devices.items()}
        app.panel._right_click.emit("pressed", 1, 10.0, 10.0)
        assert not app.panel.get_visible()
        app.toggle()
        assert app.panel.get_visible()
        app.backend.connect_device("speaker")
        assert "speaker" in app.backend.pending
        app.backend.disconnect_device("speaker")
        assert not app.backend.pending
        app.backend.power("demo", False)
        assert not any(d.connected for d in app.backend.devices.values())
        app.render()
        assert not app.scan_button.get_sensitive()
        app.backend.power("demo", True)
        app.render()
        assert app.scan_button.get_sensitive()
        app.backend.error("Simulated connection failure", "Speaker")
        assert app.last_error == "Simulated connection failure"
        assert app.provider.to_string()
        result.append("PASS: native right-click dismissal, connection invariants, panel toggle, cancellation, power states, error UI, CSS")
    except Exception as exc:
        result.append("FAIL: " + repr(exc))
    finally:
        app.quit()
    return False

app.connect("startup", lambda *_: GLib.idle_add(check))
app.run([sys.argv[0], "--daemon"])
print(result[0] if result else "FAIL: test did not run")
raise SystemExit(0 if result and result[0].startswith("PASS") else 1)
