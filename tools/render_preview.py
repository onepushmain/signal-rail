"""Render actual GTK widgets with simulated data, without capturing a desktop."""
import sys
from pathlib import Path
import tempfile
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cairo
import signal_rail
from gi.repository import GLib

target = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/preview.png").resolve()
temporary = tempfile.TemporaryDirectory()
signal_rail.CONFIG = Path(temporary.name)
(signal_rail.CONFIG / "signal-rail").mkdir()
(signal_rail.CONFIG / "signal-rail/config.json").write_text(json.dumps({"theme":"evangelion", "notification_seconds":0}))
app = signal_rail.App(demo=True, force_window=True)
app.set_application_id("io.github.signalrail.Preview")
failure = []


def render():
    try:
        panel = app.shell
        notifications = app.toast_box
        pw, ph = panel.get_allocated_width(), panel.get_allocated_height()
        nw, nh = notifications.get_allocated_width(), notifications.get_allocated_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pw + nw + 96, max(ph, nh) + 64)
        cr = cairo.Context(surface)
        cr.set_source_rgb(.045, .035, .065)
        cr.paint()
        cr.save()
        cr.translate(32, 32)
        panel.draw(cr)
        cr.restore()
        cr.translate(pw + 64, 32)
        notifications.draw(cr)
        target.parent.mkdir(parents=True, exist_ok=True)
        surface.write_to_png(str(target))
        print(target)
    except Exception as exc:
        failure.append(exc)
    finally:
        app.quit()
    return False


def prepare():
    app.show_panel()
    app.panel.resize(380, 620)
    app.device_event(app.backend.devices["headphones"], True)
    app.device_event(app.backend.devices["speaker"], False)
    GLib.timeout_add(400, render)
    return False


app.connect("startup", lambda *_: GLib.idle_add(prepare))
app.run([sys.argv[0], "--daemon"])
temporary.cleanup()
if failure:
    raise failure[0]
