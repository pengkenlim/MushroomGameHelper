"""Vision module: screen capture and frame analysis."""

from typing import Any, Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np

import config

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
    def color_mask_pixels(
        frame: np.ndarray,
        lower: Tuple[int, int, int],
        upper: Tuple[int, int, int],
    ) -> int:
        """Counts pixels within an HSV range using ``cv2.inRange``.

        Args:
            frame: BGR frame.
            lower: Lower HSV bound.
            upper: Upper HSV bound.

        Returns:
            Number of pixels inside the range.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        return int(cv2.countNonZero(mask))

    def analyze(self, frame: np.ndarray) -> Dict[str, Any]:
        """Extracts structured data from a frame.

        Args:
            frame: BGR frame.

        Returns:
            Dictionary with ``matches`` (template name -> list of
            ``(x, y, confidence)``), ``targets_visible`` (bool) and
            ``health_low`` (bool).
        """
        matches: Dict[str, List[Match]] = {}
        for name, template in self.templates.items():
            threshold = config.TEMPLATE_THRESHOLDS.get(
                name, config.MATCH_THRESHOLD
            )
            matches[name] = self.find_template(frame, template, threshold)
        health_pixels = self.color_mask_pixels(
            frame, config.HEALTH_BAR_HSV_LOWER, config.HEALTH_BAR_HSV_UPPER
        )
        return {
            "matches": matches,
            "targets_visible": any(matches.values()),
            "health_low": health_pixels < config.HEALTH_BAR_MIN_PIXELS,
        }

    def process(self) -> Dict[str, Any]:
        """Captures and analyzes one frame.

        Returns:
            The structured result of :meth:`analyze`.
        """
        return self.analyze(self.capture())
