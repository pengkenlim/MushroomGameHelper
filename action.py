"""Action module: keyboard simulation via pynput."""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Union

from pynput.keyboard import Controller as KeyboardController, Key, KeyCode, Listener
from pynput.mouse import Button as MouseButton, Controller as MouseController

import config
from logger import logger
from state import SharedState

KeyType = Union[Key, KeyCode]

SPECIAL_KEYS: Dict[str, object] = {
    "mouse_left": MouseButton.left,
    "mouse_right": MouseButton.right,
    "mouse_middle": MouseButton.middle,
    "media_play_pause": Key.media_play_pause,
    "media_volume_up": Key.media_volume_up,
    "media_volume_down": Key.media_volume_down,
    "media_volume_mute": Key.media_volume_mute,
}

# Left/right modifier variants are folded into one logical name so that a
# chord such as ``ctrl+l`` matches either physical Ctrl key.
_MODIFIER_ALIASES: Dict[str, str] = {
    "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "shift_l": "shift", "shift_r": "shift",
    "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "cmd_l": "cmd", "cmd_r": "cmd",
}


def normalize_key_name(name: str) -> str:
    """Maps left/right modifier variants onto their base name.

    Args:
        name: A ``pynput`` key name such as ``"ctrl_l"``.

    Returns:
        The base name (``"ctrl"``), or ``name`` unchanged for non-modifiers.
    """
    return _MODIFIER_ALIASES.get(name, name)


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
    """Toggles looting, repotting and rebuffing via two-key chords."""

    def __init__(
        self,
        state: SharedState,
        looting_key1: Optional[str] = None,
        looting_key2: Optional[str] = None,
        repot_key1: Optional[str] = None,
        repot_key2: Optional[str] = None,
        rebuff_key1: Optional[str] = None,
        rebuff_key2: Optional[str] = None,
        callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Creates the listener (not started until :meth:`start`)."""
        self._state: SharedState = state
        self._looting_key1: str = normalize_key_name(
            (looting_key1 or config.LOOTING_TOGGLE_1).strip().lower())
        self._looting_key2: str = normalize_key_name(
            (looting_key2 or config.LOOTING_TOGGLE_2).strip().lower())
        self._repot_key1: str = normalize_key_name(
            (repot_key1 or config.REPOT_TOGGLE_1).strip().lower())
        self._repot_key2: str = normalize_key_name(
            (repot_key2 or config.REPOT_TOGGLE_2).strip().lower())
        self._rebuff_key1: str = normalize_key_name(
            (rebuff_key1 or config.REBUFF_TOGGLE_1).strip().lower())
        self._rebuff_key2: str = normalize_key_name(
            (rebuff_key2 or config.REBUFF_TOGGLE_2).strip().lower())
        self._callback: Callable[[str], None] = callback or self._toggle_state
        self._pressed: Set[str] = set()
        self._pressed_lock: threading.Lock = threading.Lock()
        self._toggle_lock: threading.Lock = threading.Lock()
        self._listener: Optional[Listener] = None

    def _toggle_state(self, flag_name: str) -> None:
        """Atomically flips a named boolean in the shared state."""
        with self._toggle_lock:
            new_state = self._state.toggle(flag_name)
            logger.info(f"{flag_name} toggled: {flag_name}={new_state}")

    def _on_press(self, key: Union[Key, KeyCode, None]) -> None:
        """Backward-compatible alias for the chord-detection callback."""
        self.on_press(key)

    def toggle_looting(self) -> None:
        """Atomically flips ``looting_active`` in the shared state."""
        self._toggle_state("looting_active")

    def toggle_repot(self) -> None:
        """Atomically flips ``repot_active`` in the shared state."""
        self._toggle_state("repot_active")

    def toggle_rebuff(self) -> None:
        """Atomically flips ``rebuff_active`` in the shared state."""
        self._toggle_state("rebuff_active")

    def on_press(self, key: Union[Key, KeyCode, None]) -> None:
        """Records a key press and fires the callback on a matching chord."""
        name = normalize_key_name(normalize_key(key) or "")
        if not name:
            return
        fire: Optional[str] = None
        with self._pressed_lock:
            self._pressed.add(name)
            if {self._looting_key1, self._looting_key2}.issubset(self._pressed):
                self._pressed.clear()
                fire = "looting_active"
            elif {self._repot_key1, self._repot_key2}.issubset(self._pressed):
                self._pressed.clear()
                fire = "repot_active"
            elif {self._rebuff_key1, self._rebuff_key2}.issubset(self._pressed):
                self._pressed.clear()
                fire = "rebuff_active"
        if fire is not None:
            try:
                self._callback(fire)
            except Exception as exc:  # an exception would kill the listener
                logger.error(f"Toggle callback failed for {fire}: {exc}",
                             exc_info=True)

    def on_release(self, key: Union[Key, KeyCode, None]) -> None:
        """Forgets a released key.

        Args:
            key: Key reported by ``pynput``.
        """
        name = normalize_key_name(normalize_key(key) or "")
        if not name:
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
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.stop()
            if listener is not threading.current_thread():
                listener.join(timeout=1.0)  # do not leave a zombie thread
        with self._pressed_lock:
            self._pressed.clear()


class Action:
    """Simulates key presses and tracks held keys."""

    def __init__(self, state: SharedState | None = None) -> None:
        """Creates the keyboard controller."""
        self._keyboard: KeyboardController = KeyboardController()
        self._mouse: MouseController = MouseController()
        self._lock: threading.Lock = threading.Lock()
        self._held: Set[str] = set()
        self._last_pressed: Dict[str, float] = {}
        self._last_buff_input: float | None = None
        self._last_automated_input: float = 0.0
        self._loot_retrigger_time: float = 0.0
        self._loot_last_hold: Optional[float] = None
        self._state: SharedState = state or SharedState()

    @staticmethod
    def _resolve(name: str) -> KeyType | MouseButton:
        """Resolves a keybind name to a pynput key or mouse button.

        Args:
            name: Logical action name (in ``config.KEYBINDS``) or key name.

        Returns:
            A pynput key or mouse button object.
        """
        raw = config.KEYBINDS.get(name, name).lower().strip()
        if raw in SPECIAL_KEYS:
            return SPECIAL_KEYS[raw]
        if hasattr(Key, raw):
            return getattr(Key, raw)
        if len(raw) == 1:
            return KeyCode.from_char(raw)
        raise ValueError(f"Unknown keybind: {raw}")

    def press(self, name: str, duration: float = config.DEFAULT_PRESS_DURATION
              ) -> None:
        """Presses and releases a key after ``duration`` seconds.

        Args:
            name: Logical action name or key name.
            duration: Seconds to hold the key.
        """
        key = self._resolve(name)
        if isinstance(key, MouseButton):
            self._mouse.press(button=key, click_count=1)
            try:
                time.sleep(duration)
            finally:
                self._mouse.release(button=key)
        else:
            self._keyboard.press(key)
            try:
                time.sleep(duration)
            finally:
                self._keyboard.release(key)
        with self._lock:
            last_actions = list(self._state.get("last_actions", []))
            last_actions.append({"key": name, "time": time.time()})
            self._state.set("last_actions", last_actions[-3:])

    def hold(self, name: str) -> None:
        """Starts holding a key (no-op if already held).

        Args:
            name: Logical action name or key name.
        """
        with self._lock:
            if name not in self._held:
                key = self._resolve(name)
                if isinstance(key, MouseButton):
                    self._mouse.press(button=key, click_count=1)
                else:
                    self._keyboard.press(key)
                self._held.add(name)

    def release(self, name: str) -> None:
        """Releases a held key (no-op if not held).

        Args:
            name: Logical action name or key name.
        """
        with self._lock:
            if name in self._held:
                key = self._resolve(name)
                if isinstance(key, MouseButton):
                    self._mouse.release(button=key)
                else:
                    self._keyboard.release(key)
                self._held.discard(name)

    def release_all(self) -> None:
        """Releases every held key (one failure never skips the others)."""
        with self._lock:
            for name in list(self._held):
                try:
                    key = self._resolve(name)
                    if isinstance(key, MouseButton):
                        self._mouse.release(button=key)
                    else:
                        self._keyboard.release(key)
                except Exception as exc:
                    logger.error(f"Failed to release '{name}': {exc}")
            self._held.clear()

    def is_held(self, name: str) -> bool:
        """Tells whether a key is currently held.

        Args:
            name: Logical action name or key name.

        Returns:
            True if the key is in the held set.
        """
        with self._lock:
            return name in self._held

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

    def trigger(self, key: str, cooldown: float, resource: str = "") -> bool:
        """Presses ``key`` unless its cooldown has not elapsed.

        Args:
            key: Key name to press.
            cooldown: Minimum seconds since the previous press of ``key``.
            resource: Resource (``"health"``/``"mana"``) that caused the
                press, used for logging only.

        Returns:
            True if the key was pressed, False if suppressed by cooldown.
        """
        if key == config.LOOTING_KEYBIND.strip() and config.LOOTING_KEYBIND:
            logger.warning(
                f"Refusing to tap '{key}': it is the looting hold key.")
            return False

        now = time.perf_counter()
        if now - self._last_automated_input < config.GLOBAL_ACTION_COOLDOWN:
            return False

        with self._lock:
            last = self._last_pressed.get(key)
            if last is not None and now - last < cooldown:
                logger.warning(
                    f"Suppressed {key} press: cooldown active "
                    f"({cooldown - (now - last):.2f}s remaining)")
                return False
            self._last_pressed[key] = now

        self._last_automated_input = now
        if resource:
            logger.info(f"Triggered {key} due to low {resource}")
        self.press_async(key)
        with self._lock:
            last_actions = list(self._state.get("last_actions", []))
            last_actions.append({"key": key, "time": time.time()})
            self._state.set("last_actions", last_actions[-3:])
        return True

    def decide(self, snapshot: Dict[str, object]) -> None:
        """Triggers heal/mana keys from a state snapshot, honoring cooldowns and toggles.

        Args:
            snapshot: Copy of the shared state produced by the vision thread.
        """
        # Check if the Repot toggle is configured and currently active
        has_repot_toggles = bool(config.REPOT_TOGGLE_1.strip() and config.REPOT_TOGGLE_2.strip())
        repot_active = bool(snapshot.get("repot_active", False))
        
        # If toggles are configured but Repot is toggled OFF, suppress healing
        if has_repot_toggles and not repot_active:
            return

        if snapshot.get("health_low"):
            self.trigger(config.HEALTH.keybind, config.HEALTH.cooldown, "health")
        if snapshot.get("mana_low"):
            self.trigger(config.MANA.keybind, config.MANA.cooldown, "mana")

    def execute_buff_presses(self, keybinds: List[str]) -> None:
        """Presses scheduled buff keys one after another.

        Only presses if the relevant toggle is active. If no toggles are
        configured or all are off, buffs are suppressed.

        A global gap of ``config.BUFF_INPUT_COOLDOWN`` seconds is enforced
        between consecutive automated presses so keystrokes never overlap.

        Args:
            keybinds: Keys to press, in order.
        """
        # Check if any auto-action toggle is active
        # If repot or rebuff toggles exist, at least one must be ON
        repot_active = self._state.get("repot_active", False)
        rebuff_active = self._state.get("rebuff_active", False)
        
        # If both toggles are explicitly off, suppress all buffs
        # (If toggles aren't configured, they default to False, so we allow buffs)
        has_toggles = bool(config.REPOT_TOGGLE_1 and config.REPOT_TOGGLE_2) or \
                      bool(config.REBUFF_TOGGLE_1 and config.REBUFF_TOGGLE_2)
        
        if has_toggles and not (repot_active or rebuff_active):
            logger.debug("Suppressing buff presses: all toggles are OFF")
            return
        
        for keybind in keybinds:
            if keybind == config.LOOTING_KEYBIND.strip() and config.LOOTING_KEYBIND:
                logger.warning(
                    f"Skipping buff key '{keybind}': it is the looting hold key.")
                continue
            if self._last_buff_input is not None:
                wait = (config.BUFF_INPUT_COOLDOWN
                        - (time.perf_counter() - self._last_buff_input))
                if wait > 0:
                    time.sleep(wait)

            now = time.perf_counter()
            if now - self._last_automated_input < config.GLOBAL_ACTION_COOLDOWN:
                time.sleep(config.GLOBAL_ACTION_COOLDOWN -
                           (now - self._last_automated_input))
                now = time.perf_counter()

            try:
                self.press(keybind)
            finally:
                self._last_buff_input = now
                self._last_automated_input = now

    def manage_looting(self, looting_active: bool) -> None:
        """Rapidly taps the looting key to avoid input buffer conflicts.
        
        MapleStory Worlds limits simultaneous held keys. By switching to 
        rapid taps (machine-gun style), we free up the input buffer for 
        your movement and attack keys.
        """
        keybind = config.LOOTING_KEYBIND.strip()
        if not keybind:
            return

        if not looting_active:
            # Ensure the key is released when toggled off
            self.release(keybind)
            self._loot_last_hold = None
            return

        now = time.perf_counter()
        if now - self._last_automated_input < config.GLOBAL_ACTION_COOLDOWN:
            return

        self._last_automated_input = now

        # Tap the key every 0.2 seconds (200ms)
        # This mimics holding without occupying a permanent input slot.
        if self._loot_last_hold is None or now - self._loot_last_hold >= 0.2:
            self.press_async(keybind, duration=0.05)
            self._loot_last_hold = now
    def run_cycle(self, state: SharedState) -> None:
        """Runs one action cycle: scheduled buffs first, then reactive keys.

        Args:
            state: Shared state holding vision output and pending buffs.
        """
        pending = state.drain_buff_presses()
        if pending:
            self.execute_buff_presses(pending)
        snapshot = state.snapshot()
        self.manage_looting(bool(snapshot.get("looting_active", False)))
        self.decide(snapshot)
