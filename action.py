"""Action module: keyboard simulation via pynput."""

import threading
import time
from typing import Dict, List, Set, Union

from pynput.keyboard import Controller, Key, KeyCode

import config
from state import SharedState

KeyType = Union[Key, KeyCode]


class Action:
    """Simulates key presses and tracks held keys."""

    def __init__(self) -> None:
        """Creates the keyboard controller."""
        self._keyboard: Controller = Controller()
        self._lock: threading.Lock = threading.Lock()
        self._held: Set[str] = set()
        self._last_pressed: Dict[str, float] = {}
        self._last_buff_input: float | None = None

    @staticmethod
    def _resolve(name: str) -> KeyType:
        """Resolves a keybind name to a pynput key.

        Args:
            name: Logical action name (in ``config.KEYBINDS``) or key name.

        Returns:
            A pynput key object.
        """
        raw = config.KEYBINDS.get(name, name)
        special = getattr(Key, raw if len(raw) == 1 else raw.lower(), None)
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

    def press_async(
        self, name: str, duration: float = config.DEFAULT_PRESS_DURATION
    ) -> None:
        """Presses a key and releases it later without blocking the caller.

        Args:
            name: Logical action name or key name.
            duration: Seconds to hold the key before a timer releases it.
        """
        self.hold(name)
        timer = threading.Timer(duration, self.release, args=(name,))
        timer.daemon = True
        timer.start()

    def trigger(self, key: str, cooldown: float) -> bool:
        """Presses ``key`` unless its cooldown has not elapsed.

        Args:
            key: Key name to press.
            cooldown: Minimum seconds since the previous press of ``key``.

        Returns:
            True if the key was pressed, False if suppressed by cooldown.
        """
        now = time.perf_counter()
        with self._lock:
            last = self._last_pressed.get(key)
            if last is not None and now - last < cooldown:
                return False
            self._last_pressed[key] = now
        self.press_async(key)
        return True

    def decide(self, snapshot: Dict[str, object]) -> None:
        """Triggers heal/mana keys from a state snapshot, honoring cooldowns.

        Args:
            snapshot: Copy of the shared state produced by the vision thread.
        """
        if snapshot.get("health_low"):
            self.trigger(config.HEALTH.keybind, config.HEALTH.cooldown)
        if snapshot.get("mana_low"):
            self.trigger(config.MANA.keybind, config.MANA.cooldown)

    def execute_buff_presses(self, keybinds: List[str]) -> None:
        """Presses scheduled buff keys one after another.

        A global gap of ``config.BUFF_INPUT_COOLDOWN`` seconds is enforced
        between consecutive automated presses so keystrokes never overlap.

        Args:
            keybinds: Keys to press, in order.
        """
        for keybind in keybinds:
            if self._last_buff_input is not None:
                wait = (config.BUFF_INPUT_COOLDOWN
                        - (time.perf_counter() - self._last_buff_input))
                if wait > 0:
                    time.sleep(wait)
            try:
                self.press(keybind)
            finally:
                self._last_buff_input = time.perf_counter()

    def run_cycle(self, state: SharedState) -> None:
        """Runs one action cycle: scheduled buffs first, then reactive keys.

        Args:
            state: Shared state holding vision output and pending buffs.
        """
        pending = state.drain_buff_presses()
        if pending:
            self.execute_buff_presses(pending)
        self.decide(state.snapshot())
