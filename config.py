"""Typed configuration, optionally loaded from ``calibration.json``."""

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

CALIBRATION_PATH: Path = Path(__file__).resolve().parent / "calibration.json"
SCHEDULES_PATH: Path = Path(__file__).resolve().parent / "schedules.json"


def _resolve_asset(*parts: str) -> Path:
    """Resolves a bundled asset path for both source runs and frozen builds."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)


ICON_PATH: Path = _resolve_asset("visual_assets", "green_blob.ico")

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
    keybind: str = "ctrl"
    cooldown: float = 1.0


@dataclass
class LootingConfig:
    """Hold-and-retrigger looting configuration.

    Attributes:
        keybind: Key held down while looting is active (e.g. ``"x"``).
        toggle_key_1: First key of the on/off chord (e.g. ``"ctrl"``).
        toggle_key_2: Second key of the on/off chord (e.g. ``"l"``).
    """

    keybind: str = "z"
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
            keybind="shift",
        )
    )
    looting: LootingConfig = field(default_factory=LootingConfig)
    repot_toggle_1: str = "f9"
    repot_toggle_2: str = ""
    rebuff_toggle_1: str = "f10"
    rebuff_toggle_2: str = ""
    looting_toggle_1: str = "f11"
    looting_toggle_2: str = ""
    start_stop_toggle_1: str = "f12"
    start_stop_toggle_2: str = ""
    looting_keybind: str = "z"


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
        if isinstance(self.enabled, str):  # bool("false") would be True
            self.enabled = self.enabled.strip().lower() not in (
                "false", "0", "no", "off", "")
        self.enabled = bool(self.enabled)
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.keybind:
            raise ValueError("keybind must not be empty")
        if not 0.0 < self.interval_seconds < float("inf"):
            raise ValueError("interval_seconds must be a positive number")


def _atomic_write(path: Path, text: str) -> None:
    """Writes ``text`` so readers never observe a partially written file.

    Args:
        path: Destination file.
        text: Full file content.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
    """
    if not isinstance(data, dict):
        return default
    return LootingConfig(
        keybind=str(data.get("keybind", default.keybind)),
        toggle_key_1=str(data.get("toggle_key_1", default.toggle_key_1)),
        toggle_key_2=str(data.get("toggle_key_2", default.toggle_key_2)),
    )


def _safe_looting(data: Any, default: LootingConfig) -> LootingConfig:
    """Like :func:`_looting_from_dict` but falls back to ``default`` on error.

    A bad looting section must not discard the calibration of everything else.

    Args:
        data: Parsed JSON value of the looting section.
        default: Defaults used when the section is invalid.

    Returns:
        The looting configuration.
    """
    try:
        return _looting_from_dict(data, default)
    except (ValueError, TypeError, OverflowError):
        return default


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
            looting=_safe_looting(data.get("looting"), default.looting),
            repot_toggle_1=str(data.get("repot_toggle_1", default.repot_toggle_1)),
            repot_toggle_2=str(data.get("repot_toggle_2", default.repot_toggle_2)),
            rebuff_toggle_1=str(data.get("rebuff_toggle_1", default.rebuff_toggle_1)),
            rebuff_toggle_2=str(data.get("rebuff_toggle_2", default.rebuff_toggle_2)),
            looting_toggle_1=str(data.get("looting_toggle_1", default.looting_toggle_1)),
            looting_toggle_2=str(data.get("looting_toggle_2", default.looting_toggle_2)),
            start_stop_toggle_1=str(data.get("start_stop_toggle_1", default.start_stop_toggle_1)),
            start_stop_toggle_2=str(data.get("start_stop_toggle_2", default.start_stop_toggle_2)),
            looting_keybind=str(data.get("looting_keybind", default.looting_keybind)),
        )
    except (ValueError, TypeError, AttributeError, OSError, OverflowError):
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
        except (KeyError, ValueError, TypeError, AttributeError,
                OverflowError):
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
    _atomic_write(path, json.dumps(payload, indent=2))


_loaded: Config = load_config()

# Capture region (pixels, relative to the primary monitor).
CAPTURE_TOP: int = _loaded.capture.top
CAPTURE_LEFT: int = _loaded.capture.left
CAPTURE_WIDTH: int = _loaded.capture.width
CAPTURE_HEIGHT: int = _loaded.capture.height

# Optional game window title (exact match preferred, else case-insensitive
# substring). Empty means static coordinates. When non-empty the capture region
# follows the window; the static values above are the fallback. Persisted as
# ``capture.window_title`` in calibration.json.
WINDOW_TITLE: str = _loaded.capture.window_title

# Seconds between window-bounds re-checks while running (0 disables).
WINDOW_REFRESH_INTERVAL: float = 2.0

# Loop intervals (seconds).
VISION_INTERVAL: float = 0.05  # ~20 FPS
ACTION_INTERVAL: float = 0.01  # ~100 Hz

# --- Action dispatcher ---
# Minimum time (seconds) between ANY two automated presses. Prevents
# OS/hardware dropping of simultaneous synthetic keystrokes.
GLOBAL_RESOLUTION_LIMIT: float = 0.01
# Time (seconds) the game engine is "locked" in a buff cast animation.
# After the bot presses a buff key, ALL other automated actions (heals,
# pots, loots, other buffs) are suppressed for this duration because the
# game will ignore them.
BUFF_CAST_LOCKOUT: float = 0.8
# Time (seconds) between the two rapid presses of a buff key to interrupt held keys.
BUFF_DOUBLE_TAP_GAP: float = 0.35
# Backward-compatible alias used by earlier action timing checks.
RESOLUTION_LIMIT: float = GLOBAL_RESOLUTION_LIMIT
# Keys that the user holds for movement/jumping. These do NOT consume the
# game engine's action input buffer, so they are excluded from the contention count.
IGNORED_PHYSICAL_KEYS: Set[str] = {"left", "right", "up", "down", "space"}
# Physical keys the user may hold before low-priority actions are deferred.
MAX_PHYSICAL_KEYS: int = 1
# When True, heal/mana also defer under physical contention. When False only
# buff and loot actions defer (survival actions always fire).
DEFER_CRITICAL_ACTIONS: bool = False

# Temporal filter: number of frames in the rolling median window.
SMOOTHING_WINDOW: int = 4
# Percentage of the screen (0.0 to 1.0) that must be pitch black to trigger
# the loading screen state (e.g., during portal travel).
LOADING_SCREEN_BLACK_RATIO_THRESHOLD: float = 0.70
# Seconds to wait after the black screen clears before trusting HP/MP readings
# again. Prevents false triggers during the map fade-in animation.
LOADING_SCREEN_FADE_IN_TIME: float = 1.5

# Template matching.
TEMPLATES: Dict[str, str] = {
}
MATCH_THRESHOLD: float = _loaded.match_threshold
TEMPLATE_THRESHOLDS: Dict[str, float] = {}

# Bar calibration (health / mana).
HEALTH: BarConfig = _loaded.health
MANA: BarConfig = _loaded.mana

# Looting hold-and-retrigger.
LOOTING: LootingConfig = _loaded.looting

# Toggle hotkeys.
REPOT_TOGGLE_1: str = _loaded.repot_toggle_1
REPOT_TOGGLE_2: str = _loaded.repot_toggle_2
REBUFF_TOGGLE_1: str = _loaded.rebuff_toggle_1
REBUFF_TOGGLE_2: str = _loaded.rebuff_toggle_2
LOOTING_TOGGLE_1: str = _loaded.looting_toggle_1
LOOTING_TOGGLE_2: str = _loaded.looting_toggle_2
START_STOP_TOGGLE_1: str = _loaded.start_stop_toggle_1
START_STOP_TOGGLE_2: str = _loaded.start_stop_toggle_2
LOOTING_KEYBIND: str = _loaded.looting_keybind

# Other keybinds (pynput key names or single characters).
KEYBINDS: Dict[str, str] = {
"left": "left",
"right": "right",
"jump": "space",
}

# Scheduler loop interval (seconds): 20 Hz.
SCHEDULER_INTERVAL: float = 0.05

# Minimum seconds between two automated buff key presses (global input gap).
BUFF_INPUT_COOLDOWN: float = 0.5

# How long (seconds) a tap-style key is held.
DEFAULT_PRESS_DURATION: float = 0.1


def current_config() -> Config:
    """Builds a :class:`Config` from the current module-level values.

    Returns:
        Snapshot of the live configuration (including GUI edits).
    """
    return Config(
        capture=CaptureRegion(CAPTURE_TOP, CAPTURE_LEFT,
                              CAPTURE_WIDTH, CAPTURE_HEIGHT,
                              WINDOW_TITLE),
        match_threshold=MATCH_THRESHOLD,
        health=HEALTH,
        mana=MANA,
        looting=LootingConfig(
            keybind=LOOTING_KEYBIND,
            toggle_key_1=LOOTING_TOGGLE_1,
            toggle_key_2=LOOTING_TOGGLE_2,
        ),
        repot_toggle_1=REPOT_TOGGLE_1,
        repot_toggle_2=REPOT_TOGGLE_2,
        rebuff_toggle_1=REBUFF_TOGGLE_1,
        rebuff_toggle_2=REBUFF_TOGGLE_2,
        looting_toggle_1=LOOTING_TOGGLE_1,
        looting_toggle_2=LOOTING_TOGGLE_2,
        start_stop_toggle_1=START_STOP_TOGGLE_1,
        start_stop_toggle_2=START_STOP_TOGGLE_2,
        looting_keybind=LOOTING_KEYBIND,
    )


def save_config(path: Path = CALIBRATION_PATH) -> None:
    """Writes the live configuration to ``calibration.json``.

    Args:
        path: Destination file.
    """
    _atomic_write(path, json.dumps(asdict(current_config()), indent=2))
