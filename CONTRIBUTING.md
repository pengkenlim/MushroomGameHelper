# Contributing to MushroomGameHelper

Thank you for your interest in improving this project! As this is a passion project, I have specific guidelines for what kinds of contributions I can accept at this time.

## What I Am Currently Accepting
*   **Documentation:** Typos, clarifications, and translations for the `README.md`.
*   **UI/UX Polish:** Minor CSS/Tkinter tweaks, color adjustments, or layout fixes.
*   **Bug Fixes:** Fixes for documented issues in the "Troubleshooting Matrix", provided they do not rewrite core architecture.
*   **Cross-Platform Support:** Improvements for macOS or Linux compatibility (e.g., better `pygetwindow` fallbacks).

## What I Am NOT Accepting (Please Do Not Submit)
*   **New Major Features:** I am currently writing all core feature logic myself for portfolio and learning purposes.
*   **AFK / Auto-Combat / Auto-Pathing:** This project strictly adheres to a "Quality of Life" philosophy. Any code that allows the user to walk away from the keyboard or automates combat decisions will be immediately closed.
*   **Memory Reading / Packet Injection:** This project relies exclusively on external Computer Vision (screen reading) and OS-level keystroke simulation. PRs attempting to read game memory or inject network packets will be closed to ensure the tool remains generic and safe.

## How to Submit a PR
1. Open an Issue first to discuss your proposed bug fix or UI tweak.
2. Keep PRs small and focused on a single issue.
3. Ensure your code passes `flake8` linting.
4. Provide a detailed description of your changes and how to test them.

Thank you for helping keep this project safe and accessible!