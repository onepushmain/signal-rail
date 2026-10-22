# Contributing

Use your distribution's Python with PyGObject installed. From the repository:

```sh
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 tests/native_smoke.py
```

The native smoke test uses simulated devices. To check the no-layer-shell path:

```sh
xvfb-run -a dbus-run-session -- env GDK_BACKEND=x11 SIGNAL_RAIL_DISABLE_LAYER_SHELL=1 /usr/bin/python3 tests/native_smoke.py --window
```

For bug reports, include distro, desktop/compositor, Python/GTK/GLib versions,
whether the problem occurs in `signal-rail --demo`, and relevant error output.
`signal-rail --status` includes device names; redact those before sharing if needed.
Don't include Bluetooth addresses, passkeys, or unrelated desktop screenshots.

Hardware tests should use a spare device. Verify pairing, cancellation, reconnect,
power changes, and notifications. Do not interrupt an active input device just
to run a test. New backends or desktop integrations should remain optional.
