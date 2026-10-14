# DEPRECATED: Buff management is now integrated into gui.py. This CLI script is retained for backward compatibility.
"""Interactive CLI for defining buff/potion schedules (``schedules.json``)."""

from typing import List

import config
from config import BuffSchedule


def _ask(prompt: str, default: str | None = None) -> str:
    """Prompts for a line of input.

    Args:
        prompt: Text shown to the user.
        default: Value returned when the user enters nothing.

    Returns:
        The stripped input, or ``default`` if empty and a default is given.
    """
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value or default is None else default


def _ask_schedule(existing: BuffSchedule | None,
                  others: List[BuffSchedule]) -> BuffSchedule | None:
    """Prompts for the fields of a schedule until valid.

    Args:
        existing: Schedule being edited (provides defaults), or None.
        others: Other schedules, used to reject duplicate names.

    Returns:
        The new schedule, or None if the user cancelled with an empty name.
    """
    taken = {s.name for s in others}
    while True:
        name = _ask("Name (e.g. Attack Buff)",
                    existing.name if existing else None)
        if not name:
            return None
        if name in taken:
            print("A schedule with that name already exists.")
            continue
        break
    while True:
        try:
            keybind = _ask("Keybind (e.g. F1, 3)",
                           existing.keybind if existing else None)
            interval = float(_ask(
                "Retrigger interval in seconds (e.g. 30.0)",
                f"{existing.interval_seconds:g}" if existing else None))
            enabled = (existing.enabled if existing else True)
            return BuffSchedule(name, keybind, interval, enabled)
        except ValueError as exc:
            print(f"Invalid input: {exc}")


def _list(schedules: List[BuffSchedule]) -> None:
    """Prints all schedules.

    Args:
        schedules: Schedules to display.
    """
    if not schedules:
        print("No schedules defined.")
        return
    for i, s in enumerate(schedules, 1):
        state = "on " if s.enabled else "off"
        print(f"{i:2}. [{state}] {s.name}: key={s.keybind} "
              f"every {s.interval_seconds:g}s")


def _pick(schedules: List[BuffSchedule]) -> int | None:
    """Asks the user to choose a schedule by its list number.

    Args:
        schedules: Available schedules.

    Returns:
        Zero-based index, or None if invalid/no schedules.
    """
    if not schedules:
        print("No schedules defined.")
        return None
    _list(schedules)
    try:
        index = int(_ask("Number")) - 1
    except ValueError:
        index = -1
    if 0 <= index < len(schedules):
        return index
    print("Invalid selection.")
    return None


def main() -> None:
    """Runs the menu loop, saving after every change."""
    schedules = config.load_schedules()
    menu = ("\n[l]ist  [a]dd  [e]dit  [t]oggle enabled  [d]elete  [q]uit")
    while True:
        print(menu)
        try:
            choice = _ask("Choice").lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice in ("q", "quit"):
            return
        if choice in ("l", "list"):
            _list(schedules)
        elif choice in ("a", "add"):
            new = _ask_schedule(None, schedules)
            if new:
                schedules.append(new)
                config.save_schedules(schedules)
                print(f"Added '{new.name}'.")
        elif choice in ("e", "edit", "t", "toggle", "d", "delete"):
            index = _pick(schedules)
            if index is None:
                continue
            if choice in ("e", "edit"):
                others = schedules[:index] + schedules[index + 1:]
                updated = _ask_schedule(schedules[index], others)
                if updated:
                    schedules[index] = updated
                    print(f"Updated '{updated.name}'.")
            elif choice in ("t", "toggle"):
                schedules[index].enabled = not schedules[index].enabled
                print(f"'{schedules[index].name}' enabled="
                      f"{schedules[index].enabled}.")
            else:
                print(f"Deleted '{schedules.pop(index).name}'.")
            config.save_schedules(schedules)
        else:
            print("Unknown choice.")


if __name__ == "__main__":
    main()
