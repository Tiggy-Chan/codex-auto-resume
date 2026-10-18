<p align="right">
  <b>English</b> | <a href="README_zh.md">简体中文</a>
</p>

# codex-auto-resume

> 🤖 Automated 24/7 background supervisor for the **OpenAI Codex Desktop App**. Seamlessly auto-resumes paused or usage-limited thread goals upon 5-hour quota resets or unannounced Tibo quota refills. 100% silent, zero window popups, zero chat history pollution.

---

## The Problem

When running long-horizon autonomous engineering tasks in the **OpenAI Codex App** using **Goals**, sessions inevitably pause when the account's 5-hour rolling usage limit is reached.

Furthermore, OpenAI leaders (notably Tibo on X/Twitter) frequently grant unannounced early quota refills or reset waves to users. Developers typically face three imperfect options:
1. **Manual Watching**: Periodically checking the app to click the **"Resume goal" (恢复目标)** button.
2. **Dummy Prompts (`codex queue --message`)**: Injects artificial user chat bubbles that pollute the conversation context and prompt history.
3. **Crude Mouse Macros**: Scripts that simulate mouse clicks across screens often steal focus or accidentally click desktop wallpaper (triggering macOS to slide all active windows away into Stage Manager / Mission Control).

## The Solution

**`codex-auto-resume`** is a dedicated background supervisor designed to automate goal continuation cleanly:

- **100% Silent & Non-Intrusive**: Interacts directly with the underlying button element via native macOS Accessibility (`System Events`). Zero mouse cursor displacement, zero window activation/popups, and zero wallpaper misclicks.
- **Tibo Early Reset Sensing**: In addition to tracking official 5-hour reset timestamps, it headlessly probes OpenAI's backend every few minutes. The moment an unannounced refill happens, the goal is resumed instantly.
- **Zero Chat Context Pollution**: Uses the native `thread/goal/set` UI transition, generating zero artificial user messages.
- **Zero Dependencies**: Built entirely with Python's standard library and macOS built-in tools. No `pip install` required.

---

## Features

- 🕒 **5-Hour Rolling Window Tracking**: Automatically parses local session metadata to determine the exact second quota restores.
- ⚡ **Tibo Early Refill Detection**: Periodically probes backend quota headlessly in the background to catch mid-window quota gifts.
- 🎯 **Automatic Thread Detection**: Automatically targets the latest active thread goal, or accepts a specific `--thread-id`.
- 🔕 **True Background Daemon**: Runs unobtrusively in your terminal or as a `nohup` daemon while you work or sleep.

---

## Prerequisites

- **macOS 12+** (tested on macOS 14 Sonoma, 15 Sequoia, and 26+)
- **Python 3.8+** (macOS built-in Python works out of the box)
- **Accessibility Permission**: Granted to your Terminal or IDE app (System Settings → Privacy & Security → Accessibility)

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Tiggy-Chan/codex-auto-resume.git
cd codex-auto-resume

# 2. Check current thread goal status & quota diagnostics (JSON output)
./codex_auto_resume.py --status

# 3. Start the supervisor (auto-detects the active thread goal)
./codex_auto_resume.py

# 4. Or run as a continuous background daemon
nohup ./codex_auto_resume.py --log ~/.codex/codex_auto_resume.log > /dev/null 2>&1 &
```

---

## CLI Options

| Option | Description | Default |
| :--- | :--- | :--- |
| `-t, --thread-id` | Specific Codex thread UUID to monitor | *Auto-detected latest* |
| `-i, --interval` | Status polling interval in seconds | `45` |
| `-p, --probe-interval` | Headless quota probe interval in seconds | `180` (3 minutes) |
| `-l, --log` | Path to log file | *stdout only* |
| `--status` | Print goal status, reset timestamps, and quota diagnostics as JSON, then exit | - |
| `--click-only` | Trigger the native resume goal click immediately, then exit | - |

---

## License

Released under the [MIT License](LICENSE). Copyright © 2026 Tiggy Chan.
