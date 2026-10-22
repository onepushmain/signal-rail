"""Pure state/palette helpers, independent of GTK and the Bluetooth bus."""
from dataclasses import dataclass
from pathlib import Path
import json
import re

VERSION = "0.1.0"
DEFAULT_SETTINGS = {"notification_seconds": 8, "top_margin": 16, "right_margin": 20,
                    "display_mode": "auto", "theme": "auto", "palette_file": "", "palette": {}}
PRESETS = {
    "noir": {"bg": "#11161c", "fg": "#dce5ea", "accent": "#72e0c4", "secondary": "#405367", "warning": "#f4bb7e"},
    "evangelion": {"bg": "#110524", "fg": "#C5C8D6", "accent": "#50C878", "secondary": "#6B3FA0", "warning": "#FF9944"},
    "ice": {"bg": "#091923", "fg": "#D4E4EF", "accent": "#7AD8F0", "secondary": "#527EA1", "warning": "#FFB67A"},
    "ember": {"bg": "#21110E", "fg": "#F0DED3", "accent": "#F5AC78", "secondary": "#9D5D54", "warning": "#FFD29A"},
}


def load_settings(config):
    settings = dict(DEFAULT_SETTINGS)
    try:
        data = json.loads((Path(config) / "signal-rail/config.json").read_text())
    except (OSError, ValueError):
        return settings
    if not isinstance(data, dict):
        return settings
    for key in ("notification_seconds", "top_margin", "right_margin"):
        if type(data.get(key)) is int and 0 <= data[key] <= 86400:
            settings[key] = data[key]
    if data.get("display_mode") in ("auto", "window"):
        settings["display_mode"] = data["display_mode"]
    if isinstance(data.get("theme"), str) and data["theme"] in ("auto", "hyde", "system", "custom", *PRESETS):
        settings["theme"] = data["theme"]
    if isinstance(data.get("palette_file"), str):
        settings["palette_file"] = data["palette_file"]
    if isinstance(data.get("palette"), dict):
        settings["palette"] = data["palette"]
    return settings


@dataclass
class Device:
    path: str
    name: str
    adapter: str = ""
    icon: str = "bluetooth-symbolic"
    paired: bool = False
    connected: bool = False
    trusted: bool = False
    battery: int | None = None


def connection_events(before, after):
    """No startup/discovery spam; only transitions of already known devices."""
    result = []
    for path, old in before.items():
        new = after.get(path)
        if old.connected and (new is None or not new.connected):
            result.append((new or old, False))
        elif new is not None and not old.connected and new.connected:
            result.append((new, True))
    return result


def luminance(color):
    values = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
    return sum(v * w for v, w in zip(values, (.2126, .7152, .0722)))


def contrast(a, b):
    values = sorted((luminance(a), luminance(b)))
    return (values[1] + .05) / (values[0] + .05)


def readable(color, background):
    if contrast(color, background) >= 4.5:
        return color
    return max(("#ffffff", "#101010"), key=lambda c: contrast(c, background))


def read_palette(config=None, settings=None, system_palette=None):
    config = Path(config or Path.home() / ".config")
    settings = settings or load_settings(config)
    def read(path):
        try:
            return path.read_text()
        except OSError:
            return ""
    waybar = dict(re.findall(r"@define-color\s+([\w-]+)\s+(#[0-9a-fA-F]{6})\s*;", read(config / "waybar/theme.css")))
    hypr = dict(re.findall(r"\$wallbash_(\w+)\s*=\s*([0-9a-fA-F]{6})\b", read(config / "hypr/themes/colors.conf")))
    def h(name, fallback):
        return "#" + hypr[name] if name in hypr else fallback
    mode = settings.get("theme", "auto")
    palette = dict(PRESETS["noir"])
    if mode in PRESETS:
        palette.update(PRESETS[mode])
    elif mode in ("auto", "system") and system_palette:
        palette.update(system_palette)
    if mode == "hyde" or (mode == "auto" and (waybar or hypr)):
        palette.update(bg=waybar.get("main-bg", h("pry1", palette["bg"])),
                       fg=waybar.get("main-fg", h("txt1", palette["fg"])),
                       accent=waybar.get("wb-act-bg", h("2xa7", palette["accent"])),
                       secondary=waybar.get("wb-hvr-bg", h("1xa7", palette["secondary"])),
                       warning=h("4xa7", palette["warning"]))
    external = {}
    file = settings.get("palette_file")
    if file:
        path = Path(file).expanduser()
        if not path.is_absolute():
            path = config / "signal-rail" / path
        try:
            external = json.loads(read(path))
        except ValueError:
            pass
    for overrides in (external, settings.get("palette", {})):
        if isinstance(overrides, dict):
            for key in palette:
                value = overrides.get(key)
                if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                    palette[key] = value
    bg = palette["bg"]
    fg = readable(palette["fg"], bg)
    accent = palette["accent"]
    return dict(bg=bg, fg=fg, accent=accent,
                accent_text=readable(accent, bg),
                on_accent=readable(bg, accent),
                secondary=palette["secondary"], warning=readable(palette["warning"], bg))


def valid_pin(value, numeric=False):
    if numeric:
        return value.isascii() and value.isdigit() and 1 <= len(value) <= 6
    return 1 <= len(value) <= 16 and all(c.isprintable() for c in value)
