"""Window manager module: locates the game window by its title."""

from typing import Any, Dict, Optional

from logger import logger


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


def get_window_bounds(window_title: str) -> Optional[Dict[str, int]]:
    """Finds a window whose title contains ``window_title`` (case-insensitive).

    ``pygetwindow`` is imported lazily because it raises on unsupported
    platforms (e.g. Linux) at import time. Every failure mode degrades to
    ``None`` so callers can fall back to the static capture region.

    Args:
        window_title: Substring to search for in window titles.

    Returns:
        ``{"top", "left", "width", "height"}`` of the first matching,
        non-minimized window, or None if there is no match, the title is empty
        or window lookup is unavailable.
    """
    needle = window_title.strip().lower()
    if not needle:
        return None
    try:
        import pygetwindow as gw
    except (ImportError, NotImplementedError) as exc:
        logger.warning(f"pygetwindow unavailable: {exc}")
        return None
    try:
        for win in gw.getAllWindows():
            if needle in str(win.title).lower() and _is_usable(win):
                return {"top": int(win.top), "left": int(win.left),
                        "width": int(win.width), "height": int(win.height)}
    except Exception as exc:  # incl. gw.PyGetWindowException
        logger.warning(f"Window lookup for '{window_title}' failed: {exc}")
    return None
