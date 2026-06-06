import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import asyncio
import logging
import ctypes
import sys
import os
import json
import re

# Resolve base directory whether running as script or PyInstaller exe
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.json")


def _load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_config(data: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _extract_sheet_id(text: str) -> str:
    """Accept a full Google Sheets URL or a bare ID."""
    text = text.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", text)
    return match.group(1) if match else text


class _GUILogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self._cb = callback

    def emit(self, record):
        try:
            self._cb(self.format(record) + "\n", record.levelname.lower())
        except Exception:
            pass


class BotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("FHS Bot")
        self.root.geometry("720x580")
        self.root.resizable(False, False)
        self.root.configure(bg="#12121f")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._thread: threading.Thread | None = None
        self._handler: _GUILogHandler | None = None
        self._build_ui()

    # ── UI layout ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#1c1c30", pady=12)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="FHS Bot",
            font=("Segoe UI", 20, "bold"),
            bg="#1c1c30", fg="#ffffff",
        ).pack(side=tk.LEFT, padx=20)

        self._dot = tk.Label(
            header, text="●", font=("Segoe UI", 16),
            bg="#1c1c30", fg="#e74c3c",
        )
        self._dot.pack(side=tk.RIGHT, padx=6)

        self._status = tk.Label(
            header, text="Stopped",
            font=("Segoe UI", 11),
            bg="#1c1c30", fg="#888888",
        )
        self._status.pack(side=tk.RIGHT)

        # Sheet settings row
        sheet_frame = tk.Frame(self.root, bg="#1a1a2e", pady=8, padx=14)
        sheet_frame.pack(fill=tk.X)

        tk.Label(
            sheet_frame, text="Google Sheet:",
            font=("Segoe UI", 10),
            bg="#1a1a2e", fg="#aaaaaa",
        ).pack(side=tk.LEFT)

        self._sheet_var = tk.StringVar()
        cfg = _load_config()
        self._sheet_var.set(cfg.get("spreadsheet_id", ""))

        sheet_entry = tk.Entry(
            sheet_frame,
            textvariable=self._sheet_var,
            font=("Consolas", 9),
            bg="#0d0d1a", fg="#d4d4d4",
            insertbackground="white",
            relief=tk.FLAT,
            bd=4,
            width=52,
        )
        sheet_entry.pack(side=tk.LEFT, padx=(8, 6))

        tk.Button(
            sheet_frame, text="Save",
            font=("Segoe UI", 9, "bold"),
            bg="#2980b9", fg="white",
            activebackground="#3498db", activeforeground="white",
            relief=tk.FLAT, padx=12, pady=4,
            cursor="hand2", command=self._save_sheet,
        ).pack(side=tk.LEFT)

        # Log area
        log_frame = tk.Frame(self.root, bg="#12121f", padx=14, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self._log = scrolledtext.ScrolledText(
            log_frame,
            bg="#0d0d1a", fg="#d4d4d4",
            font=("Consolas", 10),
            state=tk.DISABLED,
            relief=tk.FLAT,
            borderwidth=0,
            wrap=tk.WORD,
        )
        self._log.pack(fill=tk.BOTH, expand=True)
        self._log.tag_config("info",    foreground="#6ccb6c")
        self._log.tag_config("error",   foreground="#e74c3c")
        self._log.tag_config("warning", foreground="#f39c12")
        self._log.tag_config("default", foreground="#d4d4d4")

        # Button row
        btn_row = tk.Frame(self.root, bg="#12121f", pady=10, padx=14)
        btn_row.pack(fill=tk.X)

        self._start_btn = tk.Button(
            btn_row, text="▶  Start",
            font=("Segoe UI", 11, "bold"),
            bg="#27ae60", fg="white",
            activebackground="#2ecc71", activeforeground="white",
            relief=tk.FLAT, padx=22, pady=9,
            cursor="hand2", command=self.start_bot,
        )
        self._start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._stop_btn = tk.Button(
            btn_row, text="■  Stop",
            font=("Segoe UI", 11, "bold"),
            bg="#c0392b", fg="white",
            activebackground="#e74c3c", activeforeground="white",
            relief=tk.FLAT, padx=22, pady=9,
            cursor="hand2", command=self.stop_bot,
            state=tk.DISABLED,
        )
        self._stop_btn.pack(side=tk.LEFT)

        tk.Button(
            btn_row, text="Clear",
            font=("Segoe UI", 10),
            bg="#2c2c40", fg="#aaaaaa",
            activebackground="#3a3a55", activeforeground="white",
            relief=tk.FLAT, padx=16, pady=9,
            cursor="hand2", command=self._clear_log,
        ).pack(side=tk.RIGHT)

    # ── Sheet config ──────────────────────────────────────────────────────────

    def _save_sheet(self):
        raw = self._sheet_var.get().strip()
        if not raw:
            messagebox.showwarning("FHS Bot", "Please enter a Google Sheet URL or ID.")
            return
        sheet_id = _extract_sheet_id(raw)
        cfg = _load_config()
        cfg["spreadsheet_id"] = sheet_id
        cfg.setdefault("sheet_name", "Sheet1")
        cfg.setdefault("email_column", 1)
        cfg.setdefault("credentials_file", "config/credentials.json")
        _save_config(cfg)
        self._sheet_var.set(sheet_id)
        self._log_append(f"[Config] Sheet saved: {sheet_id}\n", "info")

    # ── Bot control ───────────────────────────────────────────────────────────

    def start_bot(self):
        if self._thread and self._thread.is_alive():
            return

        if raw:
            sheet_id = _extract_sheet_id(raw)
            cfg = _load_config()
            if cfg.get("spreadsheet_id") != sheet_id:
                cfg["spreadsheet_id"] = sheet_id
                cfg.setdefault("sheet_name", "Sheet1")
                cfg.setdefault("email_column", 1)
                cfg.setdefault("credentials_file", "config/credentials.json")
                _save_config(cfg)

        os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

        self._handler = _GUILogHandler(
            lambda msg, lvl: self.root.after(0, self._log_append, msg, lvl)
        )
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logging.root.setLevel(logging.INFO)
        logging.root.addHandler(self._handler)

        self._log_append("[Bot] Starting...\n", "info")
        self._thread = threading.Thread(target=self._run_bot, daemon=True)
        self._thread.start()
        self._set_running(True)

    def stop_bot(self):
        if self._thread and self._thread.is_alive():
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(self._thread.ident),
                ctypes.py_object(SystemExit),
            )
        self._log_append("[Bot] Stopped by user.\n", "warning")
        self._set_running(False)

    def _run_bot(self):
        try:
            asyncio.run(self._bot_main())
        except (SystemExit, KeyboardInterrupt):
            pass
        except Exception as e:
            self.root.after(0, self._log_append, f"[ERROR] {e}\n", "error")
        finally:
            if self._handler:
                logging.root.removeHandler(self._handler)
            self.root.after(0, self._set_running, False)

    async def _bot_main(self):
        from bot.core import Bot
        bot = Bot()
        await bot.start()

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _set_running(self, running: bool):
        if running:
            self._start_btn.config(state=tk.DISABLED)
            self._stop_btn.config(state=tk.NORMAL)
            self._status.config(text="Running")
            self._dot.config(fg="#2ecc71")
        else:
            self._start_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._status.config(text="Stopped")
            self._dot.config(fg="#e74c3c")

    def _log_append(self, text: str, tag: str = "default"):
        self._log.config(state=tk.NORMAL)
        self._log.insert(tk.END, text, tag)
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)

    def _clear_log(self):
        self._log.config(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.config(state=tk.DISABLED)

    def _on_close(self):
        self.stop_bot()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    BotApp(root)
    root.mainloop()
