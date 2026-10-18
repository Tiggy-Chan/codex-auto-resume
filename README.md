# codex-auto-resume

> 🤖 Automated 24/7 background supervisor for the **OpenAI Codex Desktop App**. Seamlessly auto-resumes paused or usage-limited thread goals upon 5-hour quota resets or unannounced Tibo quota refills. 100% silent, zero window popups, zero chat history pollution.

---

[中文说明](#中文说明) | [English](#overview)

---

## Overview

When running long-horizon autonomous tasks in the **OpenAI Codex App** using **Goals**, sessions inevitably pause when the account's 5-hour rolling usage limit is exhausted.

While OpenAI occasionally grants unannounced early quota resets (known in the community as "Tibo refills"), developers typically have to either:
1. Manually check the app and click the **"Resume goal" (恢复目标)** button.
2. Send a dummy prompt via CLI (`codex queue --message`), which pollutes the thread context and adds noisy chat bubbles.
3. Run clumsy mouse-click macros that steal window focus or accidentally click desktop wallpaper (causing macOS to slide all windows away into Stage Manager / Mission Control).

**`codex-auto-resume`** solves this cleanly:
- **100% Silent & Non-intrusive**: Uses macOS native Accessibility APIs (`System Events`) to trigger the exact underlying UI button directly. Zero mouse pointer movement, zero window focus stealing, zero wallpaper misclicks.
- **Tibo Early Reset Sensing**: In addition to tracking the official 5-hour reset timestamp, it silently queries OpenAI backend headlessly every few minutes. If quota is refilled early, it immediately triggers the resume button.
- **Zero Chat History Pollution**: Triggers the native `thread/goal/set` lifecycle without sending dummy user messages.
- **Zero Heavy Dependencies**: Written entirely in pure Python standard library + macOS built-in tools. No `pip install` required.

---

## Features

- 🕒 **Rolling 5-Hour Reset Tracking**: Reads local session metadata to know the exact second quota becomes available.
- ⚡ **Tibo Early Refill Detector**: Headlessly probes backend limits in the background to catch mid-window quota gifts.
- 🎯 **Auto Thread Detection**: Automatically targets the most recently active thread with a goal, or accepts an explicit `--thread-id`.
- 🔕 **True Background Execution**: Runs unobtrusively in terminal or as a `nohup` daemon while you work or sleep.

---

## Quick Start

### Prerequisites
- macOS 12+ (tested on macOS 14 Sonoma, 15 Sequoia, and 26+)
- Python 3.8+ (macOS system Python works out of the box)
- Accessibility permission for your Terminal app (System Settings → Privacy & Security → Accessibility)

### Usage

```bash
# 1. Clone the repository
git clone https://github.com/Tiggy-Chan/codex-auto-resume.git
cd codex-auto-resume

# 2. Check current thread goal status
./codex_auto_resume.py --status

# 3. Start the supervisor (auto-detects the active thread goal)
./codex_auto_resume.py

# 4. Or run as a continuous background daemon
nohup ./codex_auto_resume.py --log codex_auto_resume.log > /dev/null 2>&1 &
```

### CLI Arguments

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-t, --thread-id` | Codex thread UUID to monitor | *Auto-detected latest* |
| `-i, --interval` | Status check interval (seconds) | `45` |
| `-p, --probe-interval` | Headless quota probe interval (seconds) | `180` (3 mins) |
| `-l, --log` | Path to log file | *stdout only* |
| `--status` | Output goal & quota diagnostics in JSON, then exit | - |
| `--click-only` | Trigger native resume click once, then exit | - |

---

<a name="中文说明"></a>
## 中文说明

在 **OpenAI Codex Desktop App** 中运行多阶段长时自主任务（Goals）时，往往会因 5 小时的滑动额度用尽而进入 `usage_limited` 暂停状态。

除固定的 5 小时重置外，OpenAI 负责人（如社区熟知的 Tibo）经常会突发向用户发放额度重置补偿。以往开发者要么需要人工定时守候点击卡片上的**“恢复目标”**按钮，要么使用命令发送消息（产生多余的用户聊天气泡污染上下文），或者使用模拟鼠标点击造成前端窗口缩进。

**`codex-auto-resume`** 是专为解决此痛点设计的全自动后台守护工具：
- **纯原生无感恢复**：通过 macOS 辅助功能树（Accessibility API）底层精准触发“恢复目标”，不抢占鼠标、不强弹窗口、不误触壁纸。
- **智能探测 Tibo 提前放水**：除对齐 5 小时时间戳外，每隔几分钟在后台无头静默探针向 OpenAI 网关校验；一旦提前解封，秒级唤醒接续。
- **绝不污染上下文**：走官方原生的目标轮次机制，会话历史里 0 垃圾气泡。
- **零外部安装依赖**：完全基于 Python 标准库与 macOS 原生工具开发，开箱即用。

---

## License

[MIT License](LICENSE) © 2026 Tiggy Chan.
