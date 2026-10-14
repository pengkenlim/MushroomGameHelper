"""Entry point: runs the vision and action threads (CLI or GUI)."""

import sys
import threading
import time
from typing import Callable, List

import config
from action import Action
from state import SharedState
from vision import Vision


def run_loop(
    step: Callable[[], None], interval: float, stop: threading.Event
) -> None:
    """Runs ``step`` repeatedly at a fixed interval until ``stop`` is set.

    Args:
        step: Callable executed each tick.
        interval: Target seconds between tick starts.
        stop: Event signalling shutdown.
    """
    while not stop.is_set():
        started = time.monotonic()
        try:
            step()
        except Exception as exc:  # keep the loop alive
            print(f"[error] {exc!r}")
        stop.wait(max(0.0, interval - (time.monotonic() - started)))


class Runner:
    """Owns the shared state and the vision/action threads."""

    def __init__(self) -> None:
        """Creates the shared state; threads are created on ``start``."""
        self.state: SharedState = SharedState(
            {"matches": {}, "targets_visible": False, "health_low": False}
        )
        self._stop: threading.Event = threading.Event()
        self._threads: List[threading.Thread] = []
        self._vision: Vision | None = None
        self._action: Action | None = None

    @property
    def running(self) -> bool:
        """Whether the worker threads are active."""
        return bool(self._threads)

    def start(self) -> None:
        """Starts the vision and action threads (no-op if running)."""
        if self.running:
            return
        self._stop = threading.Event()
        vision = self._vision = Vision()
        action = self._action = Action()
        state = self.state

        def vision_step() -> None:
            state.update(vision.process())

        def action_step() -> None:
            action.decide(state.snapshot())

        self._threads = [
            threading.Thread(
                target=run_loop, name="vision", daemon=True,
                args=(vision_step, config.VISION_INTERVAL, self._stop)),
            threading.Thread(
                target=run_loop, name="action", daemon=True,
                args=(action_step, config.ACTION_INTERVAL, self._stop)),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        """Stops the threads, releases held keys and capture handles."""
        if not self.running:
            return
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads = []
        if self._action is not None:
            self._action.release_all()
        if self._vision is not None:
            self._vision.close()


def main() -> None:
    """Runs headless, or launches the GUI with ``--gui``."""
    if "--gui" in sys.argv[1:]:
        from gui import launch
        launch()
        return
    runner = Runner()
    runner.start()
    print("Running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        runner.stop()


if __name__ == "__main__":
    main()
