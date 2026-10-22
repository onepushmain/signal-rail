"""GTK widget construction, pairing prompts, and notification presentation."""
import os
import shutil
import sys
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango
try:
    from gi.repository import GLibUnix
    add_unix_signal = GLibUnix.signal_add
except ImportError:
    add_unix_signal = GLib.unix_signal_add
try:
    if os.environ.get("SIGNAL_RAIL_DISABLE_LAYER_SHELL") == "1":
        raise ImportError("Layer shell disabled")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except (ValueError, ImportError):
    GtkLayerShell = None
from model import valid_pin


def css(widget, *classes):
    for name in classes:
        widget.get_style_context().add_class(name)
    return widget


def label(text, style=None, wrap=False):
    widget = Gtk.Label(label=text, xalign=0)
    if style:
        css(widget, style)
    if wrap:
        widget.set_line_wrap(True)
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        widget.set_max_width_chars(37)
    return widget


def button(text, callback, style=None):
    widget = Gtk.Button(label=text)
    if style:
        css(widget, style)
    widget.connect("clicked", lambda *_: callback())
    return widget


def box(vertical=True, spacing=0):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)


class PanelUI:
    def window(self, namespace, keyboard=False):
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("Signal rail")
        window.set_decorated(not self.layer_shell and keyboard)
        window.set_resizable(not self.layer_shell and keyboard)
        window.set_app_paintable(True)
        visual = window.get_screen().get_rgba_visual()
        if visual:
            window.set_visual(visual)
        css(window, "signal-rail")
        if self.layer_shell:
            GtkLayerShell.init_for_window(window)
            GtkLayerShell.set_namespace(window, namespace)
            GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, self.settings["top_margin"])
            GtkLayerShell.set_margin(window, GtkLayerShell.Edge.RIGHT, self.settings["right_margin"])
            GtkLayerShell.set_exclusive_zone(window, 0)
            GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.ON_DEMAND if keyboard else GtkLayerShell.KeyboardMode.NONE)
        else:
            window.set_position(Gtk.WindowPosition.CENTER)
            if not keyboard:
                window.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
                window.set_skip_taskbar_hint(True)
                window.set_accept_focus(False)
                window.set_focus_on_map(False)
                window.set_keep_above(True)
        return window

    @staticmethod
    def right_click(widget, callback):
        gesture = Gtk.GestureMultiPress.new(widget)
        gesture.set_button(3)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect("pressed", lambda *_: callback())
        widget._right_click = gesture

    def create_panel(self):
        self.panel = self.window("signal-rail", True)
        self.panel.set_default_size(380, -1)
        self.panel.connect("delete-event", lambda *_: self.close_panel())
        self.panel.connect("key-press-event", self.key_press)
        self.right_click(self.panel, self.close_panel)
        self.shell = css(box(spacing=0), "shell")
        self.shell.connect("draw", self.draw_shell, False)
        self.panel.add(self.shell)
        head = box(False, 12)
        head.pack_start(label("Signal rail", "heading"), True, True, 0)
        self.power = Gtk.Switch()
        self.power.set_valign(Gtk.Align.CENTER)
        self.power.get_accessible().set_name("Bluetooth power")
        self.power.connect("state-set", self.power_changed)
        head.pack_start(self.power, False, False, 0)
        close = button("×", self.close_panel, "close")
        close.get_accessible().set_name("Close Bluetooth panel")
        head.pack_start(close, False, False, 0)
        self.shell.pack_start(head, False, False, 0)
        self.subtitle = label("Bluetooth", "muted")
        self.subtitle.set_margin_top(8)
        self.shell.pack_start(self.subtitle, False, False, 0)
        self.adapter_picker = Gtk.ComboBoxText()
        self.adapter_picker.connect("changed", self.choose_adapter)
        self.shell.pack_start(self.adapter_picker, False, False, 8)
        self.prompt_box = box()
        self.shell.pack_start(self.prompt_box, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        scroll.set_min_content_width(330)
        scroll.set_max_content_height(410)
        self.rows = box()
        scroll.add(self.rows)
        self.shell.pack_start(scroll, True, True, 0)
        self.scan_button = button("Scan for devices", self.scan, "scan")
        self.shell.pack_start(self.scan_button, False, False, 0)
        self.message = label("", "muted", True)
        self.message.set_margin_top(12)
        self.shell.pack_start(self.message, False, False, 0)
        footer = box(False)
        footer.pack_start(label("Right-click or Esc to close", "muted"), True, True, 0)
        if shutil.which("blueman-manager"):
            footer.pack_end(button("Advanced", self.advanced, "action"), False, False, 0)
        footer.set_margin_top(12)
        self.shell.pack_start(footer, False, False, 0)

    def draw_shell(self, widget, cr, warning):
        """GTK CSS cannot express chamfers; paint the silhouette natively."""
        if not self.palette:
            return False
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        def color(name):
            rgba = Gdk.RGBA()
            rgba.parse(self.palette[name])
            Gdk.cairo_set_source_rgba(cr, rgba)
        cr.move_to(.5, .5)
        cr.line_to(width - 15, .5)
        cr.line_to(width - .5, 15)
        cr.line_to(width - .5, height - .5)
        cr.line_to(15, height - .5)
        cr.line_to(.5, height - 15)
        cr.close_path()
        color("bg")
        cr.fill_preserve()
        color("secondary")
        cr.set_line_width(1)
        cr.stroke()
        color("warning" if warning else "accent")
        cr.set_line_width(4)
        cr.move_to(2, 1)
        cr.line_to(2, height - 16)
        cr.stroke()
        return False

    def key_press(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close_panel()
            return True
        return False

    def toggle(self):
        if self.panel.get_visible():
            self.close_panel()
        else:
            self.show_panel()

    def show_panel(self):
        self.panel.show_all()
        self.render()
        self.position_toasts()
        self.panel.present()

    def close_panel(self):
        self.panel.hide()
        if self.agent and self.agent.device:
            path = self.agent.device
            self.agent.cancel()
            if path in self.backend.pending:
                self.backend.disconnect_device(path)
        if self.backend:
            self.backend.stop_scan()
        self.position_toasts()
        return True

    def advanced(self):
        try:
            Gio.Subprocess.new(["blueman-manager"], Gio.SubprocessFlags.NONE)
            self.close_panel()
        except GLib.Error as exc:
            self.error(exc.message)

    def schedule_render(self):
        if not self.render_id:
            self.render_id = GLib.idle_add(self.render)

    def render(self):
        self.render_id = 0
        if not self.panel:
            return False
        self.rendering = True
        backend = self.backend
        adapters = backend.adapters if backend else {}
        if self.adapter_path not in adapters:
            self.adapter_path = next((p for p, a in adapters.items() if a.get("Powered")), next(iter(adapters), None))
        self.adapter_picker.remove_all()
        for path, adapter in adapters.items():
            self.adapter_picker.append(path, adapter.get("Alias", path.rsplit("/", 1)[-1]))
        if self.adapter_path:
            self.adapter_picker.set_active_id(self.adapter_path)
        self.adapter_picker.set_visible(len(adapters) > 1)
        powered = bool(adapters.get(self.adapter_path, {}).get("Powered"))
        self.power.set_sensitive(bool(adapters))
        self.power.set_active(powered)
        self.power.set_state(powered)
        self.subtitle.set_text("Demo · Bluetooth" if self.demo else "Bluetooth · " + ("On" if powered else "Off"))
        for child in self.rows.get_children():
            child.destroy()
        if not backend or not backend.ready:
            self.rows.pack_start(label("Bluetooth service unavailable. Start bluetooth.service and try again.", "muted", True), False, False, 20)
        elif not adapters:
            self.rows.pack_start(label("No Bluetooth adapter found.", "muted"), False, False, 20)
        elif not powered:
            self.rows.pack_start(label("Bluetooth is off. Turn it on to connect your devices.", "muted", True), False, False, 20)
        else:
            devices = sorted((d for d in backend.devices.values() if d.adapter == self.adapter_path), key=lambda d: (not d.connected, not d.paired, d.name.casefold()))
            groups = [("Your devices", [d for d in devices if d.paired or d.connected]), ("Nearby devices", [d for d in devices if not d.paired and not d.connected])]
            for title, members in groups:
                if members:
                    self.rows.pack_start(label(title, "section"), False, False, 0)
                    for device in members:
                        self.rows.pack_start(self.device_row(device), False, False, 0)
            if not devices:
                self.rows.pack_start(label("No devices yet. Put your device in pairing mode, then scan.", "muted", True), False, False, 20)
        scanning = bool(backend and (backend.scan_path or backend.scan_starting))
        self.scan_button.set_sensitive(powered)
        self.scan_button.set_label("Stop scanning" if scanning else "Scan for devices")
        self.message.set_text(self.last_error or ("Scanning nearby devices…" if scanning else ""))
        self.message.set_visible(bool(self.message.get_text()))
        self.rows.show_all()
        self.rendering = False
        if self.prompt_path and backend and self.prompt_path not in backend.pending:
            if self.agent:
                self.agent.cancel()
            else:
                self.clear_prompt()
        return False

    def device_row(self, device):
        row = css(box(spacing=8), "device")
        top = box(False, 10)
        top.pack_start(css(label("▪", "rail-dot"), *( [] if device.connected else ["offline"])), False, False, 0)
        icon = css(Gtk.Image.new_from_icon_name(device.icon, Gtk.IconSize.LARGE_TOOLBAR), "device-icon")
        top.pack_start(icon, False, False, 0)
        name = label(device.name, "device-name")
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_max_width_chars(21)
        name.set_tooltip_text(device.name)
        top.pack_start(name, True, True, 0)
        if device.connected and device.battery is not None:
            top.pack_end(label(f"{device.battery}%", "battery"), False, False, 0)
        row.pack_start(top, False, False, 0)
        bottom = box(False, 7)
        bottom.set_margin_start(31)
        pending = self.backend.pending.get(device.path)
        failed = device.path in self.backend.failures
        state = pending[0] + "…" if pending else "Connected" if device.connected else "Failed" if failed else "Disconnected" if device.paired else "Available"
        badge = css(label(state, "badge"), "connected" if device.connected and not pending else "warning" if failed else "muted")
        bottom.pack_start(badge, False, False, 0)
        if failed:
            badge.set_tooltip_text(self.backend.failures[device.path])
        action = "Cancel" if pending else "Disconnect" if device.connected else "Retry" if failed else "Connect" if device.paired else "Pair"
        control = button(action, lambda: self.device_action(device.path), "action")
        control.get_accessible().set_name(f"{action} {device.name}")
        bottom.pack_end(control, False, False, 0)
        row.pack_start(bottom, False, False, 0)
        return row

    def device_action(self, path):
        device = self.backend.devices.get(path)
        if not device:
            return
        self.last_error = ""
        if device.connected or path in self.backend.pending:
            self.backend.disconnect_device(path)
        elif not device.paired and self.agent and not self.agent.registered:
            self.error("Pairing agent is not ready. Try again in a moment.")
        else:
            self.backend.connect_device(path)

    def power_changed(self, _switch, state):
        if not self.rendering and self.backend and self.adapter_path:
            self.last_error = ""
            self.backend.power(self.adapter_path, state)
        return True

    def choose_adapter(self, picker):
        if not self.rendering:
            self.backend.stop_scan()
            self.adapter_path = picker.get_active_id()
            self.schedule_render()

    def scan(self):
        if not self.backend or not self.adapter_path:
            return
        self.last_error = ""
        if self.backend.scan_path or self.backend.scan_starting:
            self.backend.stop_scan()
        else:
            self.backend.start_scan(self.adapter_path)

    def error(self, text, device="Bluetooth"):
        self.last_error = text
        print(text, file=sys.stderr)
        self.toast(device, "Could not complete action", text, True)
        self.schedule_render()

    def device_event(self, device, connected):
        self.toast(device.name, "Connected" if connected else "Disconnected",
                   "Ready to use." if connected else "Device connection ended.", not connected)

    def toast(self, title, state, detail, warning=False):
        if not self.toast_window:
            self.toast_window = self.window("signal-rail-notifications")
            self.toast_box = box(spacing=12)
            self.toast_window.add(self.toast_box)
        event = Gtk.EventBox()
        event.set_visible_window(False)
        shell = css(box(spacing=8), "shell", "toast")
        shell.connect("draw", self.draw_shell, warning)
        if warning:
            css(shell, "warning-shell")
        event.add(shell)
        head = box(False, 12)
        name = label(title, "toast-title")
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_max_width_chars(25)
        head.pack_start(name, True, True, 0)
        head.pack_end(button("×", lambda: self.dismiss(event), "close"), False, False, 0)
        shell.pack_start(head, False, False, 0)
        shell.pack_start(label(state, "warning" if warning else "connected"), False, False, 0)
        shell.pack_start(label(detail, "muted", True), False, False, 0)
        shell.pack_start(label("Right-click to dismiss", "muted"), False, False, 0)
        event.set_size_request(340, -1)
        self.right_click(event, lambda: self.dismiss(event))
        self.toast_box.pack_start(event, False, False, 0)
        self.toasts.append(event)
        event._expiry = 0
        while len(self.toasts) > 3:
            self.dismiss(self.toasts[0])
        seconds = self.settings["notification_seconds"]
        if seconds:
            def expire():
                event._expiry = 0
                self.dismiss(event)
                return False
            event._expiry = GLib.timeout_add_seconds(seconds, expire)
        self.position_toasts()
        self.toast_window.show_all()

    def dismiss(self, event):
        if event not in self.toasts:
            return
        if event._expiry:
            GLib.source_remove(event._expiry)
        self.toasts.remove(event)
        event.destroy()
        if not self.toasts:
            self.toast_window.hide()

    def position_toasts(self):
        if self.toast_window and self.layer_shell:
            offset = 400 if self.panel.get_visible() else 0
            GtkLayerShell.set_margin(self.toast_window, GtkLayerShell.Edge.RIGHT, self.settings["right_margin"] + offset)

    def clear_prompt(self):
        self.prompt_path = None
        for child in self.prompt_box.get_children():
            child.destroy()

    def pairing_prompt(self, path, kind, text, _unused, entered):
        self.clear_prompt()
        self.prompt_path = path
        prompt = css(box(spacing=10), "prompt")
        device = self.backend.devices.get(path)
        prompt.pack_start(label("Pair " + (device.name if device else "device"), "device-name"), False, False, 0)
        prompt.pack_start(label(text, wrap=True), False, False, 0)
        entry = None
        if kind in ("pin", "numeric"):
            entry = Gtk.Entry()
            entry.set_max_length(6 if kind == "numeric" else 16)
            entry.set_input_purpose(Gtk.InputPurpose.DIGITS if kind == "numeric" else Gtk.InputPurpose.FREE_FORM)
            prompt.pack_start(entry, False, False, 0)
        if kind == "display" and entered:
            prompt.pack_start(label(f"{entered} digits entered", "muted"), False, False, 0)
        actions = box(False, 10)
        def reject():
            self.agent.cancel()
            self.backend.disconnect_device(path)
        actions.pack_start(button("Cancel", reject), False, False, 0)
        if kind != "display":
            def accept():
                value = entry.get_text() if entry else None
                if entry and not valid_pin(value, kind == "numeric"):
                    entry.set_placeholder_text("Enter a valid pairing code")
                    return
                self.agent.answer(True, value, kind == "numeric")
            actions.pack_end(button("Confirm", accept, "primary"), False, False, 0)
            if entry:
                entry.connect("activate", lambda *_: accept())
        prompt.pack_start(actions, False, False, 0)
        self.prompt_box.pack_start(prompt, False, False, 0)
        self.show_panel()
        if entry:
            entry.grab_focus()
