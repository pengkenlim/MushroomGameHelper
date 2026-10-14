"""Typed configuration, optionally loaded from ``calibration.json``."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

CALIBRATION_PATH: Path = Path(__file__).resolve().parent / "calibration.json"
SCHEDULES_PATH: Path = Path(__file__).resolve().parent / "schedules.json"

HSV = Tuple[int, int, int]
Roi = Tuple[int, int, int, int]  # (x, y, width, height) within the capture


@dataclass
class CaptureRegion:
    """Screen region captured by ``mss`` (pixels)."""

    top: int = 0
    left: int = 0
    width: int = 800
    height: int = 600
    window_title: str = ""


@dataclass
class BarConfig:
    """Calibration of one resource bar (health or mana).

    Attributes:
        roi: Bar rectangle ``(x, y, w, h)`` relative to the captured region.
        full_lower: Lower HSV bound of the "occupied" color.
        full_upper: Upper HSV bound of the "occupied" color.
        empty_lower: Lower HSV bound of the "empty/background" color.
        empty_upper: Upper HSV bound of the "empty/background" color.
        threshold_percent: The bar is "low" below this percentage (0-100).
        keybind: Key pressed when the bar is low.
        cooldown: Minimum seconds between presses of ``keybind``.
    """

    roi: Roi = (0, 0, 100, 10)
    full_lower: HSV = (0, 150, 150)
    full_upper: HSV = (10, 255, 255)
    empty_lower: HSV = (0, 0, 0)
    empty_upper: HSV = (180, 255, 60)
    threshold_percent: float = 40.0
    keybind: str = "h"
    cooldown: float = 1.0


@dataclass
class LootingConfig:
    """Hold-and-retrigger looting configuration.

    Attributes:
        keybind: Key held down while looting is active (e.g. ``"x"``).
        retrigger_interval: Seconds after which the held key is released and
            re-held so the game does not ignore a long-held key.
        toggle_key_1: First key of the on/off chord (e.g. ``"ctrl"``).
        toggle_key_2: Second key of the on/off chord (e.g. ``"l"``).
    """

    keybind: str = "x"
    retrigger_interval: float = 5.0
    toggle_key_1: str = "ctrl"
    toggle_key_2: str = "l"


@dataclass
class Config:
    """Complete persisted configuration."""

    capture: CaptureRegion = field(default_factory=CaptureRegion)
    match_threshold: float = 0.80
    health: BarConfig = field(default_factory=BarConfig)
    mana: BarConfig = field(
        default_factory=lambda: BarConfig(
            roi=(0, 20, 100, 10),
            full_lower=(100, 150, 150),
            full_upper=(130, 255, 255),
            keybind="m",
        )
    )
    looting: LootingConfig = field(default_factory=LootingConfig)


@dataclass
class BuffSchedule:
    """A buff/potion that is re-triggered on a fixed interval.

    Attributes:
        name: Human-readable unique name (e.g. ``"Attack Buff"``).
        keybind: Key to press (pynput key name or single character).
        interval_seconds: Seconds between automated presses (must be > 0).
        enabled: Disabled schedules are kept in the file but never fire.

    Raises:
        ValueError: If a field is empty, non-positive or not finite.
    """

    name: str
    keybind: str
    interval_seconds: float
    enabled: bool = True

    def __post_init__(self) -> None:
        """Normalizes and validates the fields."""
        self.name = str(self.name).strip()
        self.keybind = str(self.keybind).strip()
        self.interval_seconds = float(self.interval_seconds)
        self.enabled = bool(self.enabled)
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.keybind:
            raise ValueError("keybind must not be empty")
        if not 0.0 < self.interval_seconds < float("inf"):
            raise ValueError("interval_seconds must be a positive number")


def _tuple(value: Any, default: Tuple[int, ...]) -> Tuple[int, ...]:
    """Converts a JSON list to an int tuple of the default's length."""
    if isinstance(value, (list, tuple)) and len(value) == len(default):
        return tuple(int(v) for v in value)
    return default


def _bar_from_dict(data: Dict[str, Any], default: BarConfig) -> BarConfig:
    """Builds a :class:`BarConfig`, falling back to ``default`` per field.

    Args:
        data: Parsed JSON object for one bar.
        default: Defaults used for missing/invalid fields.

    Returns:
        The resulting bar configuration.
    """
    return BarConfig(
        roi=_tuple(data.get("roi"), default.roi),  # type: ignore[arg-type]
        full_lower=_tuple(data.get("full_lower"), default.full_lower),  # type: ignore[arg-type]
        full_upper=_tuple(data.get("full_upper"), default.full_upper),  # type: ignore[arg-type]
        empty_lower=_tuple(data.get("empty_lower"), default.empty_lower),  # type: ignore[arg-type]
        empty_upper=_tuple(data.get("empty_upper"), default.empty_upper),  # type: ignore[arg-type]
        threshold_percent=float(
            data.get("threshold_percent", default.threshold_percent)),
        keybind=str(data.get("keybind", default.keybind)),
        cooldown=float(data.get("cooldown", default.cooldown)),
    )


def _looting_from_dict(data: Any, default: LootingConfig) -> LootingConfig:
    """Builds a :class:`LootingConfig`, falling back to ``default`` per field.

    Args:
        data: Parsed JSON object for the looting section.
        default: Defaults used for missing/invalid fields.

    Returns:
        The resulting looting configuration.

    Raises:
        ValueError: If ``retrigger_interval`` is not a positive finite number.
    """
    if not isinstance(data, dict):
        return default
    interval = float(data.get("retrigger_interval", default.retrigger_interval))
    if not 0.0 < interval < float("inf"):
        raise ValueError("retrigger_interval must be a positive number")
    return LootingConfig(
        keybind=str(data.get("keybind", default.keybind)),
        retrigger_interval=interval,
        toggle_key_1=str(data.get("toggle_key_1", default.toggle_key_1)),
        toggle_key_2=str(data.get("toggle_key_2", default.toggle_key_2)),
    )


def load_config(path: Path = CALIBRATION_PATH) -> Config:
    """Loads configuration from JSON, falling back to defaults.

    Args:
        path: Location of the calibration file.

    Returns:
        The loaded configuration, or defaults if the file is missing/invalid.
    """
    default = Config()
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cap = data.get("capture", {})
        return Config(
            capture=CaptureRegion(
                top=int(cap.get("top", default.capture.top)),
                left=int(cap.get("left", default.capture.left)),
                width=int(cap.get("width", default.capture.width)),
                height=int(cap.get("height", default.capture.height)),
                window_title=str(
                    cap.get("window_title", default.capture.window_title)),
            ),
            match_threshold=float(
                data.get("match_threshold", default.match_threshold)),
            health=_bar_from_dict(data.get("health", {}), default.health),
            mana=_bar_from_dict(data.get("mana", {}), default.mana),
            looting=_looting_from_dict(data.get("looting"), default.looting),
        )
    except (ValueError, TypeError, AttributeError, OSError):
        return default


def load_schedules(path: Path = SCHEDULES_PATH) -> List[BuffSchedule]:
    """Loads buff schedules from JSON.

    Invalid entries and entries with duplicate names are skipped.

    Args:
        path: Location of the schedules file.

    Returns:
        The valid schedules; empty if the file is missing or unreadable.
    """
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("schedules", []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
    except (ValueError, OSError):
        return []
    schedules: List[BuffSchedule] = []
    seen = set()
    for item in items:
        try:
            schedule = BuffSchedule(
                name=item["name"],
                keybind=item["keybind"],
                interval_seconds=item["interval_seconds"],
                enabled=item.get("enabled", True),
            )
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if schedule.name not in seen:
            seen.add(schedule.name)
            schedules.append(schedule)
    return schedules


def save_schedules(schedules: List[BuffSchedule],
                   path: Path = SCHEDULES_PATH) -> None:
    """Writes buff schedules to JSON.

    Args:
        schedules: Schedules to persist.
        path: Destination file.
    """
    payload = {"schedules": [asdict(s) for s in schedules]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


_loaded: Config = load_config()

# Capture region (pixels, relative to the primary monitor).
CAPTURE_TOP: int = _loaded.capture.top
CAPTURE_LEFT: int = _loaded.capture.left
CAPTURE_WIDTH: int = _loaded.capture.width
CAPTURE_HEIGHT: int = _loaded.capture.height

# Optional game window title (substring, case-insensitive). When non-empty the
# capture region follows the window; the static values above are the fallback.
CAPTURE_WINDOW_TITLE: str = _loaded.capture.window_title

# Seconds between window-bounds re-checks while running (0 disables).
WINDOW_REFRESH_INTERVAL: float = 2.0

# Loop intervals (seconds).
VISION_INTERVAL: float = 0.25  # ~4 FPS
ACTION_INTERVAL: float = 0.10  # ~10 Hz

# Temporal filter: number of frames in the rolling median window.
SMOOTHING_WINDOW: int = 4

# Template matching.
TEMPLATES: Dict[str, str] = {
    "mushroom": "templates/mushroom.png",
}
MATCH_THRESHOLD: float = _loaded.match_threshold
TEMPLATE_THRESHOLDS: Dict[str, float] = {}

# Bar calibration (health / mana).
HEALTH: BarConfig = _loaded.health
MANA: BarConfig = _loaded.mana

# Looting hold-and-retrigger.
LOOTING: LootingConfig = _loaded.looting

# Other keybinds (pynput key names or single characters).
KEYBINDS: Dict[str, str] = {
    "left": "left",
    "right": "right",
    "jump": "space",
    "attack": "z",
}

# Scheduler loop interval (seconds): 5 Hz.
SCHEDULER_INTERVAL: float = 0.20

# Minimum seconds between two automated buff key presses (global input gap).
BUFF_INPUT_COOLDOWN: float = 0.15

# How long (seconds) a tap-style key is held.
DEFAULT_PRESS_DURATION: float = 0.05


def current_config() -> Config:
    """Builds a :class:`Config` from the current module-level values.

    Returns:
        Snapshot of the live configuration (including GUI edits).
    """
    return Config(
        capture=CaptureRegion(CAPTURE_TOP, CAPTURE_LEFT,
                              CAPTURE_WIDTH, CAPTURE_HEIGHT,
                              CAPTURE_WINDOW_TITLE),
        match_threshold=MATCH_THRESHOLD,
        health=HEALTH,
        mana=MANA,
        looting=LOOTING,
    )


def save_config(path: Path = CALIBRATION_PATH) -> None:
    """Writes the live configuration to ``calibration.json``.

    Args:
        path: Destination file.
    """
    path.write_text(json.dumps(asdict(current_config()), indent=2),
                    encoding="utf-8")
