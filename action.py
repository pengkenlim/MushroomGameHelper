"""Action module: keyboard simulation via pynput."""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Union

from pynput.keyboard import Controller, Key, KeyCode, Listener

import config
from state import SharedState

KeyType = Union[Key, KeyCode]

# Left/right modifier variants are folded into one logical name so that a
# chord such as ``ctrl+l`` matches either physical Ctrl key.
_MODIFIER_ALIASES: Dict[str, str] = {
    "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "shift_l": "shift", "shift_r": "shift",
    "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "cmd_l": "cmd", "cmd_r": "cmd",
}


def normalize_key(key: Union[Key, KeyCode, None]) -> Optional[str]:
    """Converts a pynput key event into a lowercase logical key name.

    Args:
        key: Key reported by a ``pynput`` listener.

    Returns:
        A name such as ``"ctrl"``, ``"l"`` or ``"space"``; ``None`` if the key
        has no usable name.
    """
    if isinstance(key, Key):
        return _MODIFIER_ALIASES.get(key.name, key.name)
    char = getattr(key, "char", None)
    if not char:
        return None
    if len(char) == 1 and 1 <= ord(char) <= 26:
        # With Ctrl held some platforms report control codes (Ctrl+L -> \x0c).
        char = chr(ord(char) + 96)
    return char.lower()


class KeyComboListener:
    """Toggles looting when a two-key chord is pressed simultaneously.

    The listener only *observes* the keyboard and flips
    ``looting_active`` in the :class:`SharedState`; it never presses keys.
    ``Action.manage_looting`` is solely responsible for physical key holds.

    Chord detection: every key press adds its normalized name to a set of
    currently pressed keys and every release removes it. As soon as both
    ``toggle_key_1`` and ``toggle_key_2`` are in the set at the same time the
    callback fires and the set is cleared, so key auto-repeat or a slow
    release cannot toggle repeatedly; the chord must be released and pressed
    again to toggle once more.

    Thread safety: ``pynput`` invokes the handlers on its own thread. The
    pressed-key set and the read-modify-write of the toggle are guarded by
    locks, and the state itself is a lock-protected :class:`SharedState`.
    """

    def __init__(
        self,
        state: SharedState,
        key1: Optional[str] = None,
        key2: Optional[str] = None,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """Creates the listener (not started until :meth:`start`).

        Args:
            state: Shared state whose ``looting_active`` flag is toggled.
            key1: First chord key; defaults to ``config.LOOTING.toggle_key_1``.
            key2: Second chord key; defaults to ``config.LOOTING.toggle_key_2``.
            callback: Called when the chord is detected; defaults to
                :meth:`toggle_looting`.
        """
        self._state: SharedState = state
        self._key1: str = (key1 or config.LOOTING.toggle_key_1).strip().lower()
        self._key2: str = (key2 or config.LOOTING.toggle_key_2).strip().lower()
        self._callback: Callable[[], None] = callback or self.toggle_looting
        self._pressed: Set[str] = set()
        self._pressed_lock: threading.Lock = threading.Lock()
        self._toggle_lock: threading.Lock = threading.Lock()
        self._listener: Optional[Listener] = None

    def toggle_looting(self) -> None:
        """Atomically flips ``looting_active`` in the shared state."""
        with self._toggle_lock:
            current_state = bool(self._state.get("looting_active", False))
            self._state.update({"looting_active": not current_state})

    def on_press(self, key: Union[Key, KeyCode, None]) -> None:
        """Records a key press and fires the callback on a full chord.

        Args:
            key: Key reported by ``pynput``.
        """
        name = normalize_key(key)
        if name is None:
            return
        with self._pressed_lock:
            self._pressed.add(name)
            if self._key1 in self._pressed and self._key2 in self._pressed:
                self._pressed.clear()
                fire = True
            else:
                fire = False
        if fire:
            self._callback()

    def on_release(self, key: Union[Key, KeyCode, None]) -> None:
        """Forgets a released key.

        Args:
            key: Key reported by ``pynput``.
        """
        name = normalize_key(key)
        if name is None:
            return
        with self._pressed_lock:
            self._pressed.discard(name)

    def start(self) -> None:
        """Starts listening on a background thread (no-op if running)."""
        if self._listener is not None:
            return
        self._listener = Listener(on_press=self.on_press,
                                  on_release=self.on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        """Stops listening and forgets any pressed keys."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        with self._pressed_lock:
            self._pressed.clear()


class Action:
    """Simulates key presses and tracks held keys."""

    def __init__(self) -> None:
        """Creates the keyboard controller."""
        self._keyboard: Controller = Controller()
        self._lock: threading.Lock = threading.Lock()
        self._held: Set[str] = set()
        self._last_pressed: Dict[str, float] = {}
        self._last_buff_input: float | None = None
        self._loot_retrigger_time: float = 0.0

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

    def manage_looting(self, snapshot: Dict[str, Any]) -> None:
        """Holds the looting key while looting is active, re-triggering it.

        Games may ignore a key that has been held down for a long time. While
        looting is active the key is therefore held permanently, but once
        ``config.LOOTING.retrigger_interval`` seconds have passed since it was
        (re)pressed it is released, given 50 ms for the game to register the
        release, and held again; the interval timer is then restarted. When
        looting is switched off the key is released immediately.

        Only this method touches the physical key; the toggle listener merely
        updates ``looting_active`` in the shared state.

        Args:
            snapshot: Copy of the shared state containing ``looting_active``.
        """
        looting_key = config.LOOTING.keybind
        active = bool(snapshot.get("looting_active", False))
        held = looting_key in self._held
        if not active:
            if held:
                self.release(looting_key)
        elif not held:
            self.hold(looting_key)
            self._loot_retrigger_time = time.perf_counter()
        elif (time.perf_counter() - self._loot_retrigger_time
              > config.LOOTING.retrigger_interval):
            self.release(looting_key)
            time.sleep(0.05)
            self.hold(looting_key)
            self._loot_retrigger_time = time.perf_counter()

    def run_cycle(self, state: SharedState) -> None:
        """Runs one action cycle: scheduled buffs first, then reactive keys.

        Args:
            state: Shared state holding vision output and pending buffs.
        """
        pending = state.drain_buff_presses()
        if pending:
            self.execute_buff_presses(pending)
        self.decide(state.snapshot())
        self.manage_looting(state.snapshot())
