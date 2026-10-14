"""Entry point: runs the vision, scheduler and action threads (CLI or GUI)."""

import sys
import threading
import time
from typing import Callable, List

import config
from action import Action, KeyComboListener
from logger import logger
from scheduler import Scheduler
from state import SharedState
from vision import Vision
from window_manager import get_window_bounds


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
        started = time.perf_counter()
        try:
            step()
        except Exception as exc:  # keep the loop alive
            thread_name = threading.current_thread().name
            logger.error(f"Error in {thread_name}: {exc}", exc_info=True)
        stop.wait(max(0.0, interval - (time.perf_counter() - started)))


def config_summary() -> str:
    """Builds a one-line summary of the active configuration.

    Returns:
        Human-readable summary for the startup log entry.
    """
    return (
        f"health(key={config.HEALTH.keybind}, "
        f"threshold={config.HEALTH.threshold_percent}, "
        f"cooldown={config.HEALTH.cooldown}) "
        f"mana(key={config.MANA.keybind}, "
        f"threshold={config.MANA.threshold_percent}, "
        f"cooldown={config.MANA.cooldown}) "
        f"looting(key={config.LOOTING.keybind}, "
        f"toggle={config.LOOTING.toggle_key_1}+{config.LOOTING.toggle_key_2}) "
        f"intervals(vision={config.VISION_INTERVAL}, "
        f"action={config.ACTION_INTERVAL}, "
        f"scheduler={config.SCHEDULER_INTERVAL})")


class Runner:
    """Owns the shared state and the vision/scheduler/action threads."""

    def __init__(self) -> None:
        """Creates the shared state; threads are created on ``start``."""
        self.state: SharedState = SharedState(
            {"matches": {}, "targets_visible": False, "health_low": False}
        )
        self._stop: threading.Event = threading.Event()
        self._threads: List[threading.Thread] = []
        self._vision: Vision | None = None
        self._action: Action | None = None
        self._scheduler: Scheduler | None = None
        self._combo_listener: KeyComboListener | None = None

    @property
    def running(self) -> bool:
        """Whether the worker threads are active."""
        return bool(self._threads)

    def start(self) -> None:
        """Starts the vision, scheduler and action threads (no-op if running)."""
        logger.debug("Runner.start() called")
        if self.running:
            return
        logger.info(f"Bot session starting. Config: {config_summary()}")
        if config.CAPTURE_WINDOW_TITLE:
            bounds = get_window_bounds(config.CAPTURE_WINDOW_TITLE)
            if bounds is None:
                logger.warning(
                    f"Window '{config.CAPTURE_WINDOW_TITLE}' not found; "
                    "falling back to static capture coordinates")
            else:
                logger.info(
                    f"Window '{config.CAPTURE_WINDOW_TITLE}' found: {bounds}")
        stop_event = self._stop = threading.Event()
        vision = self._vision = Vision()
        action = self._action = Action()
        scheduler = self._scheduler = Scheduler()
        state = self.state
        state.clear_buff_presses()
        state.set("looting_active", False)
        listener = self._combo_listener = KeyComboListener(state)
        listener.start()

        def vision_step() -> None:
            state.update(vision.process())

        def vision_worker() -> None:
            # mss handles are thread-local: create and close them on this thread.
            try:
                run_loop(vision_step, config.VISION_INTERVAL, stop_event)
            finally:
                vision.close()

        def action_step() -> None:
            action.run_cycle(state)

        def scheduler_step() -> None:
            # Never presses keys: only queues them for the action thread.
            for keybind in scheduler.poll():
                state.append_buff_press(keybind)
            state.set("schedule_status", scheduler.status())

        self._threads = [
            threading.Thread(target=vision_worker, name="vision", daemon=True),
            threading.Thread(
                target=run_loop, name="action", daemon=True,
                args=(action_step, config.ACTION_INTERVAL, self._stop)),
            threading.Thread(
                target=run_loop, name="scheduler", daemon=True,
                args=(scheduler_step, config.SCHEDULER_INTERVAL, self._stop)),
        ]
        try:
            for thread in self._threads:
                thread.start()
        except BaseException:
            self.stop()  # never leave the listener or started threads behind
            raise

    def stop(self) -> None:
        """Stops the threads and listener and releases held keys.

        The vision thread closes its own ``mss`` handle when its loop ends.
        """
        if not self.running:
            return
        self._stop.set()
        try:
            if self._combo_listener is not None:
                self._combo_listener.stop()
                self._combo_listener = None
            for thread in self._threads:
                if thread.ident is None or thread is threading.current_thread():
                    continue  # never started / called from itself
                thread.join(timeout=2.0)
                if thread.is_alive():
                    logger.warning(f"Thread '{thread.name}' did not stop in time")
        finally:
            self._threads = []
            self.state.set("looting_active", False)
            if self._action is not None:
                self._action.release_all()
        logger.info("Bot session stopped gracefully")


def main() -> None:
    """Runs headless, or launches the GUI (``--gui``) or overlay (``--osd``)."""
    logger.info("MushroomHelper main() invoked")
    if "--gui" in sys.argv[1:]:
        from gui import launch
        launch()
        return
    runner = Runner()
    if "--osd" in sys.argv[1:]:
        from osd import launch_osd
        runner.start()
        try:
            launch_osd(runner.state)
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            runner.stop()
        return
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
