# Design notes

Signal rail is a compact desktop Bluetooth utility. Its visual identity is a
vertical status rail, cut corners, restrained typography, and adaptive colors.
Device state must remain understandable without relying on color alone.

Keep desktop integrations optional. BlueZ owns device state; operations use async
D-Bus calls and report failures. The pairing agent handles only requests tied to
user-initiated pairing and does not replace the system's default agent.

Use layer shell only where available. A normal GTK window is the portability
fallback. Themes come from desktop colors, presets, or validated JSON palettes.
Never modify someone's bar/compositor config as part of the default install.

Popup dismissal must not change device connections. Notifications expire after
eight seconds by default; manual-only dismissal is configurable. Battery values
are displayed only when BlueZ provides them. Scan sessions are owned by this app
and stop after 20 seconds or when its panel closes.
