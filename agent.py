"""Pairing agent scoped to pairing initiated by this application."""
from gi.repository import Gio, GLib

XML = '''<node><interface name="org.bluez.Agent1">
<method name="Release"/><method name="Cancel"/>
<method name="RequestPinCode"><arg type="o" direction="in"/><arg type="s" direction="out"/></method>
<method name="RequestPasskey"><arg type="o" direction="in"/><arg type="u" direction="out"/></method>
<method name="DisplayPinCode"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
<method name="DisplayPasskey"><arg type="o" direction="in"/><arg type="u" direction="in"/><arg type="q" direction="in"/></method>
<method name="RequestConfirmation"><arg type="o" direction="in"/><arg type="u" direction="in"/></method>
<method name="RequestAuthorization"><arg type="o" direction="in"/></method>
<method name="AuthorizeService"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
</interface></node>'''


class PairingAgent:
    def __init__(self, backend, prompt, clear):
        self.backend, self.prompt, self.clear = backend, prompt, clear
        self.path = "/io/github/signalrail/agent"
        self.invocation = None
        self.device = None
        self.registered = False
        self.registration = backend.bus.register_object(self.path,
            Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], self.method, None, None)
        backend.manager.connect("notify::name-owner", self.register)
        self.register()

    def register(self, *_):
        self.registered = False
        if not self.backend.manager.get_name_owner():
            self.cancel()
            return
        def done(err):
            self.registered = not bool(err)
            if err:
                self.backend.error("Pairing agent unavailable: " + err)
        self.backend.call("/org/bluez", "org.bluez.AgentManager1", "RegisterAgent",
                          GLib.Variant("(os)", (self.path, "KeyboardDisplay")), done)

    def cancel(self):
        if self.invocation:
            self.invocation.return_dbus_error("org.bluez.Error.Canceled", "Pairing dismissed")
            self.invocation = None
        self.device = None
        self.clear()

    def answer(self, accepted, value=None, numeric=False):
        invocation, self.invocation = self.invocation, None
        self.device = None
        self.clear()
        if not invocation:
            return
        if not accepted:
            invocation.return_dbus_error("org.bluez.Error.Rejected", "Pairing declined")
        else:
            reply = None if value is None else GLib.Variant("(u)" if numeric else "(s)", (int(value) if numeric else value,))
            invocation.return_value(reply)

    def method(self, _bus, sender, _path, _interface, method, parameters, invocation):
        if sender != self.backend.manager.get_name_owner():
            invocation.return_dbus_error("org.bluez.Error.Rejected", "Only BlueZ may call this agent")
            return
        args = parameters.unpack()
        if method in ("Release", "Cancel"):
            self.cancel()
            if method == "Release":
                self.registered = False
            invocation.return_value(None)
            return
        device = args[0]
        if device not in self.backend.pending:
            invocation.return_dbus_error("org.bluez.Error.Rejected", "No user-initiated pairing for this device")
            return
        if method in ("DisplayPinCode", "DisplayPasskey"):
            self.device = device
            code = str(args[1]) if method == "DisplayPinCode" else f"{args[1]:06d}"
            entered = args[2] if method == "DisplayPasskey" else 0
            self.prompt(device, "display", f"Type {code} on the device, then press Enter.", None, entered)
            invocation.return_value(None)
            return
        if self.invocation:
            self.cancel()
        self.invocation, self.device = invocation, device
        if method == "RequestConfirmation":
            self.prompt(device, "confirm", f"Does {args[1]:06d} match the code on your device?", None, 0)
        elif method in ("RequestPinCode", "RequestPasskey"):
            self.prompt(device, "numeric" if method == "RequestPasskey" else "pin", "Enter the pairing code shown by your device.", None, 0)
        elif method in ("RequestAuthorization", "AuthorizeService"):
            self.prompt(device, "confirm", "Allow this device to pair and connect?", None, 0)
        else:
            self.answer(False)
