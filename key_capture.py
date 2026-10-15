"""Captures a single key press or mouse click for the GUI's keybind fields."""

import threading
import time
from typing import Dict, List, Optional, Union

from pynput import keyboard, mouse

from action import normalize_key

POLL_INTERVAL_S: float = 0.05

# Only these buttons can be re-created by ``Action`` (see ``SPECIAL_KEYS``).
MOUSE_NAMES: Dict[mouse.Button, str] = {
    mouse.Button.left: "mouse_left",
    mouse.Button.right: "mouse_right",
    mouse.Button.middle: "mouse_middle",
}


def capture_single_input(
    timeout: Optional[float] = None,
    cancel: Optional[threading.Event] = None,
) -> Optional[str]:
    """Waits for one key press or mouse click anywhere on the desktop.

    The returned name uses the same vocabulary as the keybind settings:
    modifiers are folded into ``ctrl``/``shift``/``alt``/``cmd``, other keys
    are their ``pynput`` names (``f5``, ``space``, ``media_play_pause``) or
    the lowercase character, and mouse buttons are ``mouse_left``,
    ``mouse_right`` and ``mouse_middle``. Key releases, mouse releases, extra
    mouse buttons and keys without a usable name are ignored.

    Args:
        timeout: Seconds to wait before giving up; ``None`` waits forever.
        cancel: Optional event; setting it abandons the capture.

    Returns:
        The captured name, or ``None`` if the wait timed out or was cancelled.

    Raises:
        RuntimeError: If the system input listeners stop unexpectedly.
        Exception: Whatever a listener raised while starting (for example a
            missing display or missing macOS permissions).
    """
    done = threading.Event()
    lock = threading.Lock()
    captured: List[str] = []

    def accept(name: Optional[str]) -> bool:
        """Stores the first usable name; returns True to stop the listener."""
        if not name:
            return False
        with lock:
            if captured:
                return True
            captured.append(name)
        done.set()
        return True

    def on_press(key: Union[keyboard.Key, keyboard.KeyCode, None]) -> bool:
        """Handles a key press; returning False stops the listener."""
        return not accept(normalize_key(key))

    def on_click(_x: int, _y: int, button: mouse.Button,
                 pressed: bool) -> bool:
        """Handles a mouse click; returning False stops the listener."""
        return not (pressed and accept(MOUSE_NAMES.get(button)))

    listeners = (keyboard.Listener(on_press=on_press),
                 mouse.Listener(on_click=on_click))
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        for listener in listeners:
            listener.start()
        while not done.wait(POLL_INTERVAL_S):
            if cancel is not None and cancel.is_set():
                return None
            if deadline is not None and time.monotonic() >= deadline:
                return None
            if all(listener.is_alive() for listener in listeners):
                continue
            if done.is_set():
                break
            for listener in listeners:
                if not listener.is_alive():
                    listener.join()  # re-raises the listener's own error
            raise RuntimeError("The input listener stopped unexpectedly.")
        return captured[0] if captured else None
    finally:
        for listener in listeners:
            listener.stop()
