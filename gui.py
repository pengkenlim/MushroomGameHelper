"""Tkinter GUI for controlling the automation."""

import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Dict, List

import config
from config import BuffSchedule
from main import Runner

REFRESH_MS: int = 250
CALIBRATOR_POLL_MS: int = 200
CALIBRATOR_PATH: Path = Path(__file__).resolve().parent / "calibrator.py"


class App:
    """Main window: start/stop, region/threshold settings, live status."""

    def __init__(self, root: tk.Tk, runner: Runner | None = None) -> None:
        """Builds the widgets.

        Args:
            root: The Tk root window.
            runner: Optional runner (a new one is created by default).
        """
        self.root: tk.Tk = root
        self._refresh_id: str | None = None
        self._poll_id: str | None = None
        self._closing: bool = False
        self._calibrator: subprocess.Popen[bytes] | None = None
        self.runner: Runner = runner or Runner()
        root.title("MushroomGameHelper")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.notebook = ttk.Notebook(root)
        self.notebook.grid(sticky="nsew")
        frame = ttk.Frame(self.notebook, padding=10)
        self.calibrate_tab = ttk.Frame(self.notebook, padding=10)
        self.buffs_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="Dashboard")
        self.notebook.add(self.calibrate_tab, text="Calibrate Bars")
        self.notebook.add(self.buffs_tab, text="Manage Buffs")

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

        self.title_var = tk.StringVar(value=config.WINDOW_TITLE)
        ttk.Label(frame, text="Game Window Title").grid(
            row=len(settings), column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.title_var, width=20).grid(
            row=len(settings), column=1, padx=5, pady=2)
        ttk.Label(frame, text=self.WINDOW_TITLE_HELP, wraplength=320,
                  justify=tk.LEFT).grid(
            row=len(settings) + 1, column=0, columnspan=2, sticky="w")

        self.start_btn = ttk.Button(frame, text="Start", command=self.start)
        self.stop_btn = ttk.Button(frame, text="Stop", command=self.stop,
                                   state=tk.DISABLED)
        self.start_btn.grid(row=len(settings) + 2, column=0, pady=8)
        self.stop_btn.grid(row=len(settings) + 2, column=1, pady=8)

        self.status = tk.StringVar(value="Idle")
        self.info = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.status, wraplength=320).grid(
            row=len(settings) + 3, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, textvariable=self.info, justify=tk.LEFT).grid(
            row=len(settings) + 4, column=0, columnspan=2, sticky="w")

        self._build_calibrate_tab()
        self._build_buffs_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        if not self.is_calibration_valid():
            self.start_btn.config(state=tk.DISABLED)
            self.status.set(self.SETUP_INCOMPLETE)
            self.notebook.select(self.calibrate_tab)
        self.refresh()

    WINDOW_TITLE_HELP: str = ("Leave blank to use static coordinates. Enter "
                              "exact game window title for auto-tracking.")
    SETUP_INCOMPLETE: str = ("Setup Incomplete: Please calibrate your bars in "
                             "the 'Calibrate Bars' tab before starting.")

    @staticmethod
    def is_calibration_valid() -> bool:
        """Checks whether a usable bar calibration exists.

        Valid means ``calibration.json`` exists and the Health and Mana ROIs
        have a positive width/height and are not the default placeholders.

        Returns:
            True if the bars have been calibrated.
        """
        if not config.CALIBRATION_PATH.is_file():
            return False
        placeholder = {config.BarConfig().roi,
                       config.Config().mana.roi}
        for bar in (config.HEALTH, config.MANA):
            _, _, width, height = bar.roi
            if width <= 0 or height <= 0 or tuple(bar.roi) in placeholder:
                return False
        return True

    def _build_calibrate_tab(self) -> None:
        """Builds the "Calibrate Bars" tab."""
        ttk.Button(self.calibrate_tab, text="Launch Bar Calibrator",
                   command=self.launch_calibrator).grid(
            row=0, column=0, pady=10, ipadx=20, ipady=10)
        ttk.Label(self.calibrate_tab,
                  text="Calibration saves directly to calibration.json"
                  ).grid(row=1, column=0, pady=5)

    def launch_calibrator(self) -> None:
        """Starts ``calibrator.py`` with the main window hidden.

        The subprocess is polled with ``root.after`` instead of being awaited,
        so the Tk event loop is never blocked. Current settings are saved first
        because the calibrator reads the capture region from
        ``calibration.json``. The window is always restored when the process
        ends (finished, cancelled, closed, crashed) or fails to start.
        """
        if self._calibrator is not None:
            return
        if self.runner.running:
            self.status.set("Stop the bot before calibrating.")
            return
        if not self.apply_settings():
            return
        try:
            config.save_config()
        except OSError as exc:
            self.status.set(f"Save failed: {exc}")
            return
        self.root.withdraw()
        try:
            self._calibrator = subprocess.Popen(
                [sys.executable, str(CALIBRATOR_PATH)],
                cwd=str(CALIBRATOR_PATH.parent))
        except OSError as exc:
            self.root.deiconify()
            self.status.set(f"Could not launch calibrator: {exc}")
            return
        self._poll_id = self.root.after(
            CALIBRATOR_POLL_MS, self._poll_calibrator)

    def _poll_calibrator(self) -> None:
        """Restores the window and re-checks calibration once the tool exits."""
        proc = self._calibrator
        if proc is not None and proc.poll() is None:
            self._poll_id = self.root.after(
                CALIBRATOR_POLL_MS, self._poll_calibrator)
            return
        self._calibrator = None
        self.root.deiconify()
        self.reload_calibration()

    def reload_calibration(self) -> None:
        """Reloads ``calibration.json`` and re-evaluates the first-run check."""
        loaded = config.load_config()
        # Calibration may have recorded the tracked window geometry; refresh
        # the fields so a later save() does not overwrite it with stale values.
        config.CAPTURE_TOP = loaded.capture.top
        config.CAPTURE_LEFT = loaded.capture.left
        config.CAPTURE_WIDTH = loaded.capture.width
        config.CAPTURE_HEIGHT = loaded.capture.height
        for attr in ("CAPTURE_TOP", "CAPTURE_LEFT", "CAPTURE_WIDTH",
                     "CAPTURE_HEIGHT"):
            self.fields[attr].set(str(getattr(config, attr)))
        config.HEALTH = loaded.health
        config.MANA = loaded.mana
        config.LOOTING = loaded.looting
        if self.is_calibration_valid():
            self.start_btn.config(state=tk.NORMAL)
            self.status.set("Calibration loaded. Ready.")
            self.notebook.select(0)
        else:
            self.start_btn.config(state=tk.DISABLED)
            self.status.set(self.SETUP_INCOMPLETE)

    def _build_buffs_tab(self) -> None:
        """Builds the "Manage Buffs" tab."""
        columns = ("Name", "Keybind", "Interval", "Enabled")
        self.tree = ttk.Treeview(self.buffs_tab, columns=columns,
                                 show="headings", height=8,
                                 selectmode="browse")
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=90, anchor="w")
        self.tree.grid(row=0, column=0, columnspan=3, sticky="nsew")
        ttk.Button(self.buffs_tab, text="Add",
                   command=self.add_buff_dialog).grid(row=1, column=0, pady=5)
        ttk.Button(self.buffs_tab, text="Toggle",
                   command=self.toggle_buff).grid(row=1, column=1, pady=5)
        ttk.Button(self.buffs_tab, text="Delete",
                   command=self.delete_buff).grid(row=1, column=2, pady=5)
        self.refresh_buffs()

    def on_tab_changed(self, _event: object = None) -> None:
        """Reloads the schedules when the "Manage Buffs" tab is entered."""
        if self.notebook.select() == str(self.buffs_tab):
            self.refresh_buffs()

    def refresh_buffs(self) -> None:
        """Populates the Treeview from ``config.load_schedules()``."""
        self.tree.delete(*self.tree.get_children())
        for sched in config.load_schedules():
            self.tree.insert("", tk.END, iid=sched.name, values=(
                sched.name, sched.keybind, f"{sched.interval_seconds:g}",
                "Yes" if sched.enabled else "No"))

    def _persist_buffs(self, schedules: List[BuffSchedule]) -> None:
        """Saves schedules and refreshes the table.

        Args:
            schedules: The full updated schedule list.
        """
        try:
            config.save_schedules(schedules)
        except OSError as exc:
            self.status.set(f"Save failed: {exc}")
        self.refresh_buffs()

    def _selected_name(self) -> str | None:
        """Returns the selected schedule name, or None if nothing selected."""
        selection = self.tree.selection()
        return selection[0] if selection else None

    def toggle_buff(self) -> None:
        """Flips the enabled flag of the selected schedule."""
        name = self._selected_name()
        if name is None:
            return
        schedules = config.load_schedules()
        for sched in schedules:
            if sched.name == name:
                sched.enabled = not sched.enabled
        self._persist_buffs(schedules)

    def delete_buff(self) -> None:
        """Deletes the selected schedule."""
        name = self._selected_name()
        if name is None:
            return
        self._persist_buffs(
            [s for s in config.load_schedules() if s.name != name])

    def add_buff_dialog(self) -> None:
        """Opens a dialog to add a new schedule."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Buff")
        dialog.transient(self.root)
        vars_: Dict[str, tk.StringVar] = {}
        for row, label in enumerate(("Name", "Keybind", "Interval (s)")):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w",
                                               padx=5, pady=2)
            var = tk.StringVar()
            ttk.Entry(dialog, textvariable=var, width=20).grid(
                row=row, column=1, padx=5, pady=2)
            vars_[label] = var
        error = tk.StringVar()
        ttk.Label(dialog, textvariable=error, foreground="red").grid(
            row=3, column=0, columnspan=2)

        def submit() -> None:
            """Validates the fields and stores the new schedule."""
            try:
                new = BuffSchedule(vars_["Name"].get(),
                                   vars_["Keybind"].get(),
                                   float(vars_["Interval (s)"].get()))
                schedules = config.load_schedules()
                if any(s.name == new.name for s in schedules):
                    raise ValueError("name already exists")
            except ValueError as exc:
                error.set(str(exc))
                return
            schedules.append(new)
            self._persist_buffs(schedules)
            dialog.destroy()

        ttk.Button(dialog, text="Save", command=submit).grid(
            row=4, column=0, columnspan=2, pady=5)

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
        config.WINDOW_TITLE = self.title_var.get().strip()
        return True

    def start(self) -> None:
        """Applies settings and starts the worker threads."""
        if not self.apply_settings():
            return
        if not self.is_calibration_valid():
            self.status.set(self.SETUP_INCOMPLETE)
            self.start_btn.config(state=tk.DISABLED)
            return
        try:
            self.runner.start()
        except Exception as exc:  # e.g. no display / input backend
            self.status.set(f"Could not start: {exc}")
            return
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
        """Updates the live status display and reschedules itself.

        The next tick is always scheduled (unless the window is closing), so a
        transient error cannot freeze the status panel.
        """
        try:
            snap = self.runner.state.snapshot()
            counts = {k: len(v) for k, v in snap.get("matches", {}).items()}
            self.info.set(
                f"Targets visible: {snap.get('targets_visible')}\n"
                f"Health: {snap.get('health_percent', 0.0):.0f}% "
                f"(low: {snap.get('health_low')})\n"
                f"Mana: {snap.get('mana_percent', 0.0):.0f}% "
                f"(low: {snap.get('mana_low')})\n"
                f"Matches: {counts or '-'}\n" + self.schedule_text(snap)
                + "\n" + self.looting_status_text(snap))
        except (tk.TclError, ValueError, TypeError, AttributeError) as exc:
            if not self._closing:
                self.info.set(f"Status unavailable: {exc}")
        finally:
            if not self._closing:
                self._refresh_id = self.root.after(REFRESH_MS, self.refresh)

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
        """Stops threads (releasing keys) and closes the window.

        The window is destroyed even if stopping or saving fails, and pending
        ``after`` callbacks and a running calibrator are cancelled first.
        """
        self._closing = True
        for after_id in (self._refresh_id, self._poll_id):
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
        proc = self._calibrator
        if proc is not None and proc.poll() is None:
            proc.terminate()
        try:
            self.runner.stop()
            self.save()
        finally:
            self.root.destroy()


def launch() -> None:
    """Creates the window and runs the Tk main loop."""
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    launch()
