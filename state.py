"""Thread-safe shared state bridging the vision and action threads."""

import copy
import threading
from typing import Any, Dict


class SharedState:
    """A dictionary-like store whose every access is guarded by a lock."""

    def __init__(self, initial: Dict[str, Any] | None = None) -> None:
        """Initializes the state.

        Args:
            initial: Optional initial key/value pairs.
        """
        self._lock: threading.Lock = threading.Lock()
        self._data: Dict[str, Any] = dict(initial or {})

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
