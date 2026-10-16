"""Action module: keyboard simulation via pynput."""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

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

# Dispatcher priorities. Lower number = higher priority = fired first.
PRIORITY_HEAL: int = 0
PRIORITY_MANA: int = 1
PRIORITY_BUFF: int = 2
PRIORITY_LOOT: int = 3

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


def bot_key_names() -> Set[str]:
    """Returns the normalized set of keys the bot itself presses.

    pynput's Listener also observes the bot's own synthetic key events, so
    they must be excluded when counting what the user is physically holding.

    Returns:
        Normalized key names owned by the automation.
    """
    raw = [
        config.HEALTH.keybind, config.MANA.keybind, config.LOOTING_KEYBIND,
        config.LOOTING_TOGGLE_1, config.LOOTING_TOGGLE_2,
        config.REPOT_TOGGLE_1, config.REPOT_TOGGLE_2,
        config.REBUFF_TOGGLE_1, config.REBUFF_TOGGLE_2,
    ]
    for schedule in config.load_schedules():
        raw.append(schedule.keybind)
    return {normalize_key_name(str(k).strip().lower()) for k in raw if k}


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
        self._physical: Set[str] = set()
        self._pressed_lock: threading.Lock = threading.Lock()
        self._toggle_lock: threading.Lock = threading.Lock()
        self._listener: Optional[Listener] = None

    def _toggle_state(self, flag_name: str) -> None:
        """Atomically flips a named boolean in the shared state."""
        with self._toggle_lock:
            new_state = self._state.toggle(flag_name)
            logger.info(f"{flag_name} toggled: {flag_name}={new_state}")

    @staticmethod
    def _bot_key_names() -> Set[str]:
        """Returns the normalized set of keys the bot itself presses."""
        raw = [
            config.HEALTH.keybind, config.MANA.keybind, config.LOOTING_KEYBIND,
            config.LOOTING_TOGGLE_1, config.LOOTING_TOGGLE_2,
            config.REPOT_TOGGLE_1, config.REPOT_TOGGLE_2,
            config.REBUFF_TOGGLE_1, config.REBUFF_TOGGLE_2,
        ]
        for schedule in config.load_schedules():
            raw.append(schedule.keybind)
        return {normalize_key_name(str(k).strip().lower()) for k in raw if k}

    def _publish_physical_count(self) -> None:
        """Publishes the count of physical action keys held to SharedState."""
        bot_keys = self._bot_key_names()
        ignored = config.IGNORED_PHYSICAL_KEYS
        with self._pressed_lock:
            count = len(self._physical - bot_keys - ignored)
        try:
            self._state.set("physical_keys_held", count)
        except Exception as exc:
            logger.debug(f"Could not publish physical key count: {exc}")

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
        import time
        try:
            self._state.set("last_input_timestamp", time.perf_counter())
        except Exception as exc:
            logger.debug(f"Could not record user input timestamp: {exc}")
        name = normalize_key_name(normalize_key(key) or "")
        if not name:
            return
        fire: Optional[str] = None
        with self._pressed_lock:
            self._pressed.add(name)
            self._physical.add(name)
            if {self._looting_key1, self._looting_key2}.issubset(self._pressed):
                self._pressed.clear()
                fire = "looting_active"
            elif {self._repot_key1, self._repot_key2}.issubset(self._pressed):
                self._pressed.clear()
                fire = "repot_active"
            elif {self._rebuff_key1, self._rebuff_key2}.issubset(self._pressed):
                self._pressed.clear()
                fire = "rebuff_active"
        self._publish_physical_count()
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
        import time
        try:
            self._state.set("last_input_timestamp", time.perf_counter())
        except Exception as exc:
            logger.debug(f"Could not record user release timestamp: {exc}")
        name = normalize_key_name(normalize_key(key) or "")
        if not name:
            return
        with self._pressed_lock:
            self._pressed.discard(name)
            self._physical.discard(name)
        self._publish_physical_count()

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
            self._physical.clear()
        self._publish_physical_count()


class Action:
    """Simulates key presses and tracks held keys."""

    def __init__(self, state: SharedState | None = None) -> None:
        """Creates the keyboard controller."""
        self._keyboard: KeyboardController = KeyboardController()
        self._mouse: MouseController = MouseController()
        self._lock: threading.Lock = threading.Lock()
        self._held: Set[str] = set()
        self._last_pressed: Dict[str, float] = {}
        # Timestamp of the last automated press (enforces GLOBAL_RESOLUTION_LIMIT)
        self._last_auto_press_time: float = 0.0
        # Timestamp until which the game is assumed to be animating a buff
        # (enforces BUFF_CAST_LOCKOUT)
        self._buff_lockout_until: float = 0.0
        self._state: SharedState = state or SharedState()
        # Dispatcher state
        self._queue: List[Tuple[int, str, str]] = []   # (priority, key, reason)
        self._last_automated_input: float = 0.0
        self._last_buff_input: Optional[float] = None

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
        self.hold(name)
        try:
            time.sleep(duration)
        finally:
            self.release(name)
        self._state.set("last_input_timestamp", time.perf_counter())

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

    def _can_press(self, is_buff: bool) -> bool:
        """Checks if an automated press is allowed right now.

        Args:
            is_buff: True if the pending press is a buff.

        Returns:
            True if the press is allowed, False if it should be deferred.
        """
        now = time.perf_counter()
        if now - self._last_auto_press_time < config.GLOBAL_RESOLUTION_LIMIT:
            return False
        if now < self._buff_lockout_until:
            return False
        return True

    def _record_press(self, is_buff: bool) -> None:
        """Records that an automated press just occurred.

        Args:
            is_buff: True if the press was a buff (triggers the lockout).
        """
        now = time.perf_counter()
        self._last_auto_press_time = now
        if is_buff:
            self._buff_lockout_until = now + config.BUFF_CAST_LOCKOUT
            logger.debug(
                f"Buff lockout active until {self._buff_lockout_until:.2f}")

    def trigger(self, key: str, cooldown: float, resource: str = "") -> bool:
        """Presses ``key`` unless cooldown or resolution limit blocks it.

        Args:
            key: Key name to press.
            cooldown: Minimum seconds since the previous press of ``key``.
            resource: Resource (``"health"``/``"mana"``) that caused the
                press, used for logging only.

        Returns:
            True if the key was pressed, False if suppressed.
        """
        if key == config.LOOTING_KEYBIND.strip() and config.LOOTING_KEYBIND:
            logger.warning(
                f"Refusing to tap '{key}': it is the looting hold key.")
            return False
        if not self._can_press(is_buff=False):
            return False

        now = time.perf_counter()

        last_input = self._state.get("last_input_timestamp", 0.0)
        if now - last_input < config.GLOBAL_RESOLUTION_LIMIT:
            logger.debug(
                f"Deferring {key}: resolution limit active "
                f"({config.GLOBAL_RESOLUTION_LIMIT - (now - last_input):.2f}s remaining)")
            return False

        with self._lock:
            last = self._last_pressed.get(key)
            if last is not None and now - last < cooldown:
                logger.warning(
                    f"Suppressed {key} press: cooldown active "
                    f"({cooldown - (now - last):.2f}s remaining)")
                return False
            self._last_pressed[key] = now

        if resource:
            logger.info(f"Triggered {key} due to low {resource}")
        self._record_press(is_buff=False)
        self.press_async(key)

        with self._lock:
            last_actions = list(self._state.get("last_actions", []))
            last_actions.append({"key": key, "time": time.time()})
            self._state.set("last_actions", last_actions[-3:])

        self._state.set("last_input_timestamp", time.perf_counter())
        return True

    def execute_buff_presses(self, keybinds: List[str]) -> None:
        """Presses a single scheduled buff key per cycle using non-blocking async.

        If multiple buffs are queued, only the first is processed this cycle.
        The rest are pushed back into the shared state to be processed on
        subsequent 100ms ticks, preventing the action thread from blocking.

        Args:
            keybinds: Keys to press, in order.
        """
        for keybind in keybinds:
            if keybind == config.LOOTING_KEYBIND.strip() and config.LOOTING_KEYBIND:
                logger.warning(f"Skipping buff key '{keybind}': looting hold key.")
                continue

            # Only process the first valid buff this cycle
            now = time.perf_counter()
            if self._last_buff_input is not None:
                wait = config.BUFF_INPUT_COOLDOWN - (now - self._last_buff_input)
                if wait > 0:
                    # Not ready yet, push all remaining back to queue and exit
                    for kb in keybinds[keybinds.index(keybind):]:
                        self._state.append_buff_press(kb)
                    return

            self._last_buff_input = now
            logger.info(f"Pressing buff: {keybind}")
            self.press_async(keybind)

            # Push the rest back to the queue for the next tick
            remaining = keybinds[keybinds.index(keybind) + 1:]
            for kb in remaining:
                self._state.append_buff_press(kb)
            return

    def manage_looting(self, looting_active: bool, user_is_acting: bool) -> None:
        """Holds the looting key if active and no user conflicts exist.

        Args:
            looting_active: Current toggle state from SharedState.
            user_is_acting: True if the user is holding a non-movement key.
        """
        keybind = config.LOOTING_KEYBIND.strip()
        if not keybind:
            return

        if not looting_active:
            self.release(keybind)
            return

        if user_is_acting:
            self.release(keybind)
        else:
            self.hold(keybind)

    def _enqueue(self, priority: int, key: str, reason: str) -> None:
        """Adds a press request to the dispatcher queue.

        Requests are idempotent: an identical (priority, key, reason) triple
        already waiting is not added again, so the queue cannot grow without
        bound while the action thread is busy.

        Args:
            priority: Dispatcher priority (lower fires first).
            key: Keybind to press.
            reason: Human-readable cause, used for logging and dedup.
        """
        if not key:
            return
        with self._lock:
            entry = (priority, key, reason)
            if entry in self._queue:
                return
            self._queue.append(entry)
            if len(self._queue) > config.ACTION_QUEUE_MAX:
                # Drop the lowest-priority (highest number) overflow entries.
                self._queue.sort(key=lambda item: item[0])
                del self._queue[config.ACTION_QUEUE_MAX:]

    def _pop_next(self) -> Optional[Tuple[int, str, str]]:
        """Removes and returns the highest-priority queued request.

        Returns:
            The ``(priority, key, reason)`` tuple, or None if the queue is empty.
        """
        with self._lock:
            if not self._queue:
                return None
            self._queue.sort(key=lambda item: item[0])
            return self._queue.pop(0)

    def _peek_priority(self) -> Optional[int]:
        """Returns the priority of the next queued request without removing it.

        Returns:
            The best (lowest) priority currently queued, or None if empty.
        """
        with self._lock:
            if not self._queue:
                return None
            return min(item[0] for item in self._queue)

    def _dispatch(self, snapshot: Dict[str, object]) -> None:
        """Fires at most one queued action per cycle.

        Enforces a global minimum gap between any two automated presses so the
        game engine's limited input buffer is never given two simultaneous
        key events. Low-priority actions (buff, loot) are deferred — not
        dropped — while the user is physically holding many keys, because
        engines like MapleStory Worlds cancel synthetic input once their input
        slots are full. Critical actions (heal, mana) fire regardless unless
        ``config.DEFER_CRITICAL_ACTIONS`` is True.

        Args:
            snapshot: Current shared-state snapshot.
        """
        best = self._peek_priority()
        if best is None:
            return
        now = time.perf_counter()
        last_input = self._state.get("last_input_timestamp", 0.0)
        if now - last_input < config.GLOBAL_RESOLUTION_LIMIT:
            logger.debug(
                f"Deferring action: resolution limit active "
                f"({config.GLOBAL_RESOLUTION_LIMIT - (now - last_input):.2f}s remaining)")
            return
        if now - self._last_automated_input < config.GLOBAL_ACTION_COOLDOWN:
            return  # budget exhausted; retried on the next 10 Hz tick
        critical = best <= PRIORITY_MANA
        if not critical or config.DEFER_CRITICAL_ACTIONS:
            held = int(snapshot.get("physical_keys_held", 0) or 0)
            if held >= config.MAX_PHYSICAL_KEYS:
                logger.debug(
                    f"Deferring action: user holds {held} keys "
                    f"(limit {config.MAX_PHYSICAL_KEYS})")
                return  # request stays queued and is retried
        entry = self._pop_next()
        if entry is None:
            return
        priority, key, reason = entry
        is_buff = priority == PRIORITY_BUFF
        if not self._can_press(is_buff=is_buff):
            self._queue.append(entry)
            return
        # Per-key cooldown still applies (prevents heal spam).
        per_key = config.HEALTH.cooldown if reason == "health" else (
            config.MANA.cooldown if reason == "mana" else 0.0)
        with self._lock:
            last = self._last_pressed.get(key)
            if per_key and last is not None and now - last < per_key:
                self._queue.append(entry)   # requeue, still on cooldown
                return
            self._last_pressed[key] = now
        self._last_automated_input = time.perf_counter()
        logger.info(f"Dispatching '{key}' ({reason})")
        self._record_press(is_buff=is_buff)
        self.press_async(key)
        self._state.set("last_input_timestamp", time.perf_counter())
        with self._lock:
            last_actions = list(self._state.get("last_actions", []))
            last_actions.append({"key": key, "time": time.time()})
            self._state.set("last_actions", last_actions[-3:])

    def _collect(self, state: SharedState, snapshot: Dict[str, object]) -> None:
        """Turns the current world state into queued press requests.

        No key is pressed here; this only enqueues. ``_dispatch`` decides what
        actually fires and when.

        Args:
            state: Shared state (used to drain the buff queue).
            snapshot: Consistent copy of the shared state.
        """
        repot = bool(snapshot.get("repot_active", False))
        rebuff = bool(snapshot.get("rebuff_active", False))
        looting = bool(snapshot.get("looting_active", False))

        # Drain scheduled buffs every cycle so the queue never backs up, but
        # only enqueue them while rebuffing is enabled.
        pending = state.drain_buff_presses()
        if pending and rebuff:
            for keybind in pending:
                self._enqueue(PRIORITY_BUFF, keybind, "buff")
        loot_key = config.LOOTING_KEYBIND.strip()
        if not looting:
            self.release(loot_key) if loot_key else None
            self._last_loot_tap = 0.0
        elif loot_key and (
                time.perf_counter() - self._last_loot_tap
                >= config.LOOT_TAP_INTERVAL):
            self._enqueue(PRIORITY_LOOT, loot_key, "loot")
            self._last_loot_tap = time.perf_counter()
        if repot:
            if snapshot.get("health_low"):
                self._enqueue(PRIORITY_HEAL, config.HEALTH.keybind, "health")
            if snapshot.get("mana_low"):
                self._enqueue(PRIORITY_MANA, config.MANA.keybind, "mana")

    def run_cycle(self, state: SharedState) -> None:
        """Runs one action cycle with context-aware looting."""
        pending = state.drain_buff_presses()
        snapshot = state.snapshot()

        looting_active = bool(snapshot.get("looting_active", False))
        user_is_acting = int(snapshot.get("physical_keys_held", 0)) > 0
        bot_wants_to_act = bool(pending) or snapshot.get("health_low") or snapshot.get("mana_low")

        # Pre-emptively release loot if there's a conflict
        if looting_active and (user_is_acting or bot_wants_to_act):
            self.release(config.LOOTING_KEYBIND.strip())

        # Execute bot actions (only processes one buff per tick now)
        if pending:
            self.execute_buff_presses(pending)
        self.decide(snapshot)

        # Re-evaluate and hold loot if the coast is clear
        self.manage_looting(looting_active, user_is_acting)
