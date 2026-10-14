"""Interactive calibration tool for the health and mana bars.

Run ``python calibrator.py``. For each bar: drag a rectangle around it, click
a pixel in the occupied (full) part, then click a pixel in the empty part.
Keys: ``r`` redo current bar, ``q``/Esc abort. Results are saved to
``calibration.json``.
"""

import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np

import config
from config import HSV, BarConfig, Roi
from window_manager import get_window_bounds

WINDOW: str = "Calibrator"
HUE_TOLERANCE: int = 15
SV_TOLERANCE: int = 40
BAR_NAMES: Tuple[str, str] = ("Health", "Mana")


def bgr_to_hsv(bgr: Tuple[int, int, int]) -> HSV:
    """Converts one BGR (OpenCV order) color to OpenCV HSV.

    Args:
        bgr: Blue, green, red values (0-255).

    Returns:
        ``(H 0-179, S 0-255, V 0-255)``.
    """
    pixel = np.uint8([[list(bgr)]])
    h, s, v = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0]
    return int(h), int(s), int(v)


def tolerance_range(hsv: HSV) -> Tuple[HSV, HSV]:
    """Builds an HSV range around a sample (±15 H, ±40 S/V, clipped).

    Hue wrap-around (e.g. reds near 0/179) is not handled; the range is
    clipped to the valid interval.

    Args:
        hsv: Sampled HSV color.

    Returns:
        ``(lower, upper)`` bounds.
    """
    h, s, v = hsv
    lower = (max(0, h - HUE_TOLERANCE), max(0, s - SV_TOLERANCE),
             max(0, v - SV_TOLERANCE))
    upper = (min(179, h + HUE_TOLERANCE), min(255, s + SV_TOLERANCE),
             min(255, v + SV_TOLERANCE))
    return lower, upper


class Step(Enum):
    """Stages of calibrating one bar."""

    DRAW_ROI = auto()
    PICK_FULL = auto()
    PICK_EMPTY = auto()
    DONE = auto()


@dataclass
class BarSample:
    """Interactive results for a single bar."""

    roi: Optional[Roi] = None
    full_hsv: Optional[HSV] = None
    empty_hsv: Optional[HSV] = None


@dataclass
class CalibrationSession:
    """Stateful owner of the OpenCV window state and mouse callback."""

    image: np.ndarray
    samples: Dict[str, BarSample] = field(
        default_factory=lambda: {n: BarSample() for n in BAR_NAMES})
    bar_index: int = 0
    step: Step = Step.DRAW_ROI
    _drag_start: Optional[Tuple[int, int]] = None
    _drag_now: Optional[Tuple[int, int]] = None

    @property
    def bar(self) -> str:
        """Name of the bar currently being calibrated."""
        return BAR_NAMES[min(self.bar_index, len(BAR_NAMES) - 1)]

    @property
    def finished(self) -> bool:
        """Whether both bars have been fully calibrated."""
        return self.bar_index >= len(BAR_NAMES)

    def prompt(self) -> str:
        """Instruction text for the current step."""
        if self.finished:
            return "Done - press any key"
        text = {
            Step.DRAW_ROI: "drag a box around the bar",
            Step.PICK_FULL: "click the FULL (occupied) part",
            Step.PICK_EMPTY: "click the EMPTY (background) part",
        }
        return f"{self.bar}: {text[self.step]}  [r=redo q=quit]"

    def on_mouse(self, event: int, x: int, y: int, flags: int,
                 param: object = None) -> None:
        """OpenCV mouse callback.

        Args:
            event: ``cv2.EVENT_*`` code.
            x: Pointer x in image pixels.
            y: Pointer y in image pixels.
            flags: OpenCV event flags (unused).
            param: User data (unused).
        """
        if self.finished:
            return
        if self.step is Step.DRAW_ROI:
            if event == cv2.EVENT_LBUTTONDOWN:
                self._drag_start = self._drag_now = (x, y)
            elif event == cv2.EVENT_MOUSEMOVE and self._drag_start:
                self._drag_now = (x, y)
            elif event == cv2.EVENT_LBUTTONUP and self._drag_start:
                x0, y0 = self._drag_start
                rx, ry = min(x0, x), min(y0, y)
                rw, rh = abs(x - x0), abs(y - y0)
                self._drag_start = self._drag_now = None
                if rw >= 2 and rh >= 2:
                    self.samples[self.bar].roi = (rx, ry, rw, rh)
                    self.step = Step.PICK_FULL
        elif event == cv2.EVENT_LBUTTONDOWN:
            sample = self.samples[self.bar]
            rx, ry, rw, rh = sample.roi or (0, 0, 0, 0)
            if not (rx <= x < rx + rw and ry <= y < ry + rh):
                return  # sample must be inside the ROI
            patch = self.image[max(0, y - 1):y + 2, max(0, x - 1):x + 2]
            b, g, r = (int(c) for c in patch.reshape(-1, 3).mean(axis=0))
            hsv = bgr_to_hsv((b, g, r))
            if self.step is Step.PICK_FULL:
                sample.full_hsv = hsv
                self.step = Step.PICK_EMPTY
            else:
                sample.empty_hsv = hsv
                self.bar_index += 1
                self.step = Step.DRAW_ROI

    def redo(self) -> None:
        """Restarts calibration of the current bar."""
        if not self.finished:
            self.samples[self.bar] = BarSample()
            self.step = Step.DRAW_ROI

    def render(self) -> np.ndarray:
        """Draws ROIs, the live drag box and instructions.

        Returns:
            Annotated copy of the screenshot.
        """
        canvas = self.image.copy()
        for name, s in self.samples.items():
            if s.roi:
                x, y, w, h = s.roi
                cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 255, 0), 1)
                cv2.putText(canvas, name, (x, max(10, y - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        if self._drag_start and self._drag_now:
            cv2.rectangle(canvas, self._drag_start, self._drag_now,
                          (0, 255, 255), 1)
        cv2.putText(canvas, self.prompt(), (5, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        return canvas

    def bar_configs(self, answers: Dict[str, Tuple[float, str, float]]
                    ) -> Dict[str, BarConfig]:
        """Combines samples and terminal answers into bar configs.

        Args:
            answers: Bar name -> ``(threshold_percent, keybind, cooldown)``.

        Returns:
            Bar name -> :class:`BarConfig`.
        """
        out: Dict[str, BarConfig] = {}
        for name, s in self.samples.items():
            assert s.roi and s.full_hsv and s.empty_hsv
            fl, fu = tolerance_range(s.full_hsv)
            el, eu = tolerance_range(s.empty_hsv)
            pct, key, cd = answers[name]
            out[name] = BarConfig(roi=s.roi, full_lower=fl, full_upper=fu,
                                  empty_lower=el, empty_upper=eu,
                                  threshold_percent=pct, keybind=key,
                                  cooldown=cd)
        return out


def ask_float(prompt: str, lo: float, hi: float) -> float:
    """Prompts until a float in ``[lo, hi]`` is entered.

    Args:
        prompt: Text shown to the user.
        lo: Minimum accepted value.
        hi: Maximum accepted value.

    Returns:
        The validated value.
    """
    while True:
        try:
            value = float(input(prompt).strip())
            if lo <= value <= hi:
                return value
        except ValueError:
            pass
        print(f"Please enter a number between {lo:g} and {hi:g}.")


def ask_key(prompt: str) -> str:
    """Prompts until a non-empty key name is entered.

    Args:
        prompt: Text shown to the user.

    Returns:
        A pynput key name or single character.
    """
    while True:
        key = input(prompt).strip()
        if key:
            return key


def capture_screenshot() -> np.ndarray:
    """Grabs one BGR screenshot of the game window or the static region.

    If ``config.WINDOW_TITLE`` is set and the window is found, its current
    bounds are used and written into the ``config.CAPTURE_*`` values, so the
    saved ``calibration.json`` records the window geometry that was calibrated
    (the vision thread warns when the window size later differs). Otherwise
    the static ``config.CAPTURE_*`` region is used.

    Returns:
        Image array of shape (height, width, 3).
    """
    region = {"top": config.CAPTURE_TOP, "left": config.CAPTURE_LEFT,
              "width": config.CAPTURE_WIDTH, "height": config.CAPTURE_HEIGHT}
    if config.WINDOW_TITLE:
        bounds = get_window_bounds(config.WINDOW_TITLE)
        if bounds is None:
            print(f"Window '{config.WINDOW_TITLE}' not found or minimized; "
                  "using the static capture region instead.")
        else:
            region = bounds
            config.CAPTURE_TOP = bounds["top"]
            config.CAPTURE_LEFT = bounds["left"]
            config.CAPTURE_WIDTH = bounds["width"]
            config.CAPTURE_HEIGHT = bounds["height"]
    with mss.mss() as sct:
        return cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2BGR)


def run_window(session: CalibrationSession) -> bool:
    """Runs the OpenCV UI loop.

    Args:
        session: The calibration session.

    Returns:
        True if calibration completed, False if aborted.
    """
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW, session.on_mouse)
    try:
        while not session.finished:
            cv2.imshow(WINDOW, session.render())
            key = cv2.waitKey(20) & 0xFF
            if key in (ord("q"), 27):
                return False
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                return False  # window closed via the title-bar button
            if key == ord("r"):
                session.redo()
        return True
    finally:
        cv2.destroyAllWindows()


def main() -> int:
    """Runs the calibration workflow and saves ``calibration.json``.

    Returns:
        Process exit code.
    """
    session = CalibrationSession(image=capture_screenshot())
    if not run_window(session):
        print("Aborted; nothing saved.")
        return 1
    answers: Dict[str, Tuple[float, str, float]] = {}
    for name in BAR_NAMES:
        pct = ask_float(f"Enter {name} % threshold [0-100]: ", 0, 100)
        key = ask_key(f"Key to press when {name} is low: ")
        cd = ask_float(f"{name} cooldown in seconds [0-3600]: ", 0, 3600)
        answers[name] = (pct, key, cd)
    bars = session.bar_configs(answers)
    config.HEALTH = bars["Health"]
    config.MANA = bars["Mana"]
    config.save_config()
    print(f"Saved {config.CALIBRATION_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
