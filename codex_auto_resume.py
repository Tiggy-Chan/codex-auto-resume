#!/usr/bin/env python3
"""
codex-auto-resume: Automated Background Supervisor for OpenAI Codex App
Copyright (c) 2026 Tiggy Chan. Released under the MIT License.

Seamlessly monitors long-running Codex Goal sessions, detects usage limits and
server reset timestamps (including unannounced Tibo quota refills), and natively
resumes goals via direct app-server control socket or macOS Accessibility.
100% silent, zero window popups, zero wallpaper clicks, zero chat message pollution.
"""

import os
import sys
import time
import json
import glob
import sqlite3
import datetime
import argparse
import subprocess
import re
import socket
import struct
import base64
from pathlib import Path

DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_CHATGPT_APP = Path("/Applications/ChatGPT.app")
DEFAULT_CODEX_CLI = DEFAULT_CHATGPT_APP / "Contents/Resources/codex-cli/bin/codex"

APPLESCRIPT_CLICK = """
tell application "System Events"
    tell process "ChatGPT"
        if (count of windows) is 0 then return "NO_WINDOW"
        -- Search the live accessibility tree instead of using a stale hierarchy.
        repeat with itemRef in (entire contents of window 1)
            try
                set elem to contents of itemRef
                if (role of elem as text) is "AXButton" then
                    set n to name of elem as text
                    set d to description of elem as text
                    if n is "恢复目标" or d is "恢复目标" or n is "Resume goal" or d is "Resume goal" then
                        perform action "AXPress" of elem
                        return "SUCCESS_AXPRESS"
                    end if
                end if
            end try
        end repeat
        return "BUTTON_NOT_FOUND"
    end tell
end tell
"""

class CodexAutoResume:
    def __init__(self, thread_id=None, codex_home=None, log_file=None, interval=45, probe_interval=180):
        self.codex_home = Path(codex_home) if codex_home else DEFAULT_CODEX_HOME
        self.goals_db = self.codex_home / "goals_1.sqlite"
        self.control_sock = self.codex_home / "app-server-control" / "app-server-control.sock"
        self.thread_id = thread_id
        self.log_file = log_file
        self.interval = interval
        self.probe_interval = probe_interval
        self.codex_bin = self._find_codex_bin()
        self.last_probe_ts = 0

    def _find_codex_bin(self):
        if DEFAULT_CODEX_CLI.exists():
            return str(DEFAULT_CODEX_CLI)
        which_codex = subprocess.run(["which", "codex"], capture_output=True, text=True).stdout.strip()
        if which_codex:
            return which_codex
        return "codex"

    def log(self, message):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{now_str}] {message}"
        print(line, flush=True)
        if self.log_file:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as e:
                print(f"Log write error: {e}", file=sys.stderr)

    def auto_detect_thread_id(self):
        if not self.goals_db.exists():
            return None
        try:
            conn = sqlite3.connect(self.goals_db)
            cur = conn.cursor()
            cur.execute("SELECT thread_id FROM thread_goals ORDER BY updated_at_ms DESC LIMIT 1")
            row = cur.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception as e:
            self.log(f"Auto-detect thread error: {e}")
            return None

    def get_goal_status(self):
        if not self.thread_id:
            self.thread_id = self.auto_detect_thread_id()
        if not self.thread_id or not self.goals_db.exists():
            return None
        try:
            conn = sqlite3.connect(self.goals_db)
            cur = conn.cursor()
            cur.execute(
                "SELECT status, tokens_used, time_used_seconds, updated_at_ms FROM thread_goals WHERE thread_id = ?",
                (self.thread_id,)
            )
            row = cur.fetchone()
            conn.close()
            if row:
                return {
                    "thread_id": self.thread_id,
                    "status": row[0],
                    "tokens_used": row[1],
                    "time_used_seconds": row[2],
                    "updated_at": datetime.datetime.fromtimestamp(row[3] / 1000).strftime("%Y-%m-%d %H:%M:%S")
                }
            return None
        except Exception as e:
            self.log(f"Database error: {e}")
            return None

    def get_latest_resets_at(self):
        if not self.thread_id:
            return None
        pattern = str(self.codex_home / "sessions" / "**" / f"rollout-*-{self.thread_id}.jsonl*")
        matches = glob.glob(pattern, recursive=True)
        if not matches:
            return None
        latest_file = max(matches, key=os.path.getmtime)
        try:
            with open(latest_file, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                buf_size = min(size, 300000)
                f.seek(size - buf_size)
                lines = f.readlines()
                for line in reversed(lines):
                    try:
                        data = json.loads(line)
                        rl = data.get("payload", {}).get("rate_limits", {})
                        primary = rl.get("primary")
                        if primary and primary.get("resets_at"):
                            return primary["resets_at"]
                    except:
                        continue
        except Exception as e:
            self.log(f"Rollout parse error: {e}")
        return None

    def probe_quota_headless(self):
        """Silently queries OpenAI backend to detect unannounced Tibo quota refills (0 GUI)."""
        cmd = [
            self.codex_bin, "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--color", "never",
            "ping"
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
            output = proc.stdout + proc.stderr
            is_limited = ("usage limit" in output.lower()) or ("已达到使用上限" in output)
            match = re.search(r"try again at ([0-9:]+\s*[APMapm]*)", output)
            reset_str = match.group(1) if match else None
            return {
                "is_limited": is_limited,
                "reset_str": reset_str
            }
        except Exception as e:
            return {"error": str(e), "is_limited": True}

    def _make_ws_frame(self, payload: bytes, opcode=1):
        frame = bytearray()
        frame.append(0x80 | (opcode & 0x0f))
        mask_key = os.urandom(4)
        length = len(payload)
        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack("!Q", length))
        frame.extend(mask_key)
        masked = bytearray(payload)
        for i in range(len(masked)):
            masked[i] ^= mask_key[i % 4]
        frame.extend(masked)
        return bytes(frame)

    def _read_ws_frame(self, s):
        hdr = s.recv(2)
        if not hdr: return None
        b1, b2 = hdr[0], hdr[1]
        opcode = b1 & 0x0f
        masked = bool(b2 & 0x80)
        payload_len = b2 & 0x7f
        if payload_len == 126:
            payload_len = struct.unpack("!H", s.recv(2))[0]
        elif payload_len == 127:
            payload_len = struct.unpack("!Q", s.recv(8))[0]
        mask_key = s.recv(4) if masked else None
        data = bytearray()
        while len(data) < payload_len:
            chunk = s.recv(min(4096, payload_len - len(data)))
            if not chunk: break
            data.extend(chunk)
        if masked:
            for i in range(len(data)):
                data[i] ^= mask_key[i % 4]
        if opcode == 9:  # WebSocket ping
            s.sendall(self._make_ws_frame(bytes(data), opcode=10))
            return self._read_ws_frame(s)
        if opcode == 8:
            return None
        return bytes(data)

    def resume_goal_via_socket(self):
        """Primary method: Direct JSON-RPC thread/goal/set via control socket. 100% headless."""
        if not self.control_sock.exists():
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect(str(self.control_sock))
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            handshake = (
                f"GET / HTTP/1.1\r\n"
                f"Host: localhost\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n\r\n"
            )
            s.sendall(handshake.encode("utf-8"))
            resp = s.recv(4096)
            if b"101 Switching Protocols" not in resp:
                s.close()
                return False

            # initialize
            s.sendall(self._make_ws_frame(json.dumps({
                "id": "1", "method": "initialize", "params": {"clientInfo": {"name": "codex-auto-resume", "version": "1.0.0"}}
            }).encode("utf-8")))
            s.sendall(self._make_ws_frame(json.dumps({"method": "initialized"}).encode("utf-8")))

            # This is the exact server request issued by the UI's Resume goal callback.
            # The app server creates the goal-triggered continuation itself when quota allows;
            # do not send a synthetic turn/start or a user message here.
            s.sendall(self._make_ws_frame(json.dumps({
                "id": "2", "method": "thread/goal/set", "params": {"threadId": self.thread_id, "status": "active"}
            }).encode("utf-8")))

            for _ in range(10):
                raw = self._read_ws_frame(s)
                if not raw: break
                msg = json.loads(raw.decode("utf-8"))
                if msg.get("id") == "2":
                    s.close()
                    if "result" in msg:
                        self.log("App-server accepted the same thread/goal/set request used by Resume goal.")
                        return True
                    self.log(f"Resume goal request rejected: {msg.get('error', msg)}")
                    return False
            s.close()
            return False
        except Exception as e:
            self.log(f"Socket resume attempt notice: {e}")
            return False

    def click_resume_goal(self):
        """Resume goal action: Tries direct socket first, then native Accessibility UI click as fallback."""
        if self.resume_goal_via_socket():
            return True

        # Fallback to AppleScript UI accessibility
        try:
            res = subprocess.run(["osascript", "-e", APPLESCRIPT_CLICK], capture_output=True, text=True)
            out = res.stdout.strip()
            if "SUCCESS" in out:
                self.log(f"Successfully triggered '恢复目标' via Accessibility fallback ({out}).")
                return True
            else:
                self.log(f"Click notice: {out}")
                return False
        except Exception as e:
            self.log(f"Click execution error: {e}")
            return False

    def inspect_status(self):
        status_info = self.get_goal_status()
        resets_at = self.get_latest_resets_at()
        now_ts = int(time.time())
        rem = max(0, resets_at - now_ts) if resets_at else None
        return {
            "thread_id": self.thread_id,
            "goal_status": status_info,
            "resets_at": resets_at,
            "resets_at_str": datetime.datetime.fromtimestamp(resets_at).strftime("%Y-%m-%d %H:%M:%S") if resets_at else None,
            "remaining_seconds": rem
        }

    def run_supervisor(self):
        if not self.thread_id:
            self.thread_id = self.auto_detect_thread_id()
        if not self.thread_id:
            self.log("Error: No active Codex thread with a goal detected. Specify one with --thread-id.")
            sys.exit(1)

        self.log("=" * 60)
        self.log("Codex Auto-Resume Supervisor Active (24/7 Silent Mode)")
        self.log(f"Thread ID: {self.thread_id}")
        self.log(f"Polling Interval: {self.interval}s | Tibo Probe Interval: {self.probe_interval}s")
        self.log("=" * 60)

        iteration = 0
        while True:
            iteration += 1
            now_ts = int(time.time())
            info = self.get_goal_status()

            if not info:
                self.log("Waiting: Target thread goal not found in DB. Retrying...")
                time.sleep(self.interval)
                continue

            status = info["status"]
            tokens = info["tokens_used"]
            time_used = info["time_used_seconds"]

            # A goal marked active can still be idle after the previous turn failed on quota.
            # Keep probing the live backend so a stale local active flag cannot suppress resume.
            resets_at = self.get_latest_resets_at()
            remaining = (resets_at - now_ts) if resets_at else 999999

            if status == "active" and remaining > 5:
                if iteration % 4 == 1:
                    self.log(f"[ACTIVE] Goal is coding actively. Tokens: {tokens:,}, Time: {time_used}s. Silent monitoring...")
                time.sleep(self.interval)
                continue

            # A goal marked active with an expired reset timestamp is stale; test the backend.
            if status == "active":
                self.log("[STALE ACTIVE] Goal is marked active but its quota window has expired; probing before resuming.")

            # Goal is usage_limited, paused, or stale-active after a reset.
            # A. Scheduled reset time reached
            if resets_at and remaining <= 5:
                reset_str = datetime.datetime.fromtimestamp(resets_at).strftime("%Y-%m-%d %H:%M:%S")
                self.log(f"[TIME REACHED] Scheduled reset time reached ({reset_str})! Triggering resume...")
                self.click_resume_goal()
                time.sleep(15)
                continue

            # B. Check for unannounced Tibo quota refills
            if (now_ts - self.last_probe_ts) >= self.probe_interval:
                self.last_probe_ts = now_ts
                self.log("[TIBO PROBE] Checking OpenAI backend headlessly for early quota reset...")
                probe_res = self.probe_quota_headless()
                if not probe_res.get("is_limited"):
                    self.log("[TIBO REFILL] Early quota detected available on OpenAI backend! Triggering resume...")
                    self.click_resume_goal()
                    time.sleep(15)
                    continue
                else:
                    srv_str = probe_res.get("reset_str") or "unknown"
                    self.log(f"[TIBO PROBE] Quota currently not available. Server confirms reset at: {srv_str}.")

            # Heartbeat countdown
            if iteration % 2 == 1:
                hours = int(remaining // 3600)
                mins = int((remaining % 3600) // 60)
                secs = int(remaining % 60)
                time_fmt = f"{hours}h {mins}m {secs}s" if remaining > 0 else "0s"
                t_str = datetime.datetime.fromtimestamp(resets_at).strftime("%Y-%m-%d %H:%M:%S") if resets_at else "unknown"
                self.log(f"[{status.upper()}] Next scheduled reset: {t_str} (in {time_fmt}). Silently watching...")

            time.sleep(self.interval)

def main():
    parser = argparse.ArgumentParser(
        description="codex-auto-resume: Automated silent background supervisor for OpenAI Codex App"
    )
    parser.add_argument("-t", "--thread-id", help="Codex thread UUID to monitor (auto-detected if omitted)")
    parser.add_argument("-i", "--interval", type=int, default=45, help="Status polling interval in seconds (default: 45)")
    parser.add_argument("-p", "--probe-interval", type=int, default=180, help="Tibo quota probe interval in seconds (default: 180)")
    parser.add_argument("-l", "--log", help="Path to log file (default: stdout only)")
    parser.add_argument("--status", action="store_true", help="Print current goal status and quota state as JSON, then exit")
    parser.add_argument("--click-only", action="store_true", help="Perform native resume action once immediately, then exit")
    args = parser.parse_args()

    supervisor = CodexAutoResume(
        thread_id=args.thread_id,
        log_file=args.log,
        interval=args.interval,
        probe_interval=args.probe_interval
    )

    if args.status:
        print(json.dumps(supervisor.inspect_status(), indent=2, ensure_ascii=False))
        return

    if args.click_only:
        supervisor.click_resume_goal()
        return

    supervisor.run_supervisor()

if __name__ == "__main__":
    main()
