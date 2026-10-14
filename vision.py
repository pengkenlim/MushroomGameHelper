"""Vision module: screen capture and frame analysis."""

import statistics
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np

import config
from config import BarConfig

Match = Tuple[int, int, float]


class Vision:
    """Captures the configured screen region and extracts game information."""

    def __init__(self) -> None:
        """Loads templates and prepares the capture region."""
        self._sct: Optional[Any] = None
        self.region: Dict[str, int] = {
            "top": config.CAPTURE_TOP,
            "left": config.CAPTURE_LEFT,
            "width": config.CAPTURE_WIDTH,
            "height": config.CAPTURE_HEIGHT,
        }
        self.history: Dict[str, Deque[float]] = {
            "health": deque(maxlen=config.SMOOTHING_WINDOW),
            "mana": deque(maxlen=config.SMOOTHING_WINDOW),
        }
        self.templates: Dict[str, np.ndarray] = {}
        for name, path in config.TEMPLATES.items():
            image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if image is not None:
                self.templates[name] = image

    def capture(self) -> np.ndarray:
        """Grabs the capture region.

        Note:
            ``mss`` handles are thread-local, so the handle is created lazily
            on the thread that calls this method.

        Returns:
            A BGR image array of shape (height, width, 3).
        """
        if self._sct is None:
            self._sct = mss.mss()
        shot = np.array(self._sct.grab(self.region))
        return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)

    def close(self) -> None:
        """Releases the capture handle."""
        if self._sct is not None:
            self._sct.close()
            self._sct = None

    @staticmethod
    def find_template(
        frame: np.ndarray, template: np.ndarray, threshold: float
    ) -> List[Match]:
        """Finds all template matches above a confidence threshold.

        Args:
            frame: BGR or grayscale frame.
            template: Grayscale template image.
            threshold: Minimum normalized correlation (0-1).

        Returns:
            List of ``(center_x, center_y, confidence)`` tuples.
        """
        gray = (
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if frame.ndim == 3
            else frame
        )
        th, tw = template.shape[:2]
        if gray.shape[0] < th or gray.shape[1] < tw:
            return []
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(result >= threshold)
        matches: List[Match] = []
        for x, y in sorted(
            zip(xs.tolist(), ys.tolist()), key=lambda p: -result[p[1], p[0]]
        ):
            cx, cy = x + tw // 2, y + th // 2
            if all(abs(cx - m[0]) > tw // 2 or abs(cy - m[1]) > th // 2
                   for m in matches):
                matches.append((cx, cy, float(result[y, x])))
        return matches

    @staticmethod
    def bar_percent(frame: np.ndarray, bar: BarConfig) -> Optional[float]:
        """Computes the filled percentage of a bar from one frame.

        Within the ROI, pixels in the "occupied" HSV range (``cv2.inRange``)
        are counted as ``occupied`` and pixels in the "empty" range as
        ``empty``. Everything else (borders, text, glow) is treated as
        background and ignored, so ``percent = 100 * occupied /
        (occupied + empty)``.

        Args:
            frame: BGR frame of the captured region.
            bar: Calibration for the bar.

        Returns:
            Percentage in [0, 100], or None if neither range matched (e.g.
            the bar is invisible in this frame) or the ROI is invalid.
        """
        x, y, w, h = bar.roi
        roi = frame[max(0, y):y + h, max(0, x):x + w]
        if roi.size == 0:
            return None
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        occupied = cv2.countNonZero(cv2.inRange(
            hsv, np.array(bar.full_lower), np.array(bar.full_upper)))
        empty = cv2.countNonZero(cv2.inRange(
            hsv, np.array(bar.empty_lower), np.array(bar.empty_upper)))
        total = occupied + empty
        return None if total == 0 else 100.0 * occupied / total

    def smoothed_percent(self, key: str, raw: Optional[float]) -> float:
        """Applies the temporal median filter to a bar percentage.

        Bars flash or change opacity when low, which makes single-frame
        readings jump (e.g. 20, 100, 20, 100). Keep the last ``N`` readings
        (``config.SMOOTHING_WINDOW``, 4 frames = 1 s at 250 ms) in a window
        ``p_1 <= ... <= p_N`` (sorted); the reported value is the median:
        ``p_((N+1)/2)`` for odd ``N``, or ``(p_(N/2) + p_(N/2+1)) / 2`` for
        even ``N``. The median ignores up to ``floor((N-1)/2)`` outliers
        in the window, unlike the mean, so isolated flashes don't shift the
        result, while a real sustained change takes over after about half the
        window. Frames with no reading (None) are skipped so an invisible
        bar neither adds a sample nor triggers a false "low".

        Args:
            key: ``"health"`` or ``"mana"``.
            raw: This frame's percentage, or None.

        Returns:
            Median of the window; 100.0 (not low) if there is no data yet.
        """
        window = self.history[key]
        if window.maxlen != config.SMOOTHING_WINDOW:
            window = self.history[key] = deque(
                window, maxlen=config.SMOOTHING_WINDOW)
        if raw is not None:
            window.append(raw)
        return float(statistics.median(window)) if window else 100.0

    def analyze(self, frame: np.ndarray) -> Dict[str, Any]:
        """Extracts structured data from a frame.

        Args:
            frame: BGR frame.

        Returns:
            Dictionary with ``matches`` (template name -> list of
            ``(x, y, confidence)``), ``targets_visible`` (bool),
            ``health_percent`` / ``mana_percent`` (smoothed, 0-100) and
            ``health_low`` / ``mana_low`` (bool, smoothed percent below the
            configured threshold).
        """
        matches: Dict[str, List[Match]] = {}
        for name, template in self.templates.items():
            threshold = config.TEMPLATE_THRESHOLDS.get(
                name, config.MATCH_THRESHOLD
            )
            matches[name] = self.find_template(frame, template, threshold)
        health = self.smoothed_percent(
            "health", self.bar_percent(frame, config.HEALTH))
        mana = self.smoothed_percent(
            "mana", self.bar_percent(frame, config.MANA))
        return {
            "matches": matches,
            "targets_visible": any(matches.values()),
            "health_percent": health,
            "mana_percent": mana,
            "health_low": health < config.HEALTH.threshold_percent,
            "mana_low": mana < config.MANA.threshold_percent,
        }

    def process(self) -> Dict[str, Any]:
        """Captures and analyzes one frame.

        Returns:
            The structured result of :meth:`analyze`.
        """
        return self.analyze(self.capture())
