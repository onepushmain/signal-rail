"""BlueZ integration. All mutations are async and initiated by user actions."""
from gi.repository import Gio, GLib
from model import Device, connection_events

DEVICE = "org.bluez.Device1"
ADAPTER = "org.bluez.Adapter1"
BATTERY = "org.bluez.Battery1"


class BlueZ:
    def __init__(self, changed, event, error):
        self.changed, self.event, self.error = changed, event, error
        self.devices, self.adapters, self.pending, self.failures = {}, {}, {}, {}
        self.scan_path = None
        self.scan_starting = False
        self.scan_wanted = False
        self.scan_timer = 0
        self.refresh_id = 0
        self.ready = False
        self.manager = Gio.DBusObjectManagerClient.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusObjectManagerClientFlags.DO_NOT_AUTO_START,
            "org.bluez", "/", None, None, None)
        self.bus = self.manager.get_connection()
        for signal in ("object-added", "object-removed", "interface-added", "interface-removed"):
            self.manager.connect(signal, self.schedule_refresh)
        self.manager.connect("interface-proxy-properties-changed", self.properties_changed)
        self.manager.connect("notify::name-owner", self.owner_changed)
        self.refresh()

    @staticmethod
    def props(proxy):
        return {n: proxy.get_cached_property(n).unpack() for n in proxy.get_cached_property_names() or []}

    def owner_changed(self, *_):
        self.ready = False
        self.pending.clear()
        self.scan_path = None
        self.scan_starting = self.scan_wanted = False
        self.schedule_refresh()

    def properties_changed(self, _manager, _obj, _proxy, values, invalidated):
        relevant = {"Alias", "Name", "Connected", "Paired", "Trusted", "Powered", "Discovering", "Percentage", "Icon"}
        if relevant.intersection(values.unpack()) or relevant.intersection(invalidated):
            self.schedule_refresh()

    def schedule_refresh(self, *_):
        if not self.refresh_id:
            self.refresh_id = GLib.timeout_add(80, self.refresh)

    def refresh(self):
        self.refresh_id = 0
        devices, adapters = {}, {}
        for obj in self.manager.get_objects():
            path = obj.get_object_path()
            adapter = obj.get_interface(ADAPTER)
            if adapter:
                adapters[path] = self.props(adapter)
            proxy = obj.get_interface(DEVICE)
            if proxy:
                p = self.props(proxy)
                battery = obj.get_interface(BATTERY)
                percentage = self.props(battery).get("Percentage") if battery else None
                devices[path] = Device(path, p.get("Alias", p.get("Address", "Bluetooth device")),
                    p.get("Adapter", ""), p.get("Icon", "bluetooth") + "-symbolic",
                    p.get("Paired", False), p.get("Connected", False), p.get("Trusted", False), percentage)
        if self.ready:
            for device, connected in connection_events(self.devices, devices):
                self.event(device, connected)
        self.devices, self.adapters = devices, adapters
        self.ready = bool(self.manager.get_name_owner())
        self.changed()
        return False

    def call(self, path, interface, method, args=None, done=None, timeout=20000):
        def finish(bus, result):
            try:
                bus.call_finish(result)
                err = None
            except GLib.Error as exc:
                err = exc.message.split("GDBus.Error:")[-1]
            if done:
                done(err)
            elif err:
                self.error(err)
        self.bus.call("org.bluez", path, interface, method, args, None,
                      Gio.DBusCallFlags.NONE, timeout, None, finish)

    def set_property(self, path, interface, name, value, done=None):
        self.call(path, "org.freedesktop.DBus.Properties", "Set",
                  GLib.Variant("(ssv)", (interface, name, GLib.Variant("b", value))), done)

    def power(self, path, enabled):
        if not enabled:
            self.stop_scan()
        self.set_property(path, ADAPTER, "Powered", enabled)

    def connect_device(self, path):
        device = self.devices.get(path)
        if not device or path in self.pending:
            return
        token = object()
        state = "Connecting" if device.paired else "Pairing"
        self.pending[path] = (state, token)
        self.failures.pop(path, None)
        self.changed()

        def complete(err):
            if self.pending.get(path, (None, None))[1] is not token:
                return
            self.pending.pop(path, None)
            if err:
                self.failures[path] = err
                self.error(err, device.name)
            self.schedule_refresh()

        def connect(err=None):
            if err:
                complete(err)
            elif self.pending.get(path, (None, None))[1] is token:
                self.pending[path] = ("Connecting", token)
                self.changed()
                self.call(path, DEVICE, "Connect", done=complete, timeout=45000)

        if device.paired:
            connect()
        else:
            def paired(err):
                if self.pending.get(path, (None, None))[1] is not token:
                    return
                if err:
                    complete(err)
                else:
                    self.set_property(path, DEVICE, "Trusted", True, connect)
            self.call(path, DEVICE, "Pair", done=paired, timeout=120000)

    def disconnect_device(self, path):
        if path in self.pending:
            state, _ = self.pending.pop(path)
            method = "CancelPairing" if state == "Pairing" else "Disconnect"
        else:
            method = "Disconnect"
        self.call(path, DEVICE, method, done=lambda err: self._disconnected(path, err))
        self.changed()

    def _disconnected(self, path, err):
        if err:
            self.error(err, self.devices.get(path, Device(path, "Device")).name)
        self.schedule_refresh()

    def start_scan(self, path):
        if self.scan_path or self.scan_starting:
            return
        self.scan_starting = self.scan_wanted = True
        self.changed()
        def started(err):
            self.scan_starting = False
            if err:
                self.scan_wanted = False
                self.error(err)
            else:
                self.scan_path = path
                if not self.scan_wanted:
                    self.stop_scan()
                else:
                    self.scan_timer = GLib.timeout_add_seconds(20, self.stop_scan)
            self.changed()
        self.call(path, ADAPTER, "StartDiscovery", done=started)

    def stop_scan(self):
        self.scan_wanted = False
        if self.scan_timer:
            GLib.source_remove(self.scan_timer)
            self.scan_timer = 0
        if self.scan_path:
            path, self.scan_path = self.scan_path, None
            self.call(path, ADAPTER, "StopDiscovery", done=lambda _err: None)
        self.changed()
        return False


class DemoBlueZ:
    """Isolated demo backend: never opens the system bus."""
    def __init__(self, changed, event, error):
        self.changed, self.event, self.error = changed, event, error
        self.adapters = {"demo": {"Alias": "Demo adapter", "Powered": True}}
        self.devices = {d.path: d for d in [
            Device("headphones", "Studio headphones", "demo", "audio-headphones-symbolic", True, True, True, 82),
            Device("keyboard", "Keychron keyboard", "demo", "input-keyboard-symbolic", True, True, True, 64),
            Device("speaker", "Living room speaker", "demo", "audio-speakers-symbolic", True)]}
        self.pending, self.failures = {}, {}
        self.scan_path = None
        self.scan_starting = False
        self.ready = True
    def connect_device(self, path):
        token = object()
        self.pending[path] = ("Connecting", token)
        self.failures.pop(path, None)
        self.changed()
        def done():
            if self.pending.get(path, (None, None))[1] is token:
                self.pending.pop(path)
                self.devices[path].connected = True
                self.event(self.devices[path], True)
                self.changed()
            return False
        GLib.timeout_add(900, done)
    def disconnect_device(self, path):
        self.pending.pop(path, None)
        was = self.devices[path].connected
        self.devices[path].connected = False
        if was:
            self.event(self.devices[path], False)
        self.changed()
    def power(self, path, enabled):
        self.adapters[path]["Powered"] = enabled
        if not enabled:
            self.pending.clear()
            for device in self.devices.values():
                device.connected = False
        self.changed()
    def start_scan(self, path):
        self.scan_path = path
        self.changed()
        GLib.timeout_add_seconds(3, self.stop_scan)
    def stop_scan(self):
        self.scan_path = None
        self.changed()
        return False
