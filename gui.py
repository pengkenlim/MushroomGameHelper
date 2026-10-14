"""Tkinter GUI for controlling the automation."""

import time
import tkinter as tk
from tkinter import ttk
from typing import Dict, List

import config
from main import Runner

REFRESH_MS: int = 250


class App:
    """Main window: start/stop, region/threshold settings, live status."""

    def __init__(self, root: tk.Tk, runner: Runner | None = None) -> None:
        """Builds the widgets.

        Args:
            root: The Tk root window.
            runner: Optional runner (a new one is created by default).
        """
        self.root: tk.Tk = root
        self.runner: Runner = runner or Runner()
        root.title("MushroomGameHelper")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        frame = ttk.Frame(root, padding=10)
        frame.grid(sticky="nsew")

        self.fields: Dict[str, tk.StringVar] = {}
        settings = [
            ("Top", "CAPTURE_TOP"), ("Left", "CAPTURE_LEFT"),
            ("Width", "CAPTURE_WIDTH"), ("Height", "CAPTURE_HEIGHT"),
            ("Match threshold", "MATCH_THRESHOLD"),
        ]
        for row, (label, attr) in enumerate(settings):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=str(getattr(config, attr)))
            ttk.Entry(frame, textvariable=var, width=10).grid(
                row=row, column=1, padx=5, pady=2)
            self.fields[attr] = var

        self.title_var = tk.StringVar(value=config.CAPTURE_WINDOW_TITLE)
        ttk.Label(frame, text="Window Title").grid(
            row=len(settings), column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.title_var, width=20).grid(
            row=len(settings), column=1, padx=5, pady=2)

        self.start_btn = ttk.Button(frame, text="Start", command=self.start)
        self.stop_btn = ttk.Button(frame, text="Stop", command=self.stop,
                                   state=tk.DISABLED)
        self.start_btn.grid(row=len(settings) + 1, column=0, pady=8)
        self.stop_btn.grid(row=len(settings) + 1, column=1, pady=8)

        self.status = tk.StringVar(value="Idle")
        self.info = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.status).grid(
            row=len(settings) + 2, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, textvariable=self.info, justify=tk.LEFT).grid(
            row=len(settings) + 3, column=0, columnspan=2, sticky="w")
        self.refresh()

    def apply_settings(self) -> bool:
        """Validates the entries and writes them into ``config``.

        Returns:
            True if all values were valid and applied.
        """
        parsed: Dict[str, float] = {}
        try:
            for attr, var in self.fields.items():
                value = float(var.get())
                if attr == "MATCH_THRESHOLD":
                    if not 0.0 <= value <= 1.0:
                        raise ValueError("threshold must be 0-1")
                else:
                    if value < 0 or (attr.endswith(("WIDTH", "HEIGHT"))
                                     and value < 1):
                        raise ValueError(f"invalid {attr}")
                    value = int(value)
                parsed[attr] = value
        except ValueError as exc:
            self.status.set(f"Invalid settings: {exc}")
            return False
        for attr, value in parsed.items():
            setattr(config, attr, value)
        config.CAPTURE_WINDOW_TITLE = self.title_var.get().strip()
        return True

    def start(self) -> None:
        """Applies settings and starts the worker threads."""
        if not self.apply_settings():
            return
        self.runner.start()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status.set("Running")

    def stop(self) -> None:
        """Stops the worker threads."""
        self.runner.stop()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status.set("Stopped (settings saved)")
        self.save()

    def save(self) -> None:
        """Persists the current settings to ``calibration.json``."""
        if self.apply_settings():
            try:
                config.save_config()
            except OSError as exc:
                self.status.set(f"Save failed: {exc}")

    def refresh(self) -> None:
        """Updates the live status display and reschedules itself."""
        snap = self.runner.state.snapshot()
        counts = {k: len(v) for k, v in snap.get("matches", {}).items()}
        self.info.set(
            f"Targets visible: {snap.get('targets_visible')}\n"
            f"Health: {snap.get('health_percent', 0.0):.0f}% "
            f"(low: {snap.get('health_low')})\n"
            f"Mana: {snap.get('mana_percent', 0.0):.0f}% "
            f"(low: {snap.get('mana_low')})\n"
            f"Matches: {counts or '-'}"
        )
        self.info.set(self.info.get() + "\n" + self.schedule_text(snap)
                      + "\n" + self.looting_status_text(snap))
        self.root.after(REFRESH_MS, self.refresh)

    @staticmethod
    def schedule_text(snap: Dict[str, object]) -> str:
        """Formats the active buff schedules with next-press countdowns.

        Args:
            snap: Shared-state snapshot containing ``schedule_status``.

        Returns:
            Multi-line text for the status panel.
        """
        status: List[Dict[str, object]] = snap.get(
            "schedule_status") or []  # type: ignore[assignment]
        if not status:
            return "Buffs: -"
        now = time.perf_counter()
        lines = ["Buffs:"]
        for item in status:
            remaining = max(0.0, float(item["next_due"]) - now)  # type: ignore[arg-type]
            lines.append(
                f"  {item['name']} [{item['keybind']}] "
                f"every {float(item['interval_seconds']):g}s "  # type: ignore[arg-type]
                f"- next in {remaining:.1f}s")
        return "\n".join(lines)

    @staticmethod
    def looting_status_text(snap: Dict[str, object]) -> str:
        """Formats the looting hold-and-retrigger status.

        Args:
            snap: Shared-state snapshot containing ``looting_active``.

        Returns:
            ``"Looting: ACTIVE"`` or an "Inactive" hint naming the toggle chord.
        """
        if snap.get("looting_active"):
            return "Looting: ACTIVE"
        return (f"Looting: Inactive (Press {config.LOOTING.toggle_key_1}"
                f"+{config.LOOTING.toggle_key_2} to toggle)")

    def on_close(self) -> None:
        """Stops threads (releasing keys) and closes the window."""
        self.runner.stop()
        self.save()
        self.root.destroy()


def launch() -> None:
    """Creates the window and runs the Tk main loop."""
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    launch()
