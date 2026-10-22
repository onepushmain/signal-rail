#!/usr/bin/env python3
"""Per-user install/uninstall. No root, packages, or desktop config edits."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


class Installer:
    def __init__(self):
        home = Path.home()
        self.data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
        self.config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        self.state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "signal-rail"
        self.bin = home / ".local/bin/signal-rail"
        self.manifest_path = self.state / "install-manifest.json"
        try:
            self.manifest = json.loads(self.manifest_path.read_text())
        except FileNotFoundError:
            self.manifest = {}
        self.backup = self.state / "installer-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.changed = []

    def write(self, path, text, executable=False):
        path = Path(path)
        key = str(path)
        if key not in self.manifest:
            record = {"backup": None}
            if path.exists():
                backup = self.backup / hashlib.sha256(key.encode()).hexdigest()
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
                record["backup"] = str(backup)
            self.manifest[key] = record
        if not path.exists() or path.read_text() != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            self.changed.append(key)
        if executable:
            path.chmod(0o755)
        self.manifest[key]["sha256"] = digest(path)

    def save(self):
        self.state.mkdir(parents=True, exist_ok=True)
        temp = self.manifest_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.manifest, indent=2) + "\n")
        temp.replace(self.manifest_path)

    def install(self, autostart=False):
        dest = self.data / "signal-rail"
        for name in ("signal_rail.py", "ui.py", "model.py", "backend.py", "agent.py", "style.css", "LICENSE"):
            self.write(dest / name, (ROOT / name).read_text())
        self.write(self.bin, '#!/bin/sh\nexec /usr/bin/python3 ' + shlex.quote(str(dest / "signal_rail.py")) + ' "$@"\n', True)
        desktop = (ROOT / "data/io.github.signalrail.Bluetooth.desktop").read_text().replace("Exec=signal-rail --show", "Exec=" + desktop_quote(self.bin) + " --show")
        self.write(self.data / "applications/io.github.signalrail.Bluetooth.desktop", desktop)
        self.write(self.data / "icons/hicolor/scalable/apps/io.github.signalrail.Bluetooth.svg", (ROOT / "data/icon.svg").read_text())
        executable = '"' + str(self.bin).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'
        self.write(self.config / "systemd/user/signal-rail.service", f'''[Unit]
Description=Signal rail Bluetooth panel and notifications
PartOf=graphical-session.target

[Service]
Type=dbus
BusName=io.github.signalrail.Bluetooth
ExecStart={executable} --daemon
Restart=on-failure
RestartSec=3
''')
        settings = self.config / "signal-rail/config.json"
        if not settings.exists():
            self.write(settings, (ROOT / "data/config.json").read_text())
        if autostart:
            self.write(self.config / "autostart/io.github.signalrail.Bluetooth.desktop",
                       desktop.replace(" --show", " --daemon").replace("Name=Signal rail", "Name=Signal rail notifications"))
        self.save()
        print(f"Installed: {self.bin}\nApplication menu: Signal rail\nManifest: {self.manifest_path}")
        print("Desktop/bar settings were not modified. See examples/ for optional integration.")

    def uninstall(self):
        conflicts = []
        for key, record in list(self.manifest.items()):
            path = Path(key)
            if not path.exists():
                del self.manifest[key]
                continue
            if digest(path) != record["sha256"]:
                conflicts.append(key)
                continue
            if record["backup"]:
                shutil.copy2(record["backup"], path)
            else:
                path.unlink()
            del self.manifest[key]
        self.save()
        print("Removed unchanged installed files; restored any files from before installation.")
        if conflicts:
            print("Preserved locally modified files:\n" + "\n".join(conflicts))
        print("Stop any running app separately with signal-rail --quit before uninstalling.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--autostart", action="store_true", help="opt in to XDG session autostart")
    parser.add_argument("--uninstall", action="store_true", help="remove unchanged managed files, preserving edits")
    args = parser.parse_args()
    installer = Installer()
    if args.uninstall:
        installer.uninstall()
    else:
        installer.install(args.autostart)


if __name__ == "__main__":
    main()
