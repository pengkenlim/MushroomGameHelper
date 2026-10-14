"""Action module: keyboard simulation via pynput."""

import threading
import time
from typing import Dict, Set, Union

from pynput.keyboard import Controller, Key, KeyCode

import config

KeyType = Union[Key, KeyCode]


class Action:
    """Simulates key presses and tracks held keys."""

    def __init__(self) -> None:
        """Creates the keyboard controller."""
        self._keyboard: Controller = Controller()
        self._lock: threading.Lock = threading.Lock()
        self._held: Set[str] = set()

    @staticmethod
    def _resolve(name: str) -> KeyType:
        """Resolves a keybind name to a pynput key.

        Args:
            name: Logical action name (in ``config.KEYBINDS``) or key name.

        Returns:
            A pynput key object.
        """
        raw = config.KEYBINDS.get(name, name)
        special = getattr(Key, raw, None)
        return special if isinstance(special, Key) else KeyCode.from_char(raw)

    def press(self, name: str, duration: float = config.DEFAULT_PRESS_DURATION
              ) -> None:
        """Presses and releases a key after ``duration`` seconds.

        Args:
            name: Logical action name or key name.
            duration: Seconds to hold the key.
        """
        key = self._resolve(name)
        self._keyboard.press(key)
        try:
            time.sleep(duration)
        finally:
            self._keyboard.release(key)

    def hold(self, name: str) -> None:
        """Starts holding a key (no-op if already held).

        Args:
            name: Logical action name or key name.
        """
        with self._lock:
            if name not in self._held:
                self._keyboard.press(self._resolve(name))
                self._held.add(name)

    def release(self, name: str) -> None:
        """Releases a held key (no-op if not held).

        Args:
            name: Logical action name or key name.
        """
        with self._lock:
            if name in self._held:
                self._keyboard.release(self._resolve(name))
                self._held.discard(name)

    def release_all(self) -> None:
        """Releases every held key."""
        with self._lock:
            for name in list(self._held):
                self._keyboard.release(self._resolve(name))
            self._held.clear()

    def decide(self, snapshot: Dict[str, object]) -> None:
        """Performs actions based on a state snapshot.

        Args:
            snapshot: Copy of the shared state produced by the vision thread.
        """
        if snapshot.get("health_low"):
            self.press("heal")
        if snapshot.get("targets_visible"):
            self.hold("right")
        else:
            self.release("right")
