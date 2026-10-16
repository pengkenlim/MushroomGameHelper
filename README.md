<div align="center">

# 🍄 MushroomGameHelper

**A classical computer-vision assistant for 2D pixelated games: it watches your screen, reads your health and mana bars, and presses the right keys at the right time.**

[Quick Start](#quick-start) • [Features](#features) • [Philosophy](#philosophy)

</div>

> [!IMPORTANT]
> **Attention:** Before downloading or using this tool, please take a moment to read the [Project Philosophy & Design Intent](#a-note-on-the-projects-origins-and-philosophy) statement at the bottom of this page. This project was built with deep respect for the game's core loop and the community in mind!

---

## 🍄 What It Does

MushroomGameHelper takes a picture of a rectangle of your screen 20 times a second, measures how full your **health** and **mana** bars are using plain colour maths (no machine learning), and presses your potion keys when a bar runs low. It can also press buffs on a timer, hold a loot key for you, and automatically adapt when you move the game window. Special care has been taken to avoid button conflicts and prioritize user input.

Everything is set up from one tabbed window, and a small in-game overlay shows what the bot is doing.

| Feature | What it does | Where you set it up |
| --- | --- | --- |
| **Auto-heal / auto-mana** | Presses your HP/MP key while a bar is below its threshold (with a cooldown). | **Dashboard** → *Resource Monitoring* |
| **Timed buffs** | Presses a key every *N* seconds. | **Manage Buffs** tab |
| **Autolooting** | Rapidly taps a loot key so the game never ignores it. | **Dashboard** → *Action Toggles & Keybinds* |
| **Dynamic window tracking** | Follows the game window when you move it. | **Dashboard** → *Game Window Targeting* |
| **Key capture** | Records any key, media key or mouse button for you. | **Capture** buttons |
| **OSD overlay** | Always-on-top status box: HP, MP, toggles, recent key presses and buff timers. | Appears automatically with the GUI |
| **Input contention guard** | Defers bot actions when you're pressing many keys to avoid game engine conflicts. | Automatic (configurable in `config.py`) |

![Dashboard Tab - Grouped Settings](docs/screenshots/dashboard_grouped.png)
*The unified Dashboard tab with grouped configuration frames and interactive tooltips.*

| Layer | Technology | Role |
| --- | --- | --- |
| Capture | `mss` | Grabs the configured screen region. |
| Vision | `OpenCV` + `NumPy` | HSV colour thresholding for bars, template matching for sprites. |
| Input | `pynput` | Presses/holds keys and mouse buttons, and listens for the toggle hotkeys. |
| Interface | `Tkinter` | Tabbed GUI and the on-screen display. |
| Language | Python 3.10+ | Three cooperating threads: vision, scheduler, action. |

> [!NOTE]
> This project was built for learning and reliability. Use it responsibly and only in games whose terms of service permit automation.

---

## 📑 Table of Contents

1. [🚀 Quick Start](#quick-start)
2. [🖥️ GUI Walkthrough: Dashboard • Calibrate Bars • Manage Buffs](#gui-walkthrough)
3. [🧠 Advanced Features: Dual-Key Toggles • Key Capture • Dynamic Window Tracking](#advanced-features)
4. [📺 OSD & Telemetry](#osd-telemetry)
5. [🛡️ Platform Notes](#platform-notes)
6. [🩺 Troubleshooting Matrix](#troubleshooting)
7. [📁 Commands, Files and Configuration](#reference)
8. [🏗️ Architecture](#architecture)
9. [🍄 A Note on the Project’s Origins and Philosophy](#a-note-on-the-projects-origins-and-philosophy)

---

<a id="quick-start"></a>

## 🚀 Quick Start

Four steps from a fresh download to a running bot:

- [ ] **Step 1: Install.** You need **Python 3.10 or newer**. Open a terminal in the project folder (the one containing `main.py`) and run:

  ```bash
  python -m pip install --upgrade pip
  pip install -r requirements.txt