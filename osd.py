"""On-screen display: a small always-on-top overlay showing bot status."""

import sys
import time
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

import config
from state import SharedState

REFRESH_MS: int = 250  # 4 FPS, matching the vision loop
ALPHA: float = 0.8
# True: mouse clicks pass through to the game, but Escape will NOT work
#       on Windows (close with Ctrl+C in the terminal instead).
# False: the overlay can be focused and closed with Escape, but it will
#        block mouse clicks over its area.
CLICK_THROUGH: bool = True
BG_COLOR: str = "black"
FG_COLOR: str = "#00ff66"
FONT: tuple[str, int, str] = ("Consolas", 11, "bold")
POSITION: str = "+10+10"


def format_percent(label: str, value: Optional[float]) -> str:
    """Formats a bar reading.

    Args:
        label: Prefix such as ``"HP"`` or ``"MP"``.
        value: Percentage (0-100) or None if vision has not reported yet.

    Returns:
        E.g. ``"HP: 85%"`` or ``"HP: --%"``.
    """
    return f"{label}: --%" if value is None else f"{label}: {value:.0f}%"


def format_buffs(schedule_status: Optional[List[Dict[str, Any]]]) -> str:
    """Formats the enabled buff schedules.

    Args:
        schedule_status: ``schedule_status`` entry of the shared state.

    Returns:
        ``"Active Buffs: [Name [key], ...]"`` (empty list if none).
    """
    items = [f"{s['name']} [{s['keybind']}]" for s in schedule_status or []]
    return f"Active Buffs: [{', '.join(items)}]"


def format_toggle(label: str, enabled: bool, key1: str, key2: str) -> str:
    """Returns a human-readable on/off status line for a toggle state."""
    state = "ON" if enabled else "OFF"
    return f"{label}: [{state}] (Toggle: {key1}+{key2})"


def format_last_actions(last_actions: Optional[List[Dict[str, Any]]]) -> str:
    """Formats the last few keyboard actions in the shared state."""
    items: List[str] = []
    for entry in (last_actions or [])[-3:]:
        key = str(entry.get("key", "?"))
        timestamp = entry.get("time")
        if isinstance(timestamp, (int, float)):
            stamp = time.strftime("%H:%M:%S", time.localtime(timestamp))
        else:
            stamp = "--:--:--"
        items.append(f"{stamp} - Pressed '{key}'")
    return "Recent Actions: " + (" | ".join(items) if items else "None")


def format_buff_countdowns(schedule_status: Optional[List[Dict[str, Any]]]) -> str:
    """Formats the active buff countdowns relative to the current time."""
    if not schedule_status:
        return "Buff countdowns: None"
    now = time.perf_counter()
    lines = []
    for item in schedule_status:
        remaining = max(0.0, float(item.get("next_due", 0.0)) - now)
        lines.append(f"{item.get('name', 'Buff')} in {remaining:.1f}s")
    return "Buff countdowns: " + (" | ".join(lines) if lines else "None")


def make_click_through(root: tk.Tk) -> bool:
    """Makes the window ignore mouse input and never take focus (Windows only).

    Adds the ``WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE |
    WS_EX_TOOLWINDOW`` extended styles through ``ctypes``. Other platforms have
    no equivalent in plain Tkinter, so nothing is changed there.

    Args:
        root: The overlay window (must already be realized).

    Returns:
        True if the styles were applied.
    """
    if not CLICK_THROUGH:
        return False
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        root.update_idletasks()
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        gwl_exstyle = -20
        style = user32.GetWindowLongW(hwnd, gwl_exstyle)
        style |= 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080
        user32.SetWindowLongW(hwnd, gwl_exstyle, style)
        # Extended styles only take effect after the window frame is rebuilt.
        swp_nosize = 0x0001
        swp_nomove = 0x0002
        swp_nozorder = 0x0004
        swp_noactivate = 0x0010
        swp_framechanged = 0x0020
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            swp_nomove | swp_nosize | swp_nozorder
            | swp_noactivate | swp_framechanged)
        return True
    except (OSError, AttributeError):
        return False


class OSDWindow:
    """Borderless, semi-transparent, always-on-top status overlay.

    The overlay is strictly read-only: it only calls ``SharedState.snapshot()``
    and never modifies the state.
    """

    def __init__(
        self,
        state: SharedState,
        root: Optional[tk.Tk] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        """Builds the overlay.

        Args:
            state: Shared state to display (read-only).
            root: Optional Tk root (a new one is created by default).
            on_close: Optional callback invoked when the overlay is closed.
        """
        self._state: SharedState = state
        self._on_close: Optional[Callable[[], None]] = on_close
        self._after_id: Optional[str] = None
        self._closed: bool = False
        self.root: tk.Tk = root or tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", ALPHA)
        self.root.configure(bg=BG_COLOR)
        self.root.geometry(POSITION)

        self.vars: Dict[str, tk.StringVar] = {
            name: tk.StringVar(value=text) for name, text in (
                ("hp", "HP: --%"), ("mp", "MP: --%"),
                ("autolooting", "Autolooting: OFF (Toggle: ctrl+l)"),
                ("repot", "Re-poting: OFF (Toggle: ctrl+r)"),
                ("rebuff", "Re-buffing: OFF (Toggle: ctrl+b)"),
                ("last_actions", "Recent Actions: None"),
                ("buffs", "Active Buffs: []"),
                ("buff_countdowns", "Buff countdowns: None"),
            )}
        for var in self.vars.values():
            tk.Label(self.root, textvariable=var, bg=BG_COLOR, fg=FG_COLOR,
                     font=FONT, anchor="w", justify=tk.LEFT,
                     padx=8, pady=1).pack(fill=tk.X)

        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if make_click_through(self.root):
            pass  # click-through active; Escape unavailable, use Ctrl+C
        else:
            self.root.focus_force()  # lets Escape close the overlay
        self.refresh()

    def refresh(self) -> None:
        """Re-reads the shared state, updates the labels and reschedules."""
        if self._closed:
            return
        snap = self._state.snapshot()
        self.vars["hp"].set(format_percent("HP", snap.get("health_percent")))
        self.vars["mp"].set(format_percent("MP", snap.get("mana_percent")))
        self.vars["autolooting"].set(
            format_toggle(
                "Autolooting",
                bool(snap.get("looting_active", False)),
                config.LOOTING_TOGGLE_1,
                config.LOOTING_TOGGLE_2,
            )
        )
        self.vars["repot"].set(
            format_toggle(
                "Re-poting",
                bool(snap.get("repot_active", False)),
                config.REPOT_TOGGLE_1,
                config.REPOT_TOGGLE_2,
            )
        )
        self.vars["rebuff"].set(
            format_toggle(
                "Re-buffing",
                bool(snap.get("rebuff_active", False)),
                config.REBUFF_TOGGLE_1,
                config.REBUFF_TOGGLE_2,
            )
        )
        self.vars["last_actions"].set(
            format_last_actions(snap.get("last_actions"))
        )
        self.vars["buffs"].set(format_buffs(snap.get("schedule_status")))
        self.vars["buff_countdowns"].set(
            format_buff_countdowns(snap.get("schedule_status"))
        )
        self._after_id = self.root.after(REFRESH_MS, self.refresh)

    def close(self) -> None:
        """Closes the overlay (idempotent) and runs the ``on_close`` callback."""
        if self._closed:
            return
        self._closed = True
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
        self.root.destroy()
        if self._on_close is not None:
            self._on_close()

    def run(self) -> None:
        """Runs the Tk main loop; background daemon threads keep running."""
        self.root.mainloop()


def launch_osd(state: SharedState, on_close: Optional[Callable[[], None]] = None
           ) -> None:
    """Creates the overlay and blocks until it is closed.

    Args:
        state: Shared state to display.
        on_close: Optional callback invoked when the overlay closes.
    """
    OSDWindow(state, on_close=on_close).run()
