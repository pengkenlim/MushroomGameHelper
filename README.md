# MushroomGameHelper
A project to learn `Tkinter`, `mss`, `OpenCV`, "pynput" and GitHub Copilot agentic capabilities. An excuse to make my life easier in a certain mushroom game. *wink wink*

## Architecture

Two decoupled threads communicate only through a lock-protected `SharedState`:

- **Vision thread** (`vision.py`, every 250 ms / ~4 FPS): captures the region
  with `mss`, runs `cv2.matchTemplate` for sprites and `cv2.inRange` for color
  thresholds, and writes structured results (coordinates, booleans) to state.
- **Action thread** (`action.py`, every 100 ms / ~10 Hz): reads a state
  snapshot and simulates input with `pynput`.
- `state.py` – thread-safe dictionary; `config.py` – all constants;
  `main.py` – spawns threads and handles `Ctrl+C` (keys released, threads joined).

## Installation

```bash
pip install -r requirements.txt
```
`Tkinter` ships with Python; on Debian/Ubuntu install it with `sudo apt install python3-tk`.

## Configuring the screen region

Edit `CAPTURE_TOP`, `CAPTURE_LEFT`, `CAPTURE_WIDTH`, `CAPTURE_HEIGHT` in
`config.py` (pixels, primary monitor) so they cover the game window. Adjust
`MATCH_THRESHOLD`, HSV bounds and `KEYBINDS` as needed.

## Adding template images

1. Crop the sprite from a screenshot at native resolution (no scaling) and save
   it as PNG in `templates/`.
2. Register it in `config.TEMPLATES`, e.g. `"slime": "templates/slime.png"`.
3. Optionally set a per-template confidence in `config.TEMPLATE_THRESHOLDS`.
4. Matches appear in the shared state under `matches["slime"]` as
   `(x, y, confidence)` tuples; use them in `Action.decide`.

## Run

```bash
python main.py          # headless, Ctrl+C to stop
python main.py --gui    # Tkinter GUI (or: python gui.py)
```

The GUI lets you edit the capture region and match threshold, start/stop the
threads, and view live detection status. Closing the window stops the threads
and releases any held keys.
