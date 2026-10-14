"""Window manager module: locates the game window by its title."""

from typing import Any, Dict, List, Optional

from logger import logger

Bounds = Dict[str, int]


def _is_usable(win: Any) -> bool:
    """Checks that a window is visible-sized and not minimized.

    Args:
        win: A ``pygetwindow`` window object.

    Returns:
        True if the window has a positive size and is not minimized.
    """
    if getattr(win, "isMinimized", False):
        return False
    return int(win.width) > 0 and int(win.height) > 0


def get_screen_bounds() -> Optional[Bounds]:
    """Returns the bounds of the whole virtual screen (all monitors).

    Uses ``mss`` monitor 0, the union of every monitor, so a game on a
    secondary monitor is not clamped away. It contains the primary monitor.

    Returns:
        ``{"top", "left", "width", "height"}``, or None if unavailable.
    """
    try:
        import mss
        with mss.mss() as sct:
            mon = sct.monitors[0]
            return {"top": int(mon["top"]), "left": int(mon["left"]),
                    "width": int(mon["width"]), "height": int(mon["height"])}
    except Exception as exc:  # mss raises various errors without a display
        logger.warning(f"Could not read screen size from mss: {exc}")
        return None


def clamp_to_screen(bounds: Bounds, screen: Bounds) -> Optional[Bounds]:
    """Intersects window bounds with the screen rectangle.

    A window dragged partly off-screen is cropped to the visible part; one
    that is entirely off-screen (e.g. the ``-32000`` coordinates Windows
    reports for minimized windows) yields None.

    Args:
        bounds: Window ``top``/``left``/``width``/``height``.
        screen: Screen ``top``/``left``/``width``/``height``.

    Returns:
        The visible part of the window, or None if it has no visible area.
    """
    left = max(bounds["left"], screen["left"])
    top = max(bounds["top"], screen["top"])
    right = min(bounds["left"] + bounds["width"],
                screen["left"] + screen["width"])
    bottom = min(bounds["top"] + bounds["height"],
                 screen["top"] + screen["height"])
    if right - left <= 0 or bottom - top <= 0:
        return None
    return {"top": top, "left": left,
            "width": right - left, "height": bottom - top}


def get_window_bounds(title: str) -> Optional[Bounds]:
    """Finds the game window and returns its bounds clamped to the screen.

    An exact (case-insensitive) title match is preferred; otherwise the first
    window whose title contains ``title`` is used. ``pygetwindow`` is imported
    lazily because it raises on unsupported platforms at import time, and
    every call into it is guarded because the library is fragile across
    operating systems. Every failure mode degrades to ``None`` so callers can
    keep the last good region or fall back to the static coordinates.

    Args:
        title: Window title (or part of it) to look for.

    Returns:
        ``{"top", "left", "width", "height"}`` of the visible part of the
        window, or None if the title is empty, there is no match, the window
        is minimized (width/height <= 0), completely off-screen, or window
        lookup is unavailable.
    """
    needle = title.strip().lower()
    if not needle:
        return None
    try:
        import pygetwindow as gw
    except (ImportError, NotImplementedError) as exc:
        logger.warning(f"pygetwindow unavailable: {exc}")
        return None
    except Exception as exc:
        logger.warning(f"pygetwindow failed to load: {exc}")
        return None
    try:
        windows: List[Any] = list(gw.getAllWindows())
    except Exception as exc:  # incl. gw.PyGetWindowException
        logger.warning(f"Window lookup for '{title}' failed: {exc}")
        return None
    exact: Optional[Bounds] = None
    partial: Optional[Bounds] = None
    for win in windows:
        try:
            name = str(win.title).strip().lower()
            if needle not in name or not _is_usable(win):
                continue
            found = {"top": int(win.top), "left": int(win.left),
                     "width": int(win.width), "height": int(win.height)}
        except Exception as exc:  # one broken window must not abort the scan
            logger.debug(f"Skipping unreadable window: {exc}")
            continue
        if name == needle:
            exact = found
            break
        if partial is None:
            partial = found
    bounds = exact or partial
    if bounds is None:
        return None
    screen = get_screen_bounds()
    if screen is None:
        return bounds
    clamped = clamp_to_screen(bounds, screen)
    if clamped is None:
        logger.warning(f"Window '{title}' is entirely off-screen: {bounds}")
    elif clamped != bounds:
        logger.warning(
            f"Window '{title}' is partly off-screen; capture clamped from "
            f"{bounds} to {clamped}. Bar positions may be misaligned.")
    return clamped
