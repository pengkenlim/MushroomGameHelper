"""Configuration constants for the game automation framework."""

from typing import Dict, Tuple

# Screen capture region (pixels, relative to the primary monitor).
CAPTURE_TOP: int = 0
CAPTURE_LEFT: int = 0
CAPTURE_WIDTH: int = 800
CAPTURE_HEIGHT: int = 600

# Loop intervals (seconds).
VISION_INTERVAL: float = 0.25  # ~4 FPS
ACTION_INTERVAL: float = 0.10  # ~10 Hz

# Template matching: name -> image path, and confidence thresholds.
TEMPLATES: Dict[str, str] = {
    "mushroom": "templates/mushroom.png",
}
MATCH_THRESHOLD: float = 0.80
TEMPLATE_THRESHOLDS: Dict[str, float] = {}  # optional per-template override

# Color thresholding (HSV lower/upper bounds) for e.g. a health bar.
HEALTH_BAR_HSV_LOWER: Tuple[int, int, int] = (0, 150, 150)
HEALTH_BAR_HSV_UPPER: Tuple[int, int, int] = (10, 255, 255)
HEALTH_BAR_MIN_PIXELS: int = 20

# Keybind mappings (pynput key names or single characters).
KEYBINDS: Dict[str, str] = {
    "left": "left",
    "right": "right",
    "jump": "space",
    "attack": "z",
    "heal": "h",
}

# How long (seconds) a tap-style key is held.
DEFAULT_PRESS_DURATION: float = 0.05
