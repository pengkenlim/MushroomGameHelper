"""Scheduler module: time-based retriggering of buffs and potions.

This module is independent of screen capture and input simulation. It only
decides *which* keybinds are due; executing them is the action thread's job.
All times are ``time.perf_counter()`` values (monotonic, high resolution).
"""

import time
from pathlib import Path
from typing import Dict, List

import config
from config import BuffSchedule


class Scheduler:
    """Tracks last-trigger times and reports which buffs are due."""

    def __init__(self, path: Path = config.SCHEDULES_PATH) -> None:
        """Loads the schedules.

        Args:
            path: Location of ``schedules.json``.
        """
        self._path: Path = path
        self.schedules: List[BuffSchedule] = []
        self.last_triggered_time: Dict[str, float] = {}
        self.load()

    def load(self) -> None:
        """(Re)loads schedules from disk, keeping timestamps of known buffs."""
        self.schedules = config.load_schedules(self._path)
        names = {s.name for s in self.schedules}
        self.last_triggered_time = {
            n: t for n, t in self.last_triggered_time.items() if n in names}

    def next_due_time(self, schedule: BuffSchedule) -> float:
        """Returns when ``schedule`` is next due.

        Args:
            schedule: The schedule to inspect.

        Returns:
            ``perf_counter`` timestamp of the next press; ``0.0`` if the buff
            has never been triggered (i.e. it is due immediately).
        """
        last = self.last_triggered_time.get(schedule.name)
        return 0.0 if last is None else last + schedule.interval_seconds

    def due_schedules(self, current_time: float) -> List[BuffSchedule]:
        """Returns the enabled schedules that are due.

        Args:
            current_time: Current ``time.perf_counter()`` value.

        Returns:
            Due schedules, in configuration order.
        """
        return [s for s in self.schedules
                if s.enabled and current_time >= self.next_due_time(s)]

    def get_due_actions(self, current_time: float) -> List[str]:
        """Returns the keybinds of all buffs that are due (no side effects).

        Args:
            current_time: Current ``time.perf_counter()`` value.

        Returns:
            Keybinds to press.
        """
        return [s.keybind for s in self.due_schedules(current_time)]

    def mark_triggered(self, schedule: BuffSchedule,
                       current_time: float) -> None:
        """Records that ``schedule`` fired at ``current_time``.

        Args:
            schedule: The schedule that was triggered.
            current_time: ``time.perf_counter()`` value of the trigger.
        """
        self.last_triggered_time[schedule.name] = current_time

    def poll(self, current_time: float | None = None) -> List[str]:
        """Collects due keybinds and marks them as triggered.

        Args:
            current_time: Optional ``perf_counter`` value (defaults to now).

        Returns:
            Keybinds to forward to the action thread.
        """
        now = time.perf_counter() if current_time is None else current_time
        due = self.due_schedules(now)
        for schedule in due:
            self.mark_triggered(schedule, now)
        return [s.keybind for s in due]

    def status(self) -> List[Dict[str, object]]:
        """Describes enabled schedules for display.

        Returns:
            One dict per enabled schedule with ``name``, ``keybind``,
            ``interval_seconds`` and ``next_due`` (a ``perf_counter`` time).
        """
        return [
            {"name": s.name, "keybind": s.keybind,
             "interval_seconds": s.interval_seconds,
             "next_due": self.next_due_time(s)}
            for s in self.schedules if s.enabled
        ]
