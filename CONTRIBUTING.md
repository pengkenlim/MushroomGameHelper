# 🤝 Contributing to MushroomGameHelper

Thank you for your interest in improving MushroomGameHelper! Because this is an active student portfolio project focused on learning robust software engineering principles, I have specific guidelines regarding community contributions.

## ✅ What I Am Looking For
I highly welcome contributions in the following areas:
* **Documentation:** Fixes to typos, clarifications, translations, or improving the README/CONTRIBUTING guides.
* **UI/UX Polish:** Minor Tkinter layout tweaks, color adjustments, tooltip additions, or improving the "sketch-style" visual assets.
* **Bug Fixes:** Solutions for documented issues in the Troubleshooting Matrix or edge-case handling.
* **Cross-Platform Support:** Improvements or workarounds for macOS or Linux compatibility.

## 🚫 What I Am Not Accepting (For Now)
To keep the core architecture intact and aligned with the project's learning goals, I am currently **not** accepting:
* Memory-reading implementations or DLL injection logic.
* AFK / Auto-combat / Auto-pathing logic (violates the project's accessibility-first philosophy).
* Major architectural rewrites that replace the current multi-threaded `SharedState` model.

## 🛠️ How to Contribute

1. **Fork the Repository:** Create your own fork of the project.
2. **Create a Branch:** Use a descriptive branch name (e.g., `fix/osd-alignment` or `docs/update-readme`).
3. **Make Your Changes:** Keep your commits focused and atomic. Follow [Conventional Commits](https://www.conventionalcommits.org/) if possible (e.g., `fix: center key capture dialog`).
4. **Test Locally:** Ensure your changes do not break the core loop, the calibrator, or the optimized PyInstaller build.
5. **Open a Pull Request:** Provide a clear description of *what* you changed and *why*. Link to any relevant issues.

## 💬 Before You Start
If you are planning a larger change (even within the accepted categories), please **open an Issue first** to discuss your idea. This ensures we are aligned on the project's direction and saves you from doing work that might not be merged.

Thank you for helping make this tool better for the community! 🍄