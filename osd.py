"""On-screen display: a small always-on-top overlay showing bot status."""

import sys
import time
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional
import ctypes
from ctypes import wintypes

# pynput is already in your requirements.txt
from pynput import mouse

import config
from state import SharedState

REFRESH_MS: int = 250  # 4 FPS, matching the vision loop
ALPHA: float = 0.5
CLICK_THROUGH: bool = True
BG_COLOR: str = "black"
FG_COLOR: str = "#00ff66"
FONT: tuple[str, int, str] = ("Consolas", 9, "bold")
POSITION: str = "+10+10"


def format_percent(label: str, value: Optional[float]) -> str:
    return f"{label}: --%" if value is None else f"{label}: {value:.0f}%"

def format_buffs(schedule_status: Optional[List[Dict[str, Any]]]) -> str:
    items = [f"{s['name']} [{s['keybind']}]" for s in schedule_status or []]
    return f"Active Buffs: [{', '.join(items)}]"

def format_toggle(label: str, enabled: bool, key1: str, key2: str) -> str:
    state = "ON" if enabled else "OFF"
    return f"{label}: [{state}] (Toggle: {key1}+{key2})"

def format_last_actions(last_actions: Optional[List[Dict[str, Any]]]) -> str:
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
    if not schedule_status:
        return "Buff countdowns: None"
    now = time.perf_counter()
    lines = []
    for item in schedule_status:
        remaining = max(0.0, float(item.get("next_due", 0.0)) - now)
        lines.append(f"{item.get('name', 'Buff')} in {remaining:.1f}s")
    return "Buff countdowns: " + (" | ".join(lines) if lines else "None")


def set_window_transparent(hwnd: int, transparent: bool) -> None:
    """Toggles WS_EX_TRANSPARENT safely without hooking the message pump."""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if transparent:
            style |= (WS_EX_LAYERED | WS_EX_TRANSPARENT)
        else:
            style &= ~WS_EX_TRANSPARENT
            style |= WS_EX_LAYERED # Keep layered for alpha
        
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass


class OSDWindow:
    """Borderless, semi-transparent, always-on-top status overlay."""

    def __init__(
        self,
        state: SharedState,
        root: Optional[tk.Tk] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
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
                ("inputs", "Your keys held: 0"),
                ("autolooting", "Autolooting: OFF (Toggle: ctrl+l)"),
                ("repot", "Re-poting: OFF (Toggle: ctrl+r)"),
                ("rebuff", "Re-buffing: OFF (Toggle: ctrl+b)"),
                ("start_stop", "Start/Stop: Unbound"),
                ("last_actions", "Recent Actions: None"),
                ("buffs", "Active Buffs: []"),
                ("buff_countdowns", "Buff countdowns: None"),
            )}
        for var in self.vars.values():
            tk.Label(self.root, textvariable=var, bg=BG_COLOR, fg=FG_COLOR,
                     font=FONT, anchor="w", justify=tk.LEFT,
                     padx=8, pady=1).pack(fill=tk.X)

        # Add drag hint at top-right corner
        self.drag_hint = tk.Label(
            self.root,
            text="🖱️ Right-click to drag",
            bg=BG_COLOR,
            fg="#888888",  # Dimmer gray color
            font=("Consolas", 8),  # Smaller font
            anchor="ne",
            padx=4,
            pady=2
        )
        self.drag_hint.place(relx=1.0, rely=0.0, anchor="ne")

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        
        # --- DRAG & CLICK-THROUGH LOGIC ---
        self.root.update_idletasks()
        self._hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        
        # Start fully transparent (left clicks pass through)
        if CLICK_THROUGH:
            set_window_transparent(self._hwnd, True)
        
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        
        def on_move(x, y):
            if self._dragging:
                try:
                    dx = x - self._drag_start_x
                    dy = y - self._drag_start_y
                    curr_x = self.root.winfo_x()
                    curr_y = self.root.winfo_y()
                    self.root.geometry(f"+{curr_x + dx}+{curr_y + dy}")
                    self._drag_start_x = x
                    self._drag_start_y = y
                except tk.TclError:
                    pass

        def on_click(x, y, button, pressed):
            if button == mouse.Button.right:
                if pressed:
                    # Right button pressed: Disable transparency to catch the drag
                    if CLICK_THROUGH:
                        set_window_transparent(self._hwnd, False)
                    self.root.attributes("-topmost", True)
                    self._dragging = True
                    self._drag_start_x = x
                    self._drag_start_y = y
                    # Hide the hint while dragging
                    self.drag_hint.place_forget()
                else:
                    # Right button released: Re-enable transparency
                    self._dragging = False
                    if CLICK_THROUGH:
                        set_window_transparent(self._hwnd, True)
                    # Show the hint again
                    self.drag_hint.place(relx=1.0, rely=0.0, anchor="ne")

        self._mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click)
        self._mouse_listener.start()
        # -------------------------------

        self.refresh()

    def refresh(self) -> None:
        """Re-reads the shared state, updates the labels and reschedules."""
        try:
            if self._closed:
                return
            snap = self._state.snapshot()
            self.vars["hp"].set(format_percent("HP", snap.get("health_percent")))
            self.vars["mp"].set(format_percent("MP", snap.get("mana_percent")))
            self.vars["inputs"].set(f"Your keys held: {snap.get('physical_keys_held', 0)}")
            self.vars["autolooting"].set(format_toggle("Autolooting", bool(snap.get("looting_active", False)), config.LOOTING_TOGGLE_1, config.LOOTING_TOGGLE_2))
            self.vars["repot"].set(format_toggle("Re-poting", bool(snap.get("repot_active", False)), config.REPOT_TOGGLE_1, config.REPOT_TOGGLE_2))
            self.vars["rebuff"].set(format_toggle("Re-buffing", bool(snap.get("rebuff_active", False)), config.REBUFF_TOGGLE_1, config.REBUFF_TOGGLE_2))
            k1, k2 = config.START_STOP_TOGGLE_1, config.START_STOP_TOGGLE_2
            if k1 and k2 and k1 != k2:
                self.vars["start_stop"].set(f"Start/Stop: [{k1} + {k2}]")
            elif k1:
                self.vars["start_stop"].set(f"Start/Stop: [{k1}]")
            else:
                self.vars["start_stop"].set("Start/Stop: Unbound")
            self.vars["last_actions"].set(format_last_actions(snap.get("last_actions")))
            self.vars["buffs"].set(format_buffs(snap.get("schedule_status")))
            self.vars["buff_countdowns"].set(format_buff_countdowns(snap.get("schedule_status")))
        except Exception as exc:
            from logger import logger
            logger.error(f"OSD refresh error: {exc}")
        finally:
            if not self._closed:
                self._after_id = self.root.after(REFRESH_MS, self.refresh)

    def close(self) -> None:
        """Closes the overlay (idempotent) and runs the ``on_close`` callback."""
        if self._closed:
            return
        self._closed = True
        
        # Stop the pynput listener cleanly
        if hasattr(self, '_mouse_listener') and self._mouse_listener.is_alive():
            self._mouse_listener.stop()
            
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
        self.root.destroy()
        if self._on_close is not None:
            self._on_close()

    def run(self) -> None:
        """Runs the Tk main loop; background daemon threads keep running."""
        self.root.mainloop()


def launch_osd(state: SharedState, on_close: Optional[Callable[[], None]] = None) -> None:
    OSDWindow(state, on_close=on_close).run()