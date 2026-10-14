"""Entry point: runs the vision and action threads."""

import threading
import time
from typing import Callable

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


def main() -> None:
    """Starts both threads and shuts down cleanly on Ctrl+C."""
    state = SharedState({"matches": {}, "targets_visible": False,
                         "health_low": False})
    vision = Vision()
    action = Action()
    stop = threading.Event()

    def vision_step() -> None:
        state.update(vision.process())

    def action_step() -> None:
        action.decide(state.snapshot())

    threads = [
        threading.Thread(target=run_loop, name="vision", daemon=True,
                         args=(vision_step, config.VISION_INTERVAL, stop)),
        threading.Thread(target=run_loop, name="action", daemon=True,
                         args=(action_step, config.ACTION_INTERVAL, stop)),
    ]
    for thread in threads:
        thread.start()
    print("Running. Press Ctrl+C to stop.")
    try:
        while not stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=2.0)
        action.release_all()
        vision.close()


if __name__ == "__main__":
    main()
