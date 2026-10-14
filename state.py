"""Thread-safe shared state bridging the vision, scheduler and action threads."""

import copy
import threading
from typing import Any, Dict, List


PENDING_BUFF_PRESSES: str = "pending_buff_presses"
LOOTING_ACTIVE: str = "looting_active"


class SharedState:
    """A dictionary-like store whose every access is guarded by a lock."""

    def __init__(self, initial: Dict[str, Any] | None = None) -> None:
        """Initializes the state.

        Args:
            initial: Optional initial key/value pairs. ``looting_active``
                defaults to ``False``.
        """
        self._lock: threading.Lock = threading.Lock()
        self._data: Dict[str, Any] = dict(initial or {})
        self._data.setdefault(PENDING_BUFF_PRESSES, [])
        self._data.setdefault(LOOTING_ACTIVE, False)

    def get(self, key: str, default: Any = None) -> Any:
        """Returns the value for ``key`` or ``default`` if absent.

        Args:
            key: State key.
            default: Value returned when the key is missing.

        Returns:
            The stored value (a copy) or ``default``.
        """
        with self._lock:
            return copy.deepcopy(self._data.get(key, default))

    def set(self, key: str, value: Any) -> None:
        """Sets a single key.

        Args:
            key: State key.
            value: Value to store.
        """
        with self._lock:
            self._data[key] = value

    def update(self, values: Dict[str, Any]) -> None:
        """Atomically sets several keys.

        Args:
            values: Mapping of keys to new values.
        """
        with self._lock:
            self._data.update(values)

    def snapshot(self) -> Dict[str, Any]:
        """Returns a consistent deep copy of the entire state.

        Returns:
            A copy of the state dictionary.
        """
        with self._lock:
            return copy.deepcopy(self._data)

    def append_buff_press(self, keybind: str) -> None:
        """Queues a scheduled buff keybind for the action thread.

        A keybind that is already queued is not queued again, so the queue is
        bounded by the number of distinct keybinds even if the action thread
        stalls (a backlog of identical presses would otherwise be fired in a
        burst once it recovers).

        Args:
            keybind: Key to be pressed by the action thread.
        """
        with self._lock:
            pending: List[str] = self._data[PENDING_BUFF_PRESSES]
            if keybind not in pending:
                pending.append(keybind)

    def toggle(self, key: str) -> bool:
        """Atomically flips a boolean entry.

        Args:
            key: State key holding a boolean (missing counts as ``False``).

        Returns:
            The new value.
        """
        with self._lock:
            value = not bool(self._data.get(key, False))
            self._data[key] = value
            return value

    def clear_buff_presses(self) -> None:
        """Discards all pending scheduled buff presses."""
        with self._lock:
            self._data[PENDING_BUFF_PRESSES] = []

    def drain_buff_presses(self) -> List[str]:
        """Atomically returns and clears the pending buff presses.

        Using a single locked operation guarantees that presses appended
        concurrently by the scheduler are never lost between read and clear.

        Returns:
            The pending keybinds in the order they were queued.
        """
        with self._lock:
            pending: List[str] = self._data[PENDING_BUFF_PRESSES]
            self._data[PENDING_BUFF_PRESSES] = []
            return pending
