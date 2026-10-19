"""Tkinter GUI for controlling the automation."""

import math
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from functools import partial
from pathlib import Path
from tkinter import font as tkfont, messagebox, ttk
from typing import Dict, List, Optional, Tuple

import config
from config import BuffSchedule
from logger import logger
from main import Runner

try:
    import pygetwindow as gw
except Exception:  # pragma: no cover - platform-dependent dependency
    gw = None

REFRESH_MS: int = 250
CALIBRATOR_POLL_MS: int = 200
CAPTURE_TIMEOUT_S: float = 30.0
CALIBRATOR_PATH: Path = Path(__file__).resolve().parent / "calibrator.py"
ERROR_TITLE: str = "Configuration Error"
DASHBOARD_PADDING: int = 10
DASHBOARD_SPAN: int = 4
GROUP_PADX: int = 10
GROUP_PADY: int = 5
PAIR_GAP: int = 15
STATUS_MIN_WRAP: int = 200
STATUS_WRAP: int = 520

# Capture-region entries: (``config`` attribute, label, minimum value).
REGION_FIELDS: Tuple[Tuple[str, str, int], ...] = (
    ("CAPTURE_TOP", "Top", 0),
    ("CAPTURE_LEFT", "Left", 0),
    ("CAPTURE_WIDTH", "Width", 1),
    ("CAPTURE_HEIGHT", "Height", 1),
)

TOOLTIPS: Dict[str, str] = {
    "window": ("Pick the game window to track. The capture region then "
               "follows it when it moves or is resized."),
    "advanced": ("Show the manual capture coordinates. They are used when no "
                 "game window is selected or the window can't be found."),
    "CAPTURE_TOP": ("Distance in pixels from the top of the screen to the "
                    "capture region."),
    "CAPTURE_LEFT": ("Distance in pixels from the left of the screen to the "
                     "capture region."),
    "CAPTURE_WIDTH": "Width of the capture region in pixels (at least 1).",
    "CAPTURE_HEIGHT": "Height of the capture region in pixels (at least 1).",
    "MATCH_THRESHOLD": ("Confidence required for template matching (0.0 to "
                        "1.0). Higher values reduce false positives."),
    "hp_threshold": ("Health counts as low below this percentage (0-100). "
                     "The HP key is pressed while it is low."),
    "hp_keybind": ("Key pressed to heal. Type a key name or use Capture to "
                   "record a key or mouse button."),
    "hp_cooldown": "Minimum seconds between automated heal presses.",
    "mp_threshold": ("Mana counts as low below this percentage (0-100). "
                     "The MP key is pressed while it is low."),
    "mp_keybind": ("Key pressed to restore mana. Type a key name or use "
                   "Capture to record a key or mouse button."),
    "mp_cooldown": "Minimum seconds between automated mana presses.",
    "repot_toggle": ("Toggle Keys to switch Re-poting ON/OFF. Capture the same key in both boxes for a single-key toggle."),
    "rebuff_toggle": ("Toggle Keys to switch Re-buffing ON/OFF. Capture the same key in both boxes for a single-key toggle."),
    "looting_toggle": ("Toggle Keys to switch Autolooting ON/OFF. Capture the same key in both boxes for a single-key toggle."),
    "start_stop_toggle": ("Toggle Keys to Start or Stop the bot globally. Useful for emergency stops or pausing to type in chat."),
    "looting_keybind": ("Key held down while Autolooting is ON. Leave empty "
                        "to disable looting."),
    "capture": ("Click, then press any key or mouse button to fill the "
                "field. Media keys and the left, right and middle mouse "
                "buttons are supported."),
    "start": ("Apply the settings and start the bot. Disabled until the "
              "health and mana bars are calibrated."),
    "stop": "Stop the bot, release held keys and save the settings.",
}


class ToolTip:
    """Small hover tip for any Tk widget.

    A borderless ``Toplevel`` is created when the pointer enters the widget
    and destroyed again when it leaves. The tip is also removed when the
    widget is clicked, unmapped or destroyed, so no window outlives the hover
    and at most one exists per widget.

    Attributes:
        widget: The widget the tip describes.
        text: The text shown in the tip.
    """

    BACKGROUND: str = "#ffffe0"
    FOREGROUND: str = "#000000"
    WRAP_LENGTH: int = 280
    OFFSET_X: int = 12
    OFFSET_Y: int = 4

    def __init__(self, widget: tk.Misc, text: str) -> None:
        """Binds the hover events.

        Args:
            widget: The widget to describe.
            text: The tip text.
        """
        self.widget: tk.Misc = widget
        self.text: str = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show, add="+")
        for sequence in ("<Leave>", "<ButtonPress>", "<Unmap>", "<Destroy>"):
            widget.bind(sequence, self.hide, add="+")

    def show(self, _event: object = None) -> None:
        """Shows the tip below the widget (does nothing if already shown).

        Args:
            _event: The Tk event that triggered the call (unused).
        """
        if self._tip is not None or not self.text:
            return
        tip = tk.Toplevel(self.widget)
        try:
            tip.withdraw()
            tip.wm_overrideredirect(True)
            if tip.tk.call("tk", "windowingsystem") == "aqua":
                tip.tk.call("::tk::unsupported::MacWindowStyle", "style",
                            str(tip), "help", "noActivates")
            tk.Label(tip, text=self.text, justify=tk.LEFT,
                     background=self.BACKGROUND, foreground=self.FOREGROUND,
                     relief=tk.SOLID, borderwidth=1,
                     wraplength=self.WRAP_LENGTH, padx=6, pady=3).pack()
            tip.update_idletasks()
            x, y = self._position(tip.winfo_reqwidth(), tip.winfo_reqheight())
            tip.wm_geometry(f"+{x}+{y}")
            tip.deiconify()
        except tk.TclError:
            tip.destroy()
            return
        self._tip = tip

    def hide(self, _event: object = None) -> None:
        """Destroys the tip window, if there is one.

        Args:
            _event: The Tk event that triggered the call (unused).
        """
        tip, self._tip = self._tip, None
        if tip is None:
            return
        try:
            tip.destroy()
        except tk.TclError:  # already gone together with its parent
            pass

    def _position(self, width: int, height: int) -> Tuple[int, int]:
        """Picks the screen position of a tip of the given size.

        The tip goes just below the widget and moves above it (or to the
        left) when it would otherwise leave the screen.

        Args:
            width: Requested tip width in pixels.
            height: Requested tip height in pixels.

        Returns:
            The ``(x, y)`` screen coordinates of the tip's top-left corner.
        """
        widget = self.widget
        x = widget.winfo_rootx() + self.OFFSET_X
        y = widget.winfo_rooty() + widget.winfo_height() + self.OFFSET_Y
        if y + height > widget.winfo_screenheight():
            y = widget.winfo_rooty() - height - self.OFFSET_Y
        x = min(x, widget.winfo_screenwidth() - width)
        return max(0, x), max(0, y)


class App:
    """Main window: start/stop, region/threshold settings, live status."""

    PREFERRED_THEMES: Tuple[str, ...] = ("clam", "alt")
    # Themes whose buttons honour custom background colours.
    COLORABLE_THEMES: Tuple[str, ...] = ("clam", "alt", "default", "classic")
    # Style name -> (normal, hover, pressed) button background.
    BUTTON_COLORS: Dict[str, Tuple[str, str, str]] = {
        "Start.TButton": ("#2e7d32", "#388e3c", "#1b5e20"),
        "Stop.TButton": ("#c62828", "#d32f2f", "#8e0000"),
    }
    BUTTON_DISABLED_BG: str = "#c9c9c9"
    BUTTON_DISABLED_FG: str = "#7a7a7a"
    STATUS_COLORS: Dict[str, str] = {
        "running": "#116329",
        "error": "#a40e26",
        "idle": "#57606a",
    }
    ERROR_PREFIXES: Tuple[str, ...] = (
        "Invalid", "Could not", "Save failed", "Setup Incomplete",
        "Stop the bot", "Status unavailable", "Key capture failed")

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
        self._osd = None
        self._osd_root = None
        self.runner: Runner = runner or Runner()
        self.tooltips: List[ToolTip] = []
        self._bold_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        root.title("MushroomGameHelper")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self._configure_styles()

        self.notebook = ttk.Notebook(root)
        self.notebook.grid(sticky="nsew")
        frame = self.dashboard_tab = ttk.Frame(
            self.notebook, padding=DASHBOARD_PADDING)
        self.calibrate_tab = ttk.Frame(self.notebook, padding=10)
        self.buffs_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="Dashboard")
        self.notebook.add(self.calibrate_tab, text="Calibrate Bars")
        self.notebook.add(self.buffs_tab, text="Manage Buffs")

        self.fields: Dict[str, tk.StringVar] = {}
        self.manual_fields: List[ttk.Entry] = []
        self.manual_labels: List[ttk.Label] = []

        # Columns 0 and 3 are spacers that keep the Start/Stop pair centred.
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(DASHBOARD_SPAN - 1, weight=1)
        self._build_window_group(frame, row=0)
        self._build_resource_group(frame, row=1)
        self._build_action_group(frame, row=2)
        self._align_groups()
        self._build_controls(frame, row=3)

        self._build_calibrate_tab()
        self._build_buffs_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        if not self.is_calibration_valid():
            self.start_btn.config(state=tk.DISABLED)
            self.status.set(self.SETUP_INCOMPLETE)
            self.notebook.select(self.calibrate_tab)
        self.refresh()

    def _configure_styles(self) -> None:
        """Applies a custom theme using semantic color variables."""
        self.style: ttk.Style = ttk.Style(self.root)
        
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
            
        # Semantic Color Palette
        BG_PRIMARY = "#FDFBF7"       # Main window background
        BG_SECONDARY = "#EBF5EB"     # Group frames, tabs, and containers
        TEXT_PRIMARY = "#4A3F35"     # Standard body text
        TEXT_ACCENT = "#D35400"      # Group headers and highlights
        BTN_SUCCESS_BG = "#27AE60"   # Start/Primary action button
        BTN_SUCCESS_HOVER = "#2ECC71"# Start button hover state
        BTN_DANGER_BG = "#C0392B"    # Stop/Destructive action button
        BTN_DANGER_HOVER = "#E74C3C" # Stop button hover state
        BTN_DISABLED_BG = "#BDC3C7"  # Disabled button state
        
        # Global Backgrounds and Fonts
        self.style.configure("TFrame", background=BG_PRIMARY)
        self.style.configure("TNotebook", background=BG_PRIMARY, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=BG_SECONDARY, foreground=TEXT_PRIMARY, padding=[10, 5], font=("Segoe UI", 10, "bold"))
        self.style.map("TNotebook.Tab", background=[("selected", BG_PRIMARY)])
        
        self.style.configure("TLabel", background=BG_PRIMARY, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        self.style.configure("TLabelFrame", background=BG_SECONDARY, foreground=TEXT_PRIMARY, font=("Segoe UI", 9, "bold"), borderwidth=2)
        self.style.configure("TLabelFrame.Label", background=BG_SECONDARY, foreground=TEXT_ACCENT, font=("Segoe UI", 10, "bold"))
        
        self.style.configure("TCheckbutton", background=BG_SECONDARY, foreground=TEXT_PRIMARY)
        self.style.configure("TButton", background=BG_PRIMARY, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        
        # Custom Button Styles
        self.style.configure("Start.TButton", background=BTN_SUCCESS_BG, foreground="white", font=("Segoe UI", 11, "bold"))
        self.style.map("Start.TButton", background=[("active", BTN_SUCCESS_HOVER), ("disabled", BTN_DISABLED_BG)])
        
        self.style.configure("Stop.TButton", background=BTN_DANGER_BG, foreground="white", font=("Segoe UI", 11, "bold"))
        self.style.map("Stop.TButton", background=[("active", BTN_DANGER_HOVER), ("disabled", BTN_DISABLED_BG)])

    def _add_tip(self, key: str, *widgets: tk.Misc) -> None:
        """Attaches the tip registered under ``key`` to each widget.

        Args:
            key: Key into ``TOOLTIPS``.
            *widgets: The widgets that show the tip on hover.
        """
        for widget in widgets:
            self.tooltips.append(ToolTip(widget, TOOLTIPS[key]))

    def _new_group(self, parent: ttk.Frame, title: str, row: int
                   ) -> ttk.LabelFrame:
        """Creates a titled settings group in the dashboard.

        Every group shares the same padding and the same
        ``label | entry | Capture`` column pairs, so the groups line up.

        Args:
            parent: The dashboard frame.
            title: The group title.
            row: Grid row inside ``parent``.

        Returns:
            The new LabelFrame.
        """
        group = ttk.LabelFrame(parent, text=title, padding=(10, 5))
        group.grid(row=row, column=0, columnspan=DASHBOARD_SPAN, sticky="ew",
                   padx=GROUP_PADX, pady=GROUP_PADY)
        for column in (1, 4):
            group.columnconfigure(column, weight=1)
        return group

    def _align_groups(self) -> None:
        """Gives the settings groups identical caption/button column widths.

        The groups are separate containers, so their grids are independent;
        copying the widest natural width of each fixed column to every group
        makes the entries and Capture buttons line up from group to group.
        """
        groups = (self.window_group, self.resource_group, self.action_group)
        self.root.update_idletasks()
        for column in (0, 2, 3, 5):
            boxes = (group.grid_bbox(column, 0) for group in groups)
            width = max((box[2] for box in boxes if box), default=0)
            for group in groups:
                group.columnconfigure(column, minsize=width)

    def _add_field(self, group: ttk.LabelFrame, label: str,
                   variable: tk.StringVar, row: int, column: int, tip: str,
                   capture: bool = False) -> Tuple[ttk.Label, ttk.Entry]:
        """Adds a ``label | entry [| Capture]`` row segment to a group.

        Args:
            group: The LabelFrame that owns the widgets.
            label: Caption text.
            variable: Variable edited by the entry.
            row: Grid row.
            column: Grid column of the caption; the entry goes in the next
                column and the optional Capture button in the one after.
            tip: Key into ``TOOLTIPS`` for the caption, entry and button.
            capture: Whether to add a "Capture" button next to the entry.

        Returns:
            The caption label and the entry.
        """
        lead = PAIR_GAP if column else 0
        caption = ttk.Label(group, text=label)
        caption.grid(row=row, column=column, sticky="w", padx=(lead, 5),
                     pady=2)
        entry = ttk.Entry(group, textvariable=variable, width=12, state="readonly" if capture else "normal")
        entry.grid(row=row, column=column + 1, sticky="ew", padx=(0, 5),
                   pady=2)
        self._add_tip(tip, caption, entry)
        if capture:
            button = ttk.Button(group, text="Capture", width=8,
                                command=partial(self.do_capture, variable))
            button.grid(row=row, column=column + 2, padx=(0, 5), pady=2)
            self._add_tip("capture", button)
        return caption, entry

    @staticmethod
    def list_window_titles() -> List[str]:
        """Lists the titles of the open windows.

        Returns:
            The non-empty window titles, or an empty list when
            ``pygetwindow`` is not available on this platform.

        Raises:
            Exception: Whatever ``pygetwindow`` raises while enumerating.
        """
        if gw is None:
            return []
        return [w.title for w in gw.getAllWindows()
                if getattr(w, "title", "").strip()]

    def _build_window_group(self, parent: ttk.Frame, row: int) -> None:
        """Builds the "Game Window Targeting" group.

        Args:
            parent: The dashboard frame.
            row: Grid row of the group inside ``parent``.
        """
        group = self.window_group = self._new_group(
            parent, "Game Window Targeting", row)
        self.window_title_var = tk.StringVar(value=config.WINDOW_TITLE)
        try:
            window_titles = self.list_window_titles()
        except Exception as exc:  # the manual fields remain usable
            logger.warning(f"Could not list open windows: {exc}")
            window_titles = []
        # Without a usable window list the manual coordinates are the only way
        # to choose the capture region, so show them right away.
        self.advanced_toggle_var = tk.BooleanVar(value=not window_titles)

        caption = ttk.Label(group, text="Game Window")
        caption.grid(row=0, column=0, sticky="w", padx=(0, 5), pady=2)
        self.window_dropdown = ttk.Combobox(
            group, textvariable=self.window_title_var, values=window_titles,
            state="readonly" if window_titles else "disabled", width=24)
        self.window_dropdown.grid(row=0, column=1, columnspan=5, sticky="ew",
                                  pady=2)
        self.window_dropdown.bind("<<ComboboxSelected>>",
                                  self.on_window_select)
        self._add_tip("window", caption, self.window_dropdown)

        self.advanced_toggle = ttk.Checkbutton(
            group, text="Show Advanced (Manual Coordinates)",
            variable=self.advanced_toggle_var,
            command=self.toggle_manual_fields)
        self.advanced_toggle.grid(row=1, column=0, columnspan=6, sticky="w",
                                  pady=(4, 2))
        self._add_tip("advanced", self.advanced_toggle)

        for index, (attr, label, _minimum) in enumerate(REGION_FIELDS):
            var = tk.StringVar(value=str(getattr(config, attr)))
            caption, entry = self._add_field(
                group, label, var, row=2 + index // 2, column=3 * (index % 2),
                tip=attr)
            self.fields[attr] = var
            self.manual_labels.append(caption)
            self.manual_fields.append(entry)
        self.toggle_manual_fields()

    def _build_resource_group(self, parent: ttk.Frame, row: int) -> None:
        """Builds the "Resource Monitoring" group.

        Args:
            parent: The dashboard frame.
            row: Grid row of the group inside ``parent``.
        """
        group = self.resource_group = self._new_group(
            parent, "Resource Monitoring", row)
        threshold = tk.StringVar(value=str(config.MATCH_THRESHOLD))
        self.fields["MATCH_THRESHOLD"] = threshold
        self._add_field(group, "Match threshold", threshold, 0, 0,
                        "MATCH_THRESHOLD")

        self.hp_threshold_var = tk.StringVar(
            value=str(config.HEALTH.threshold_percent))
        self.hp_keybind_var = tk.StringVar(value=config.HEALTH.keybind)
        self.hp_cooldown_var = tk.StringVar(value=str(config.HEALTH.cooldown))
        self.mp_threshold_var = tk.StringVar(
            value=str(config.MANA.threshold_percent))
        self.mp_keybind_var = tk.StringVar(value=config.MANA.keybind)
        self.mp_cooldown_var = tk.StringVar(value=str(config.MANA.cooldown))
        self._add_field(group, "HP Threshold %", self.hp_threshold_var, 1, 0,
                        "hp_threshold")
        self._add_field(group, "MP Threshold %", self.mp_threshold_var, 1, 3,
                        "mp_threshold")
        self._add_field(group, "HP Keybind", self.hp_keybind_var, 2, 0,
                        "hp_keybind", capture=True)
        self._add_field(group, "MP Keybind", self.mp_keybind_var, 2, 3,
                        "mp_keybind", capture=True)
        self._add_field(group, "HP Cooldown", self.hp_cooldown_var, 3, 0,
                        "hp_cooldown")
        self._add_field(group, "MP Cooldown", self.mp_cooldown_var, 3, 3,
                        "mp_cooldown")

    def _build_action_group(self, parent: ttk.Frame, row: int) -> None:
        """Builds the Action Toggles & Keybinds group."""
        group = self.action_group = self._new_group(
            parent, "Action Toggles & Keybinds", row)
            
        self.repot_toggle_1_var = tk.StringVar(value=config.REPOT_TOGGLE_1)
        self.repot_toggle_2_var = tk.StringVar(value=config.REPOT_TOGGLE_2)
        self.rebuff_toggle_1_var = tk.StringVar(value=config.REBUFF_TOGGLE_1)
        self.rebuff_toggle_2_var = tk.StringVar(value=config.REBUFF_TOGGLE_2)
        self.looting_toggle_1_var = tk.StringVar(value=config.LOOTING_TOGGLE_1)
        self.looting_toggle_2_var = tk.StringVar(value=config.LOOTING_TOGGLE_2)
        self.start_stop_toggle_1_var = tk.StringVar(value=config.START_STOP_TOGGLE_1)
        self.start_stop_toggle_2_var = tk.StringVar(value=config.START_STOP_TOGGLE_2)
        self.looting_keybind_var = tk.StringVar(value=config.LOOTING_KEYBIND)
        
        self.repot_result_var = tk.StringVar()
        self.rebuff_result_var = tk.StringVar()
        self.looting_toggle_result_var = tk.StringVar()
        self.start_stop_result_var = tk.StringVar()
        
        # Looting Keybind (Single entry)
        self._add_field(group, "Looting Keybind", self.looting_keybind_var, 0, 0, "looting_keybind", capture=True)
        
        def add_toggle_row(row_idx, label1, var1, label2, var2, result_var, tooltip_key):
            ttk.Label(group, text=label1).grid(row=row_idx, column=0, sticky="w", padx=(0, 5), pady=2)
            e1 = ttk.Entry(group, textvariable=var1, width=8, state="readonly")
            e1.grid(row=row_idx, column=1, sticky="ew", padx=(0, 2), pady=2)
            ttk.Button(group, text="Capture", width=7, command=partial(self.do_capture, var1)).grid(row=row_idx, column=2, padx=(0, 10), pady=2)
            
            ttk.Label(group, text=label2).grid(row=row_idx, column=3, sticky="w", padx=(0, 5), pady=2)
            e2 = ttk.Entry(group, textvariable=var2, width=8, state="readonly")
            e2.grid(row=row_idx, column=4, sticky="ew", padx=(0, 2), pady=2)
            ttk.Button(group, text="Capture", width=7, command=partial(self.do_capture, var2)).grid(row=row_idx, column=5, padx=(0, 10), pady=2)
            
            ttk.Label(group, textvariable=result_var, foreground="#D35400", font=("Segoe UI", 9, "bold")).grid(row=row_idx, column=6, sticky="w", padx=(0, 5), pady=2)
            self._add_tip(tooltip_key, e1, e2)

        add_toggle_row(1, "Repot Toggle Key 1", self.repot_toggle_1_var, "Repot Toggle Key 2", self.repot_toggle_2_var, self.repot_result_var, "repot_toggle")
        add_toggle_row(2, "Rebuff Toggle Key 1", self.rebuff_toggle_1_var, "Rebuff Toggle Key 2", self.rebuff_toggle_2_var, self.rebuff_result_var, "rebuff_toggle")
        add_toggle_row(3, "Looting Toggle Key 1", self.looting_toggle_1_var, "Looting Toggle Key 2", self.looting_toggle_2_var, self.looting_toggle_result_var, "looting_toggle")
        add_toggle_row(4, "Start/Stop Toggle Key 1", self.start_stop_toggle_1_var, "Start/Stop Toggle Key 2", self.start_stop_toggle_2_var, self.start_stop_result_var, "start_stop_toggle")
        
        self._update_toggle_results()
        for var in (self.repot_toggle_1_var, self.repot_toggle_2_var,
                    self.rebuff_toggle_1_var, self.rebuff_toggle_2_var,
                    self.looting_toggle_1_var, self.looting_toggle_2_var,
                    self.start_stop_toggle_1_var, self.start_stop_toggle_2_var):
            var.trace_add("write", lambda *args: self._update_toggle_results())

    def _update_toggle_results(self) -> None:
        """Updates the dynamic text showing the combined toggle keybinds."""
        def format_result(v1, v2):
            k1, k2 = v1.get().strip(), v2.get().strip()
            if k1 and k2 and k1 != k2:
                return f"Bound to {k1} + {k2}"
            elif k1:
                return f"Bound to {k1}"
            else:
                return "Unbound"
                
        self.repot_result_var.set(format_result(self.repot_toggle_1_var, self.repot_toggle_2_var))
        self.rebuff_result_var.set(format_result(self.rebuff_toggle_1_var, self.rebuff_toggle_2_var))
        self.looting_toggle_result_var.set(format_result(self.looting_toggle_1_var, self.looting_toggle_2_var))
        self.start_stop_result_var.set(format_result(self.start_stop_toggle_1_var, self.start_stop_toggle_2_var))

    def _build_controls(self, frame: ttk.Frame, row: int) -> None:
        """Builds Start/Stop and the status lines below the settings groups.

        Args:
            frame: The dashboard frame.
            row: First grid row to use.
        """
        self.start_btn = ttk.Button(frame, text="Start", command=self.start,
                                    style="Start.TButton")
        self.stop_btn = ttk.Button(frame, text="Stop", command=self.stop,
                                   state=tk.DISABLED, style="Stop.TButton")
        self.start_btn.grid(row=row, column=1, sticky="e", padx=6, pady=8,
                            ipadx=12, ipady=2)
        self.stop_btn.grid(row=row, column=2, sticky="w", padx=6, pady=8,
                           ipadx=12, ipady=2)
        self._add_tip("start", self.start_btn)
        self._add_tip("stop", self.stop_btn)

        self.status = tk.StringVar(value="Idle")
        self.info = tk.StringVar(value="")
        self.status_label = ttk.Label(
            frame, textvariable=self.status, wraplength=STATUS_WRAP,
            font=self._bold_font)
        self.status_label.grid(row=row + 1, column=0,
                               columnspan=DASHBOARD_SPAN, sticky="w",
                               padx=GROUP_PADX)
        self.info_label = ttk.Label(frame, textvariable=self.info,
                                    justify=tk.LEFT)
        self.info_label.grid(row=row + 2, column=0, columnspan=DASHBOARD_SPAN,
                             sticky="w", padx=GROUP_PADX, pady=(2, 0))
        frame.bind("<Configure>", self._wrap_status, add="+")

    def _wrap_status(self, _event: object = None) -> None:
        """Wraps the status line to the current width of the dashboard."""
        width = self.dashboard_tab.winfo_width()
        if width > 1:
            margin = 2 * (DASHBOARD_PADDING + GROUP_PADX)
            self.status_label.configure(
                wraplength=max(STATUS_MIN_WRAP, width - margin))

    WINDOW_TITLE_HELP: str = ("Leave blank to use static coordinates. Enter "
                              "exact game window title for auto-tracking.")
    SETUP_INCOMPLETE: str = ("Setup Incomplete: Please calibrate your bars in "
                             "the 'Calibrate Bars' tab before starting.")

    def toggle_manual_fields(self) -> None:
        """Shows or hides the manual capture-region fields."""
        show = self.advanced_toggle_var.get()
        for widget in (*self.manual_labels, *self.manual_fields):
            if show:
                widget.grid()
            else:
                widget.grid_remove()

    def on_window_select(self, _event: object = None) -> None:
        """Loads the selected window's geometry into the manual fields."""
        selected_title = self.window_title_var.get().strip()
        if not selected_title or gw is None:
            return
        try:
            window = gw.getWindowsWithTitle(selected_title)[0]
            values = {
                "CAPTURE_TOP": str(int(window.top)),
                "CAPTURE_LEFT": str(int(window.left)),
                "CAPTURE_WIDTH": str(int(window.width)),
                "CAPTURE_HEIGHT": str(int(window.height)),
            }
        except IndexError:  # the window was closed since the list was built
            return
        except Exception as exc:  # pygetwindow/platform failure
            self._report_error(
                f"Could not read window '{selected_title}': {exc}", exc)
            return
        for attr, value in values.items():
            self.fields[attr].set(value)

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
        ends (finished, cancelled, closed, crashed) or fails to start, and a
        failure to start is shown in an error dialog.
        """
        if self._calibrator is not None:
            return
        if self.runner.running:
            self.status.set("Stop the bot before calibrating.")
            return
        if not self.save():
            return
        self.root.withdraw()
        try:
            self._calibrator = subprocess.Popen(
                [sys.executable, str(CALIBRATOR_PATH)],
                cwd=str(CALIBRATOR_PATH.parent))
        except OSError as exc:
            self.root.deiconify()
            self._report_error(f"Could not launch calibrator: {exc}", exc)
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
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nsew")
        ttk.Button(self.buffs_tab, text="Add",
                   command=self.add_buff_dialog).grid(row=1, column=0, pady=5, padx=2)
        ttk.Button(self.buffs_tab, text="Edit",
                   command=self.edit_buff_dialog).grid(row=1, column=1, pady=5, padx=2)
        ttk.Button(self.buffs_tab, text="Toggle",
                   command=self.toggle_buff).grid(row=1, column=2, pady=5, padx=2)
        ttk.Button(self.buffs_tab, text="Delete",
                   command=self.delete_buff).grid(row=1, column=3, pady=5, padx=2)
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
            self._report_error(f"Save failed: {exc}", exc)
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

    def edit_buff_dialog(self) -> None:
        """Opens a dialog to edit the selected schedule."""
        name = self._selected_name()
        if name is None:
            messagebox.showinfo("Edit Buff", "Please select a buff from the list to edit.")
            return
            
        schedules = config.load_schedules()
        original = next((s for s in schedules if s.name == name), None)
        if original is None:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Buff: {name}")
        dialog.transient(self.root)
        vars_: Dict[str, tk.StringVar] = {}
        
        fields = [
            ("Name", original.name),
            ("Keybind", original.keybind),
            ("Interval (s)", str(original.interval_seconds))
        ]
        
        for row, (label, default) in enumerate(fields):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=2)
            var = tk.StringVar(value=default)
            ttk.Entry(dialog, textvariable=var, width=20).grid(row=row, column=1, padx=5, pady=2)
            if label == "Keybind":
                ttk.Button(dialog, text="Capture", width=8,
                           command=lambda v=var: self.do_capture(v)).grid(row=row, column=2, padx=5, pady=2)
            vars_[label] = var
            
        error = tk.StringVar()
        ttk.Label(dialog, textvariable=error, foreground="red").grid(
            row=3, column=0, columnspan=3)

        original_name = original.name

        def submit() -> None:
            try:
                new_name = vars_["Name"].get().strip()
                new_keybind = vars_["Keybind"].get().strip()
                new_interval = float(vars_["Interval (s)"].get())
                
                if not new_name:
                    raise ValueError("name cannot be empty")
                if not new_keybind:
                    raise ValueError("keybind cannot be empty")
                if not 0.0 < new_interval < float("inf"):
                    raise ValueError("interval must be a positive number")
                    
                schedules = config.load_schedules()
                if new_name != original_name and any(s.name == new_name for s in schedules):
                    raise ValueError("name already exists")
                    
                for s in schedules:
                    if s.name == original_name:
                        s.name = new_name
                        s.keybind = new_keybind
                        s.interval_seconds = new_interval
                        break
                        
                self._persist_buffs(schedules)
                dialog.destroy()
            except ValueError as exc:
                error.set(str(exc))

        ttk.Button(dialog, text="Save Changes", command=submit).grid(
            row=4, column=0, columnspan=3, pady=5)

    def do_capture(self, target_var: tk.StringVar) -> None:
        """Opens a non-blocking capture dialog for one key or mouse input.

        The first key press or mouse click (left, right or middle button)
        is written into ``target_var``. A worker thread waits for the input
        so the Tk event loop never blocks, and the dialog polls for the
        result. If the input backend is unavailable the dialog is closed
        and the problem is shown in an error dialog; if nothing is pressed
        within ``CAPTURE_TIMEOUT_S`` seconds the dialog closes as well.

        Args:
            target_var: The variable that receives the captured name.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Key Capture")
        dialog.transient(self.root)
        prompt = ttk.Label(dialog, text="Press any key or mouse button...")
        dialog.label = prompt  # type: ignore[attr-defined]
        prompt.pack(padx=20, pady=(20, 4))
        ttk.Label(dialog, foreground=self.STATUS_COLORS["idle"],
                  text=("Media keys and the left, right and middle mouse "
                        "buttons are supported.")).pack(padx=20, pady=(0, 20))
        dialog.grab_set()
        result: Dict[str, str | None] = {"val": None, "error": None}
        finished = threading.Event()
        cancel = threading.Event()

        def run_capture() -> None:
            """Runs the key-capture helper in a worker thread."""
            try:
                from key_capture import capture_single_input
                result["val"] = capture_single_input(
                    timeout=CAPTURE_TIMEOUT_S, cancel=cancel)
            except Exception as exc:  # missing module, no input backend, ...
                result["error"] = str(exc) or type(exc).__name__
            finally:
                finished.set()

        def check_result() -> None:
            """Polls until the capture thread finishes and then stores the value."""
            if not dialog.winfo_exists():
                return
            if not finished.is_set():
                self.root.after(100, check_result)
                return
            dialog.destroy()
            if result["error"] is not None:
                self._report_error(
                    f"Key capture failed: {result['error']}", result["error"])
            elif result["val"] is not None:
                old_val = target_var.get()
                target_var.set(result["val"])
                
                # Test the new key against all other keys immediately
                error_msg = self._validate_all_keybinds()
                if error_msg:
                    target_var.set(old_val) # Revert to the old key
                    messagebox.showerror(
                        "Invalid Keybind", 
                        f"Cannot bind this key:\n\n{error_msg}\n\nPlease choose a different key."
                    )
                # If no error, the new value stays set and the dynamic UI updates automatically
            else:
                self.status.set("Key capture timed out: no input detected.")

        def on_dialog_destroy(event: object) -> None:
            """Stops the worker when the dialog is closed or the app exits."""
            if getattr(event, "widget", None) is dialog:
                cancel.set()

        dialog.bind("<Destroy>", on_dialog_destroy)
        capture_thread = threading.Thread(target=run_capture, daemon=True)
        capture_thread.start()
        self.root.after(100, check_result)

    @staticmethod
    def _parse_number(label: str, text: str, minimum: float | None = None,
                      maximum: float | None = None) -> float:
        """Parses one numeric entry.

        Args:
            label: Field name used in error messages.
            text: The raw entry text.
            minimum: Smallest accepted value (inclusive), if any.
            maximum: Largest accepted value (inclusive), if any.

        Returns:
            The parsed value.

        Raises:
            ValueError: If ``text`` is not a finite number in range.
        """
        shown = text.strip()
        try:
            value = float(shown)
        except ValueError:
            raise ValueError(
                f"{label} must be a number (got '{shown}').") from None
        if not math.isfinite(value):
            raise ValueError(
                f"{label} must be a finite number (got '{shown}').")
        if minimum is not None and value < minimum:
            raise ValueError(
                f"{label} must be at least {minimum:g} (got '{shown}').")
        if maximum is not None and value > maximum:
            raise ValueError(
                f"{label} must be at most {maximum:g} (got '{shown}').")
        return value

    def _report_error(self, status: str, detail: object) -> None:
        """Shows a problem in the status line and in an error dialog.

        Args:
            status: Text for the status line.
            detail: The exception (or message) shown in the dialog.
        """
        self.status.set(status)
        messagebox.showerror(ERROR_TITLE, str(detail) or status)

    def _validate_all_keybinds(self) -> Optional[str]:
        """Validates all keybinds against the Golden Rules. Returns an error string or None."""
        hp_key = self.hp_keybind_var.get().strip()
        mp_key = self.mp_keybind_var.get().strip()
        loot_key = self.looting_keybind_var.get().strip()
        action_keys = [k for k in [hp_key, mp_key, loot_key] if k]
        
        if len(action_keys) != len(set(action_keys)):
            return "In-game keybinds (HP, MP, Loot) must be unique from each other."

        toggle_vars = [
            ("Repot", self.repot_toggle_1_var.get().strip(), self.repot_toggle_2_var.get().strip()),
            ("Rebuff", self.rebuff_toggle_1_var.get().strip(), self.rebuff_toggle_2_var.get().strip()),
            ("Looting", self.looting_toggle_1_var.get().strip(), self.looting_toggle_2_var.get().strip()),
            ("Start/Stop", self.start_stop_toggle_1_var.get().strip(), self.start_stop_toggle_2_var.get().strip()),
        ]
        
        all_toggle_keys_flat = []
        dual_toggles = []
        single_toggles = []
        
        for name, k1, k2 in toggle_vars:
            if not k1 and not k2:
                continue
            if k1 and k2 and k1 != k2:
                all_toggle_keys_flat.extend([k1, k2])
                dual_toggles.append(frozenset([k1, k2]))
            else:
                single_key = k1 or k2
                all_toggle_keys_flat.append(single_key)
                single_toggles.append(single_key)

        if set(action_keys).intersection(set(all_toggle_keys_flat)):
            return "In-game keybinds cannot be used as Toggle Keys."

        if len(single_toggles) != len(set(single_toggles)):
            return "Single Toggle Keys must be unique."
            
        dual_keys_flat = []
        for pair in dual_toggles:
            dual_keys_flat.extend(list(pair))
            
        if set(single_toggles).intersection(set(dual_keys_flat)):
            return "Single Toggle Keys cannot be part of Dual Toggle Keys."

        if len(dual_toggles) != len(set(dual_toggles)):
            return "Dual Toggle Key combinations must be unique."

        return None

    def apply_settings(self) -> bool:
        """Validates the entries and writes them into ``config``."""
        parsed: Dict[str, float] = {}
        try:
            for attr, var in self.fields.items():
                value = float(var.get())
                if attr == "MATCH_THRESHOLD":
                    if not 0.0 <= value <= 1.0:
                        raise ValueError("threshold must be 0-1")
                elif attr.endswith(("WIDTH", "HEIGHT")):
                    if value < 1:
                        raise ValueError(f"invalid {attr}")
                    value = int(value)
                elif attr.endswith(("TOP", "LEFT")):
                    # Clamp negative coordinates to 0 to prevent crashes
                    value = max(0, int(value))
                else:
                    value = int(value)
                parsed[attr] = value
        except ValueError as exc:
            self.status.set(f"Invalid settings: {exc}")
            return False

        # Validate keybinds
        validation_error = self._validate_all_keybinds()
        if validation_error:
            self.status.set(f"Invalid settings: {validation_error}")
            return False
            
        # Apply numeric/capture settings
        for attr, value in parsed.items():
            setattr(config, attr, value)
        config.WINDOW_TITLE = self.window_title_var.get().strip()
        
        # APPLY KEYBINDS AND TOGGLES TO MEMORY IMMEDIATELY
        config.HEALTH.threshold_percent = float(self.hp_threshold_var.get())
        config.HEALTH.keybind = self.hp_keybind_var.get().strip()
        config.HEALTH.cooldown = float(self.hp_cooldown_var.get())
        config.MANA.threshold_percent = float(self.mp_threshold_var.get())
        config.MANA.keybind = self.mp_keybind_var.get().strip()
        config.MANA.cooldown = float(self.mp_cooldown_var.get())
        config.REPOT_TOGGLE_1 = self.repot_toggle_1_var.get().strip()
        config.REPOT_TOGGLE_2 = self.repot_toggle_2_var.get().strip()
        config.REBUFF_TOGGLE_1 = self.rebuff_toggle_1_var.get().strip()
        config.REBUFF_TOGGLE_2 = self.rebuff_toggle_2_var.get().strip()
        config.LOOTING_TOGGLE_1 = self.looting_toggle_1_var.get().strip()
        config.LOOTING_TOGGLE_2 = self.looting_toggle_2_var.get().strip()
        config.START_STOP_TOGGLE_1 = self.start_stop_toggle_1_var.get().strip()
        config.START_STOP_TOGGLE_2 = self.start_stop_toggle_2_var.get().strip()
        config.LOOTING_KEYBIND = self.looting_keybind_var.get().strip()

        return True
    def start(self) -> None:
        """Applies settings and starts the worker threads.

        Any failure is shown in the status line and in an error dialog; the
        Start/Stop buttons keep their state.
        """
        try:
            if not self.apply_settings():
                return
            if not self.is_calibration_valid():
                self.status.set(self.SETUP_INCOMPLETE)
                self.start_btn.config(state=tk.DISABLED)
                return
            self.runner.start()
            # Launch OSD
            try:
                from osd import OSDWindow
                self._osd_root = tk.Toplevel(self.root)
                self._osd = OSDWindow(self.runner.state, root=self._osd_root)
            except Exception as exc:
                logger.error(f"Failed to start OSD: {exc}")
                self._osd = None
        except Exception as exc:  # e.g. no display / input backend
            logger.error(f"Could not start: {exc}", exc_info=True)
            self._report_error(f"Could not start: {exc}", exc)
            return
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status.set("Running")

    def stop(self) -> None:
        """Stops the worker threads."""
        if self._osd is not None:
            try:
                self._osd.close()
            except Exception:
                pass
            self._osd = None
        if self._osd_root is not None:
            try:
                self._osd_root.destroy()
            except Exception:
                pass
            self._osd_root = None
        self.runner.stop()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status.set("Stopped (settings saved)")
        self.save()

    def save(self) -> bool:
        """Persists the current settings to ``calibration.json``.

        Returns:
            True if the settings were valid and written to disk.
        """
        if not self.apply_settings():
            return False
        try:
            config.save_config()
        except OSError as exc:
            self._report_error(f"Save failed: {exc}", exc)
            return False
        return True

    @classmethod
    def status_color(cls, text: str) -> str:
        """Picks the display colour of a status line.

        Args:
            text: The current status text.

        Returns:
            Green while running, red for errors and blocked states, and grey
            for everything else (idle, stopped, ready).
        """
        if text.startswith(("Running", "Foraging")):
            return cls.STATUS_COLORS["running"]
        if text.startswith(cls.ERROR_PREFIXES):
            return cls.STATUS_COLORS["error"]
        return cls.STATUS_COLORS["idle"]

    def refresh(self) -> None:
        """Updates the live status display and reschedules itself.

        The status line is green while running, red after an error and grey
        otherwise. The next tick is always scheduled (unless the window is
        closing), so a transient error cannot freeze the status panel.
        """
        try:
            self.status_label.configure(
                foreground=self.status_color(self.status.get()))
            snap = self.runner.state.snapshot()
            if snap.get("hotkey_start_stop"):
                self.runner.state.set("hotkey_start_stop", False)
                if self.runner.running:
                    self.stop()
                else:
                    self.start()
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
        return (f"Looting: Inactive (Press {config.LOOTING_TOGGLE_1}"
                f"+{config.LOOTING_TOGGLE_2} to toggle)")

    def show_exit_popup(self) -> tk.Toplevel:
        """Shows a high-converting thank-you popup with a link to the GitHub repository."""
        popup = tk.Toplevel(self.root)
        popup.title("Support the Project")
        popup.transient(self.root)
        popup.configure(padx=20, pady=20)

        # Psychological Framing (Using your exact text)
        ttk.Label(
            popup,
            text="If this tool helped you today, please consider\n"
                 "leaving a star on this repo! ⭐\n\n"
                 "It gives me a sense of the community's overall\n"
                 "interest and keeps me motivated!",
            wraplength=380,
            justify=tk.CENTER,
            font=("Segoe UI", 11)
        ).pack(pady=(10, 20))

        # Primary Action: Open Browser and Copy Link
        def open_and_copy():
            self.root.clipboard_clear()
            self.root.clipboard_append("https://github.com/pengkenlim/MushroomGameHelper")
            webbrowser.open("https://github.com/pengkenlim/MushroomGameHelper")
            popup.destroy()

        star_btn = tk.Button(
            popup,
            text="⭐ Star on GitHub (Link Copied!) ⭐",
            command=open_and_copy,
            bg="#24292e",  # GitHub Dark Theme Color
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=10,
            relief=tk.FLAT,
            cursor="hand2"
        )
        star_btn.pack(pady=(0, 15))

        # Secondary Action: Just Close
        ttk.Button(
            popup, 
            text="No thanks, just close", 
            command=popup.destroy
        ).pack(pady=(0, 5))

        popup.grab_set()
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        
        # Center the popup on the main window
        popup.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (popup.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (popup.winfo_height() // 2)
        popup.geometry(f"+{x}+{y}")
        
        return popup

    def on_close(self) -> None:
        """Stops threads (releasing keys) and closes the window."""
        self._closing = True
        if self._osd is not None:
            try:
                self._osd.close()
            except Exception:
                pass
            self._osd = None
        if self._osd_root is not None:
            try:
                self._osd_root.destroy()
            except Exception:
                pass
            self._osd_root = None
        for after_id in (self._refresh_id, self._poll_id):
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
        proc = self._calibrator
        if proc is not None and proc.poll() is None:
            proc.terminate()

        popup = self.show_exit_popup()
        self.root.wait_window(popup)
        try:
            self.runner.stop()
            self.save()
        finally:
            self.root.destroy()


def launch() -> None:
    """Creates the main window."""
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    launch()
