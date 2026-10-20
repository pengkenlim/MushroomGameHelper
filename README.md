<div align="center">

# 🍄 MushroomGameHelper

**An external computer-vision assistant for 2D pixelated games.**  
It watches your screen, reads your health and mana bars, and presses the right keys at the right time—without ever reading game memory.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Status](https://img.shields.io/badge/Status-Active_Development-orange)
![Platform](https://img.shields.io/badge/Platform-Windows_10/11-lightgrey)

<br>

<img src="other_images/green_blob.png" alt="MushroomGameHelper Slime Blob" width="200" />

</div>

---
> [!IMPORTANT]
> **READ THIS FIRST:** Please read [A Note on the Project’s Origins and Philosophy](#philosophy) and [Why use this tool instead of other bots?](#why-use-this-tool) before you decide if this tool is for you, or if you have reservations about using the tool!

## 📊 Feature Status Map
*Transparency is key. Here is a quick summary of the tool's current capabilities based on inherent the game-engine limitations for the mushroom game.*

| Feature | Status | Caveats & Limitations |
| :--- | :---: | :--- |
| **Auto-Pot (HP/MP)** | 🟢 **100%** | Highly reliable with temporal filtering. *Note: Bot potion presses will briefly interrupt user-held attack keys (unavoidable OS input behavior).* |
| **Context-Aware Autoloot** | 🟡 **90%** | Holds the loot key when idle and releases on attack. *Note: The held-down loot key may occasionally be interrupted by rapid manual user input.* |
| **Timed Autobuff** | 🟠 **60%** | Uses rapid double-taps to bypass animation lockouts. *Note: Buff presses will interrupt held attack keys, and buffs may fail to register if the user is mashing keys concurrently.* |

> [!IMPORTANT]
> **Antivirus False Positives:** Because this tool uses external screen capture (`mss`) and keystroke simulation (`pynput`), Windows Defender may flag the `.exe` as a false positive. This is a standard behavior for all Python automation tools. The code is 100% open-source for verification.

---

## 📑 Table of Contents

**👤 For General Users**
1. [Quick Start (Download & Play)](#quick-start)
2. [First-Time Setup & Calibration](#first-time-setup)
3. [User Guide](#user-guide)

**💻 For Developers**
4. [Build from Source](#build-from-source)
5. [Creating an Optimized Executable](#creating-an-optimized-executable)

**📚 Reference**
6. [Why use this tool instead of other bots?](#why-use-this-tool)
7. [Architecture & Design](#architecture--design)
8. [A Note on the Project’s Origins and Philosophy](#philosophy)

---

## 👤 For General Users

<a id="quick-start"></a>
### 1. Quick Start (Download & Play)
1. Go to the [Releases](https://github.com/pengkenlim/MushroomGameHelper/releases) page.
2. Download the latest `MushroomGameHelper_vX.X.X.zip`.
3. Extract the folder to your Desktop (do not run it from inside the `.zip`).
4. *(Optional but recommended)* Add the folder to your Windows Defender exclusions if flagged.
5. Double-click `MushroomGameHelper.exe`.

<a id="first-time-setup"></a>
### 2. First-Time Setup
1. On first launch, the tool will guide you to the **Calibrate Bars** tab.
2. Click **Launch Bar Calibrator**. An OpenCV window will appear.
3. Drag a box around your HP bar, click a "Full" pixel, then click an "Empty" pixel. Repeat for MP.
4. Return to the **Dashboard**, set your desired thresholds, and click **Start**.

<a id="user-guide"></a>
### 3. User Guide
*Coming soon...*  
*(Detailed step-by-step instructions, screenshots, and advanced configuration tips will be added here.)*

---

<a id="why-use-this-tool"></a>
## 🤔 Why use this tool instead of other bots?

If you've looked into Mushroom game automation before, you've probably seen other tools. Here is how MushroomGameHelper is different.

*   **External-Only (Safer):** It never reads game memory or injects DLLs. It simply watches your monitor and presses keys on your OS, making it indistinguishable (in theory) from a hardware macro keyboard.
*   **Visual Calibration:** No more taking screenshots to find hex codes. The interactive OpenCV GUI lets you just drag a box around your bars and click to calibrate.
*   **Dynamic & Robust:** Built-in dynamic window tracking and temporal median filters mean the bot won't break if you move your game window or if the UI flashes. 
*   **Game-Agnostic:** It doesn't contain a single line of game-specific code. It's a generic 2D side-scroller framework that happens to work on a mushroom game.
*   **Free & Open Source:** Some tools charge for similar functionality, but MushroomGameHelper is completely free. The entire project is freely available and open source, allowing anyone to inspect, modify, and contribute. 
*   **Terms of Service Compliant:** MushroomGameHelper operates entirely externally and does not modify the game client, helping you stay within the game's terms of service. MushroomGameHelper does not fully-automate key gameplay loop actions such as combat or questing.

---

## 💻 For Developers

<a id="build-from-source"></a>
### 4. Build from Source
To run or modify the tool directly from the Python script:

1. **Prerequisites:** Install [Python 3.10+](https://www.python.org/downloads/). Ensure "Add Python to PATH" is checked during installation.
2. **Clone the repository:**
   ```bash
   git clone https://github.com/pengkenlim/MushroomGameHelper.git
   cd MushroomGameHelper
   ```
3. **Create a virtual environment (Recommended):**
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```
4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
5. **Run the application:**
   ```bash
   python main.py --gui
   ```

<a id="creating-an-optimized-executable"></a>
### 5. Creating an Optimized Executable
To build a lightweight, standalone `.exe` (requires `upx.exe` in the project root for compression):

```bash
pyinstaller --name MushroomGameHelper --noconsole --clean --upx-dir=. --icon="visual_assets\green_blob.ico" --hidden-import=pynput.keyboard._win32 --hidden-import=pynput.mouse._win32 --exclude-module matplotlib --exclude-module scipy --exclude-module pandas --exclude-module PIL --exclude-module setuptools --exclude-module pkg_resources --exclude-module distutils --exclude-module pip --exclude-module wheel --exclude-module pytest --exclude-module unittest --exclude-module doctest --add-data "visual_assets;visual_assets" main.py
```
*The resulting optimized folder will be located in `dist/MushroomGameHelper`.*

---

## 📚 Reference

<a id="architecture--design"></a>
### 6. Architecture & Design
The tool operates on a multi-threaded, lock-protected architecture to ensure the GUI never freezes and input is handled safely:
* **Vision Thread (`mss` + `OpenCV`):** Captures the screen at ~4 FPS, applies HSV thresholding to the calibrated ROI, and uses a temporal median filter to ignore UI flashes.
* **Scheduler Thread:** Tracks `perf_counter` to determine when timed buffs are due.
* **Action Thread (`pynput`):** The *only* thread that interacts with the keyboard. It handles cooldowns, context-aware looting holds/releases, and buff double-taps.
* **Input Contention Guard:** Monitors physical key presses. If the user exceeds a threshold of held keys, low-priority bot actions (like buffs) are deferred to prevent game engine input buffer overflow.

<a id="philosophy"></a>
### 7. A Note on the Project’s Origins and Philosophy
Hello everyone! I would like to dabble in software engineering as a hobby, but am woefully inexperienced. As such, I built this project primarily as a personal learning exercise and a portfolio piece. To tackle complex topics like multi-threaded architecture and computer vision, I’ve been experimenting with using AI as a pair-programming tutor to help scaffold the initial framework. My goal isn't just to ship a tool, but to iteratively refine, debug, and deeply understand every line of code so I can grow from relying on AI assistance to mastering the underlying software engineering principles myself. I’ve always loved 2D pixelated side-scrollers (a classic version of a mushroom game in particular), and I’m sharing this publicly to learn from this amazing community, catch bugs I couldn't find alone, and hopefully help a few people along the way.

As I developed the tool, I wanted to make sure it respected the spirit of the game(s) we love. Here are a few thoughts on why I built it and how I hope it gets used:

**Preserving the Core Gameplay**
I have immense respect for game design and the effort required to progress. This tool was never meant to play the game *for* you or allow for AFK farming. The core joy of the game—exploring, hunting, and strategizing—still requires your active attention. The goal for this tool is simply to act as a digital assistant for the repetitive micro-management (like watching timers and tapping loot), so players can enjoy the games without it being too much a grind.

**A Humble Accessibility Aid**
During my own long grinding sessions, I noticed my hands getting fatigued and my focus draining from constantly tracking multiple overlapping buff timers and health bars. I realized that this heavy cognitive and motor load can be a genuine barrier to entry, especially for players dealing with repetitive strain, motor challenges, or attention difficulties. I hope this tool can serve as a gentle accessibility bridge, allowing more people to comfortably enjoy the end-game content they love without physical burnout.

**Bridging the Free-to-Play Gap**
In many MMOs, built-in quality-of-life features like auto-looting and auto-buffing are often tied to in-game cash purchases (e.g., premium cash-shop pets in a certain classic mushroom game). As a money-tight and a Free-to-Play (F2P) player, I couldn't always justify those purchases, but I still wanted to enjoy the game comfortably without my hands hurting. I built this as a free, open-source alternative to help bridge that gap for the F2P community. That said, I deeply respect the developers who keep the servers running, and I always encourage supporting them through cosmetics and other official channels!

**A Generic Technical Framework**
From a technical standpoint, the code itself contains no references, memory-reading hooks, or IP-specific data for any particular game. It is entirely blind to what you are playing; it simply watches a configurable rectangle of pixels on your monitor and simulates keystrokes based on the colors it sees. 

Thank you for checking out my project. Whether you use it to save your hands, fork it to learn from the code, or just pass by, I appreciate you taking the time to read this. Please use it responsibly, take care of your health, and happy hunting! 🍄

PS: consider leaving a star on this repo⭐ It gives me a gauge of general interest from the community and keeps me motivated!

> [!NOTE]
> **A Quick Note on the Current State (and a Small Apology!)**
> Because this is an active, solo student learning project, the UI and user experience are still very much a "Work in Progress." You will likely encounter some UI/UX jankiness, unpolished menus, or the occasional bug. I sincerely apologize in advance for these rough edges! I am iteratively refining the tool and learning as I go. If you run into a bug or find a workflow that feels clunky, please open an Issue. Your feedback is genuinely the best way for me to learn what needs polishing next.

---

<div align="center">
  <sub>Built with ❤️ and a lot of OpenCV debugging.</sub>
</div>
