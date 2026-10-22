#!/usr/bin/python3
"""Signal rail: a native Linux Bluetooth panel and event notifications."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys

from ui import PanelUI, Gdk, Gio, GLib, Gtk, GtkLayerShell, add_unix_signal
from backend import BlueZ, DemoBlueZ
from agent import PairingAgent
from model import VERSION, load_settings, read_palette

ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


class App(PanelUI, Gtk.Application):
    def __init__(self, demo=False, force_window=False):
        super().__init__(application_id="io.github.signalrail.Demo" if demo else "io.github.signalrail.Bluetooth",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.demo = demo
        self.force_window = force_window
        self.layer_shell = False
        self.backend = self.agent = self.panel = None
        self.toasts = []
        self.toast_window = None
        self.palette = None
        self.provider = Gtk.CssProvider()
        self.adapter_path = None
        self.rendering = False
        self.render_id = 0
        self.prompt_path = None
        self.last_error = ""
        self.settings = load_settings(CONFIG)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        self.layer_shell = bool(GtkLayerShell and not self.force_window and
            self.settings["display_mode"] != "window" and GtkLayerShell.is_supported())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.reload_palette()
        GLib.timeout_add_seconds(2, self.reload_palette)
        self.create_panel()
        try:
            self.backend = (DemoBlueZ if self.demo else BlueZ)(self.schedule_render, self.device_event, self.error)
            if not self.demo:
                self.agent = PairingAgent(self.backend, self.pairing_prompt, self.clear_prompt)
        except GLib.Error as exc:
            self.last_error = "Bluetooth unavailable: " + exc.message
            print(self.last_error, file=sys.stderr)
        self.render()
        add_unix_signal(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.shutdown_app)
        add_unix_signal(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.shutdown_app)

    def do_command_line(self, command):
        args = command.get_arguments()[1:]
        if "--quit" in args:
            self.shutdown_app()
        elif "--status" in args:
            status = self.status()
            command.print_literal(json.dumps(status) + "\n")
            if not command.get_is_remote():
                self.quit()
        elif "--demo-notify" in args:
            if self.demo:
                self.device_event(self.backend.devices["headphones"], True)
                self.device_event(self.backend.devices["speaker"], False)
        elif "--show" in args:
            self.show_panel()
        elif "--hide" in args:
            self.close_panel()
        elif "--daemon" not in args:
            self.toggle()
        return 0

    def status(self):
        return dict(version=VERSION, demo=self.demo, display_mode="layer-shell" if self.layer_shell else "window",
                    visible=bool(self.panel and self.panel.get_visible()),
                    pairing_agent_ready=bool(self.agent and self.agent.registered),
                    palette=self.palette, devices=[dict(name=d.name, connected=d.connected, paired=d.paired, battery=d.battery)
                    for d in self.backend.devices.values()] if self.backend else [],
                    notifications=len(self.toasts), error=self.last_error)

    def shutdown_app(self):
        if self.agent:
            self.agent.cancel()
        if self.backend:
            self.backend.stop_scan()
        self.quit()
        return False

    def reload_palette(self):
        self.settings.update(load_settings(CONFIG))
        palette = read_palette(CONFIG, self.settings, self.system_palette())
        if palette != self.palette:
            content = "\n".join(f"@define-color {key} {value};" for key, value in palette.items())
            content += "\n" + (ROOT / "style.css").read_text()
            try:
                self.provider.load_from_data(content.encode())
                self.palette = palette
            except GLib.Error as exc:
                print("Palette CSS:", exc, file=sys.stderr)
            for widget in (self.shell if self.panel else None, self.toast_box if self.toast_window else None):
                if widget:
                    widget.queue_draw()
        return True

    def system_palette(self):
        # A detached context avoids feeding our own CSS back into the next reload.
        context = Gtk.StyleContext()
        path = Gtk.WidgetPath()
        path.append_type(Gtk.Window)
        context.set_path(path)
        result = {}
        for key, names in {"bg": ("theme_bg_color",), "fg": ("theme_fg_color",),
                           "accent": ("theme_selected_bg_color",),
                           "secondary": ("borders", "theme_unfocused_selected_bg_color"),
                           "warning": ("warning_color",)}.items():
            for name in names:
                found, rgba = context.lookup_color(name)
                if found and rgba.alpha > .9:
                    result[key] = "#" + "".join(f"{round(c * 255):02x}" for c in (rgba.red, rgba.green, rgba.blue))
                    break
        return result



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("demo", "daemon", "status", "quit", "demo-notify", "window", "show", "hide"):
        parser.add_argument("--" + flag, action="store_true")
    parser.add_argument("--version", action="version", version="Signal rail " + VERSION)
    args = parser.parse_args()
    app = App(demo=args.demo, force_window=args.window)
    raise SystemExit(app.run(sys.argv))
