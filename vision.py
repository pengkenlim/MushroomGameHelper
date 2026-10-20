"""Vision module: screen capture and frame analysis."""

import statistics
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np

import config
from config import BarConfig
from logger import logger
from window_manager import get_window_bounds

Match = Tuple[int, int, float]

BAR_NONE_FRAMES: int = 3
NO_MATCH_FRAMES: int = 5


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
        self._window_found: Optional[bool] = None
        self._warned_size: Optional[Tuple[int, int]] = None
        self._last_refresh: float = time.perf_counter()
        self._region_checked_at: float = 0.0
        self.history: Dict[str, Deque[float]] = {
            "health": deque(maxlen=config.SMOOTHING_WINDOW),
            "mana": deque(maxlen=config.SMOOTHING_WINDOW),
        }
        self._bar_none_streak: Dict[str, int] = {"health": 0, "mana": 0}
        self._no_match_streak: Dict[str, int] = {}
        self._loading_screen_ended_at: float = 0.0
        self.templates: Dict[str, np.ndarray] = {}
        for name, path in config.TEMPLATES.items():
            image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if image is not None:
                self.templates[name] = image
        self._apply_window_bounds(force=True)

    def _apply_window_bounds(self, force: bool = False) -> None:
        """Refreshes the capture region from the live game window bounds.

        When ``config.WINDOW_TITLE`` is empty the static coordinates from
        ``config.py`` are used unchanged. Otherwise the OS is queried at most
        once every ``config.WINDOW_REFRESH_INTERVAL`` seconds. Every failure
        mode (window minimized, closed, off-screen, library unavailable)
        leaves ``self.region`` at its last known-good value so the vision
        thread never captures an invalid area.

        Args:
            force: Bypass the refresh-interval throttle.
        """
        title = config.WINDOW_TITLE.strip()
        if not title:
            return
        now = time.perf_counter()
        if not force and (now - self._region_checked_at
                          < config.WINDOW_REFRESH_INTERVAL):
            return
        self._region_checked_at = now
        bounds = get_window_bounds(title)
        if bounds is None:
            logger.warning(
                f"Window '{title}' not found or minimized; "
                f"keeping last capture region {self.region}")
            return
        if (bounds.get("width"), bounds.get("height")) != (
                self.region.get("width"), self.region.get("height")):
            logger.warning(
                f"Capture size changed from "
                f"{self.region.get('width')}x{self.region.get('height')} to "
                f"{bounds.get('width')}x{bounds.get('height')}. Health/mana ROIs are "
                f"relative to this region and are probably misaligned now - "
                f"re-run the calibrator.")
        if bounds != self.region:
            logger.info(f"Capture region updated to {bounds}")
        self.region = bounds

    def refresh_region(self) -> bool:
        """Re-fetches the game window bounds into ``self.region``.

        Does nothing if ``config.WINDOW_TITLE`` is empty. If the window
        cannot be found the current region is kept (initially the static
        ``CAPTURE_*`` values), so capture never breaks. Messages are only
        logged when the found/not-found state changes.

        Returns:
            True if the region was updated from a window.
        """
        title = config.WINDOW_TITLE
        if not title:
            return False
        try:
            bounds = get_window_bounds(title)
        except Exception as exc:  # never let the vision thread die here
            logger.warning(f"Window lookup raised unexpectedly: {exc}")
            bounds = None
        if bounds is not None and (bounds.get("width", 0) <= 0
                                   or bounds.get("height", 0) <= 0):
            bounds = None  # never adopt an invalid region
        if bounds is None:
            if self._window_found is not False:
                logger.warning(
                    f"Window '{title}' not found; keeping "
                    f"capture region {self.region} (static fallback if never found)")
            self._window_found = False
            return False
        if self._window_found is not True or bounds != self.region:
            logger.info(f"Capture region set from window '{title}': {bounds}")
            print(f"Capture region set from window '{title}': {bounds}")
        self._window_found = True
        self.region = bounds
        self._warn_if_resized(bounds)
        return True

    def _warn_if_resized(self, bounds: Dict[str, int]) -> None:
        """Warns (once per size) if the window size differs from calibration.

        The bar ROIs are pixel offsets inside the capture, so a different
        window size (e.g. a changed in-game resolution) misaligns them.
        ``config.CAPTURE_WIDTH/HEIGHT`` hold the size seen at calibration.

        Args:
            bounds: Newly acquired window bounds.
        """
        size = (bounds["width"], bounds["height"])
        if size == (config.CAPTURE_WIDTH, config.CAPTURE_HEIGHT):
            self._warned_size = None
            return
        if size != self._warned_size:
            self._warned_size = size
            logger.warning(
                f"Window size {size[0]}x{size[1]} differs from the size at "
                f"calibration ({config.CAPTURE_WIDTH}x{config.CAPTURE_HEIGHT})"
                "; bar positions may be misaligned. Recalibrate if readings "
                "look wrong.")

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

        # Dynamic region resolution
        if config.WINDOW_TITLE:
            try:
                bounds = get_window_bounds(config.WINDOW_TITLE)
                if bounds:
                    region = bounds
                else:
                    region = {
                        "top": config.CAPTURE_TOP, "left": config.CAPTURE_LEFT,
                        "width": config.CAPTURE_WIDTH, "height": config.CAPTURE_HEIGHT
                    }
            except Exception:
                region = {
                    "top": config.CAPTURE_TOP, "left": config.CAPTURE_LEFT,
                    "width": config.CAPTURE_WIDTH, "height": config.CAPTURE_HEIGHT
                }
        else:
            region = {
                "top": config.CAPTURE_TOP, "left": config.CAPTURE_LEFT,
                "width": config.CAPTURE_WIDTH, "height": config.CAPTURE_HEIGHT
            }

        shot = np.array(self._sct.grab(region))
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
        # Clamp both ends: a negative end index would wrap around in numpy.
        roi = frame[max(0, y):max(0, y + h), max(0, x):max(0, x + w)]
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

    def _track_bar(self, key: str, raw: Optional[float]) -> None:
        """Logs when a bar reading is missing for consecutive frames.

        Args:
            key: ``"health"`` or ``"mana"``.
            raw: This frame's raw percentage, or None.
        """
        if raw is not None:
            self._bar_none_streak[key] = 0
            return
        streak = self._bar_none_streak[key] = self._bar_none_streak[key] + 1
        if streak == BAR_NONE_FRAMES:
            logger.debug(
                f"bar_percent returned None for {key} on {streak} "
                "consecutive frames (ROI misaligned or bar hidden?)")

    def _track_matches(self, name: str, matches: List[Match]) -> None:
        """Logs when a template has no matches for consecutive frames.

        Args:
            name: Template name.
            matches: Matches found in this frame.
        """
        if matches:
            self._no_match_streak[name] = 0
            return
        streak = self._no_match_streak[name] = (
            self._no_match_streak.get(name, 0) + 1)
        if streak == NO_MATCH_FRAMES + 1:
            logger.warning(
                f"Template '{name}' had zero matches for more than "
                f"{NO_MATCH_FRAMES} consecutive frames")

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
            self._track_matches(name, matches[name])
        raw_health = self.bar_percent(frame, config.HEALTH)
        raw_mana = self.bar_percent(frame, config.MANA)
        self._track_bar("health", raw_health)
        self._track_bar("mana", raw_mana)
        health = self.smoothed_percent("health", raw_health)
        mana = self.smoothed_percent("mana", raw_mana)
        health_low = health < config.HEALTH.threshold_percent
        mana_low = mana < config.MANA.threshold_percent

        # Detect loading screen (mostly black screen during portal travel)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        black_pixels = np.sum(gray < 20)
        is_black_screen = (black_pixels / gray.size) > config.LOADING_SCREEN_BLACK_RATIO_THRESHOLD
        
        if is_black_screen:
            self._loading_screen_ended_at = 0.0
            is_loading = True
            health = 100.0
            mana = 100.0
            health_low = False
            mana_low = False
        else:
            # Just transitioned from black to not-black, start the fade-in timer
            if self._loading_screen_ended_at == 0.0:
                self._loading_screen_ended_at = time.perf_counter()
                
            # If we are still within the fade-in grace period, treat as loading
            if time.perf_counter() - self._loading_screen_ended_at < config.LOADING_SCREEN_FADE_IN_TIME:
                is_loading = True
                health = 100.0
                mana = 100.0
                health_low = False
                mana_low = False
            else:
                is_loading = False

        return {
            "matches": matches,
            "targets_visible": any(matches.values()),
            "health_percent": health,
            "mana_percent": mana,
            "health_low": health_low,
            "mana_low": mana_low,
            "is_loading": is_loading,
        }

    def process(self) -> Dict[str, Any]:
        """Captures and analyzes one frame.

        Returns:
            The structured result of :meth:`analyze`.
        """
        self._apply_window_bounds()
        return self.analyze(self.capture())
