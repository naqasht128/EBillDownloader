"""E-Bill Downloader.

High-performance desktop application to automate batch downloading,
A4 auto-formatting, stamping, and merging of utility electricity bills.
Equipped with hardware-locked licensing, auto-updates, and native C++ binary protection.
"""

from __future__ import annotations

import base64
import gc
import hashlib
import json
import os
import platform
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import winreg
except ImportError:
    winreg = None

import requests
from openpyxl import load_workbook

# ──────────────────────────────────────────────────────────────
#  APPLICATION METADATA & CONSTANTS
# ──────────────────────────────────────────────────────────────
APP_NAME = "EBillDownloader"
APP_TITLE = "E-Bill Downloader"
APP_VERSION = "1.0.8"
DEFAULT_URL = "https://bill.pitc.com.pk/pescobill"
LICENSE_API_URL = os.environ.get("LICENSE_API_URL", "https://e-bill-downloader.vercel.app").rstrip("/")
UPDATE_API_URL = f"{LICENSE_API_URL}/api/updates/latest"
SUPPORT_WHATSAPP = "https://wa.me/923339962474"
SUPPORT_EMAIL = "mailto:tahir.naqash4@gmail.com"

# VS Code Dark+ Palette
BG_DARK = "#1e1e1e"
CARD_BG = "#252526"
BORDER_COLOR = "#383838"
TEXT_WHITE = "#ffffff"
TEXT_MAIN = "#cccccc"
TEXT_MUTED = "#8b949e"
ACCENT_GREEN = "#238636"
ACCENT_GREEN_HOVER = "#2ea043"
ACCENT_BLUE = "#007acc"
ACCENT_BLUE_HOVER = "#1f8ad2"
ACCENT_RED = "#d9383a"
ACCENT_RED_HOVER = "#e5484d"
ACCENT_ORANGE = "#ca7000"
ACCENT_ORANGE_HOVER = "#e58200"
INPUT_BG = "#2d2d2d"
BTN_SEC_BG = "#3a3d41"
BTN_SEC_HOVER = "#45494e"
BTN_DISABLED_BG = "#2d2d2d"
BTN_DISABLED_FG = "#555555"

UI_FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO_FONT = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"


def resource_path(relative_path: str) -> str:
    """Resolve bundled resources in source runs, PyInstaller, and Nuitka builds."""
    bundle_root = os.environ.get("NUITKA_ONEFILE_DIRECTORY") or getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return str(Path(bundle_root) / relative_path)


def set_dark_title_bar(window: tk.Tk | tk.Toplevel):
    """Enable native Windows 10/11 immersive dark mode title bar."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnds = []
        try:
            hwnds.append(int(window.wm_frame(), 16))
        except Exception:
            pass
        try:
            parent_h = ctypes.windll.user32.GetParent(window.winfo_id())
            if parent_h:
                hwnds.append(parent_h)
        except Exception:
            pass
        hwnds.append(window.winfo_id())

        value = ctypes.c_int(1)
        for h in set(hwnds):
            if h:
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(h, 20, ctypes.byref(value), ctypes.sizeof(value)) != 0:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(h, 19, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
#  HARDWARE FINGERPRINTING & HARDWARE LOCKING
# ──────────────────────────────────────────────────────────────
_CACHED_DEVICE_ID: str | None = None
_CACHED_CANDIDATE_IDS: list[str] | None = None


def get_device_id() -> str:
    """Returns persistent, unique hardware identifier for this machine."""
    global _CACHED_DEVICE_ID
    if _CACHED_DEVICE_ID:
        return _CACHED_DEVICE_ID
    device_id = _compute_device_id()
    _CACHED_DEVICE_ID = device_id
    return device_id


def _compute_device_id() -> str:
    if sys.platform == "win32":
        # 1. Windows Registry MachineGuid (64-bit and 32-bit views)
        for flag in [getattr(winreg, 'KEY_WOW64_64KEY', 0), getattr(winreg, 'KEY_WOW64_32KEY', 0), 0]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | flag) as key:
                    machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                    if machine_guid and len(str(machine_guid).strip()) > 10:
                        return str(machine_guid).strip().upper()
            except Exception:
                pass

        # 2. Modern PowerShell CIM query for BIOS UUID (Windows 10/11)
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"]
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            output = subprocess.check_output(cmd, creationflags=flags, timeout=5).decode(errors="ignore").strip()
            if '-' in output and len(output) >= 30:
                return output.upper()
        except Exception:
            pass

        # 3. Legacy WMIC query (Windows 7/8)
        try:
            cmd = ["wmic", "csproduct", "get", "uuid"]
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            output = subprocess.check_output(cmd, creationflags=flags, timeout=4).decode(errors="ignore").splitlines()
            for line in output:
                clean_l = line.strip()
                if '-' in clean_l and len(clean_l) >= 30:
                    return clean_l.upper()
        except Exception:
            pass

        # 4. Fallback to physical MAC address
        try:
            mac = uuid.getnode()
            if (mac >> 40) % 2 == 0:
                return f"MAC-{hex(mac)[2:].upper()}"
        except Exception:
            pass

        return "UNKNOWN-HWID-WIN"

    elif sys.platform == "darwin":
        try:
            out = subprocess.check_output(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], stderr=subprocess.DEVNULL, text=True, timeout=3)
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                return m.group(1).strip().upper()
        except Exception:
            pass
    else:
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        val = f.read().strip()
                        if val:
                            return val.upper()
                except Exception:
                    pass

    try:
        mac = uuid.getnode()
        return f"FALLBACK-{hex(mac)[2:].upper()}"
    except Exception:
        return "UNKNOWN-DEVICE-ID"


def get_candidate_device_ids() -> list[str]:
    """Return all valid device IDs for this machine."""
    global _CACHED_CANDIDATE_IDS
    if _CACHED_CANDIDATE_IDS:
        return _CACHED_CANDIDATE_IDS
    primary = get_device_id()
    candidates = [primary]
    _CACHED_CANDIDATE_IDS = candidates
    return candidates


def get_os_info() -> str:
    try:
        return f"{platform.system()} {platform.release()} ({platform.machine()})"
    except Exception:
        return sys.platform


# ──────────────────────────────────────────────────────────────
#  CONFIG & LICENSING LOCAL CACHE
# ──────────────────────────────────────────────────────────────
def get_app_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        app_dir = base / "EBillDownloader"
    else:
        app_dir = Path.home() / ".ebilldownloader"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def load_app_config() -> dict:
    path = get_app_dir() / "config.json"
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_app_config(data: dict):
    path = get_app_dir() / "config.json"
    try:
        existing = load_app_config()
        existing.update(data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass


def load_local_license() -> dict:
    path = get_app_dir() / "license.json"
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_local_license(data: dict):
    path = get_app_dir() / "license.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def verify_license_remote(serial_key: str, device_id: str, candidate_ids: list[str] | None = None) -> dict:
    url = f"{LICENSE_API_URL.rstrip('/')}/api/verify"
    c_ids = candidate_ids or [device_id]
    payload = {
        "serial_key": serial_key.strip().upper(),
        "device_id": device_id,
        "candidate_ids": c_ids,
        "os_info": get_os_info(),
    }
    try:
        resp = requests.post(url, json=payload, timeout=12)
        try:
            data = resp.json()
        except Exception:
            data = {"valid": False, "status": "network_error", "message": f"Server HTTP {resp.status_code}"}
        return data
    except Exception as e:
        return {"valid": False, "status": "network_error", "message": f"Connection error: {e}"}


def activate_license_remote(serial_key: str, device_id: str, candidate_ids: list[str] | None = None) -> dict:
    url = f"{LICENSE_API_URL.rstrip('/')}/api/activate"
    c_ids = candidate_ids or [device_id]
    payload = {
        "serial_key": serial_key.strip().upper(),
        "device_id": device_id,
        "candidate_ids": c_ids,
        "os_info": get_os_info(),
    }
    try:
        resp = requests.post(url, json=payload, timeout=12)
        try:
            return resp.json()
        except Exception:
            return {"valid": False, "status": "network_error", "message": f"Server HTTP {resp.status_code}"}
    except Exception as e:
        return {"valid": False, "status": "network_error", "message": f"Connection error: {e}"}


def format_expiry_date(iso_str: str | None) -> str:
    if not iso_str:
        return "Not Activated"
    try:
        clean_ts = str(iso_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        now = datetime.now(timezone.utc)
        diff = dt - now
        date_str = dt.strftime("%d %b %Y")
        if diff.days > 0:
            return f"{date_str} ({diff.days} days remaining)"
        elif diff.total_seconds() > 0:
            return f"{date_str} (Expires today)"
        else:
            return f"{date_str} (Expired)"
    except Exception:
        return str(iso_str)


def format_plan_label(plan_code: str | None) -> str:
    mapping = {
        "1_month": "1 Month (1 Device)",
        "3_months": "3 Months (Up to 2 Devices)",
        "6_months": "6 Months (Up to 2 Devices)",
        "1_year": "1 Year (Up to 2 Devices)",
    }
    if not plan_code:
        return "Not Activated"
    return mapping.get(str(plan_code).lower(), str(plan_code).replace("_", " ").title())


# ──────────────────────────────────────────────────────────────
#  AUTO-UPDATER SUBSYSTEM
# ──────────────────────────────────────────────────────────────
def parse_version_tuple(v: str) -> tuple[int, ...]:
    nums = [int(n) for n in re.findall(r"\d+", str(v))]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


class UpdateInfo:
    def __init__(self, version: str, download_url: str, file_name: str, file_size: int = 0, release_notes: str = ""):
        self.version = version
        self.download_url = download_url
        self.file_name = file_name
        self.file_size = file_size
        self.release_notes = release_notes


def clean_release_notes(raw_notes: str) -> str:
    """Sanitizes release notes to ensure end-users only see descriptions of what has changed.
    Strictly removes GitHub repository links, comparison links, PR references, and empty headings.
    Returns cleaned description text, or empty string "" if no descriptions exist.
    """
    if not raw_notes or not isinstance(raw_notes, str):
        return ""

    lines = raw_notes.replace("\r\n", "\n").split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip automated GitHub comparison footer lines (e.g. **Full Changelog**: ...)
        if "full changelog" in stripped.lower():
            continue

        # Strip GitHub repository references, PR links, and commit comparisons
        if "github.com" in stripped.lower():
            stripped = re.sub(r"\s*in\s+https?://github\.com\S+", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\[([^\]]+)\]\(https?://github\.com[^\)]*\)", r"\1", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"https?://github\.com\S*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*by\s+@[\w-]+", "", stripped, flags=re.IGNORECASE)
            stripped = stripped.strip()

        # Strip any other raw URLs
        stripped = re.sub(r"https?://\S+", "", stripped).strip()

        # Clean markdown headers like '## What's Changed'
        if stripped.startswith("#"):
            header_text = stripped.lstrip("#").strip()
            if header_text.lower() in ("what's changed", "whats changed", "changelog", "release notes", "updates"):
                continue
            stripped = header_text

        # Skip empty lines or lone bullet marks left after link removal
        if not stripped or stripped in ("*", "-", "•", ":", "- :"):
            continue

        cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines).strip()


def check_for_updates(current_version: str = APP_VERSION) -> UpdateInfo | None:
    # 1. Primary: Query Vercel Licensing & Updates Backend
    try:
        headers = {"User-Agent": "EBillDownloader-DesktopApp", "Accept": "application/json"}
        params = {}
        if sys.platform == "win32":
            try:
                winver = sys.getwindowsversion()
                if winver.major == 6 and winver.minor == 1:
                    params["os"] = "win7"
            except Exception:
                pass
        resp = requests.get(UPDATE_API_URL, headers=headers, params=params, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            target_version = data.get("version", "").strip().lstrip("v")
            download_url = data.get("download_url", "").strip()
            if target_version and download_url:
                if parse_version_tuple(target_version) > parse_version_tuple(current_version):
                    file_name = data.get("file_name", "EBillDownloader-Setup.exe")
                    return UpdateInfo(
                        version=target_version,
                        download_url=download_url,
                        file_name=file_name,
                        file_size=data.get("file_size", 0),
                        release_notes=clean_release_notes(data.get("release_notes", "")),
                    )
    except Exception:
        pass

    # 2. Resilient Direct Fallback: Query GitHub Releases directly (naqasht128/EBillDownloader)
    try:
        gh_url = "https://api.github.com/repos/naqasht128/EBillDownloader/releases/latest"
        gh_resp = requests.get(
            gh_url,
            headers={"User-Agent": "EBillDownloader-DesktopApp", "Accept": "application/vnd.github.v3+json"},
            timeout=8
        )
        if gh_resp.status_code == 200:
            data = gh_resp.json()
            target_version = (data.get("tag_name") or "").strip().lstrip("v")
            if target_version and parse_version_tuple(target_version) > parse_version_tuple(current_version):
                assets = data.get("assets", [])
                is_win7 = False
                if sys.platform == "win32":
                    try:
                        winver = sys.getwindowsversion()
                        if winver.major == 6 and winver.minor == 1:
                            is_win7 = True
                    except Exception:
                        pass

                selected_asset = None
                if is_win7:
                    for a in assets:
                        name = a.get("name", "").lower()
                        if "win7" in name and name.endswith(".exe"):
                            selected_asset = a
                            break
                if not selected_asset:
                    for a in assets:
                        name = a.get("name", "").lower()
                        if "setup" in name and name.endswith(".exe") and "win7" not in name:
                            selected_asset = a
                            break
                if not selected_asset and assets:
                    selected_asset = assets[0]

                if selected_asset:
                    return UpdateInfo(
                        version=target_version,
                        download_url=selected_asset.get("browser_download_url", ""),
                        file_name=selected_asset.get("name", "EBillDownloader-Setup.exe"),
                        file_size=selected_asset.get("size", 0),
                        release_notes=clean_release_notes(data.get("body", "")),
                    )
    except Exception:
        pass

    return None


def install_and_restart(new_file_path: str, root_window: tk.Tk):
    is_frozen = getattr(sys, "frozen", False)
    if not is_frozen:
        msg = (
            f"Update downloaded successfully to:\n{new_file_path}\n\n"
            "Because you are running from Python source code, you can update via 'git pull' "
            "or run the downloaded Setup installer directly."
        )
        messagebox.showinfo("Update Downloaded", msg)
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer.exe", f"/select,{new_file_path}"])
        except Exception:
            pass
        return

    if sys.platform == "win32":
        clean_env = os.environ.copy()
        for k in [k for k in clean_env if k.startswith(('_PYI', '_MEI', 'PYTHON', 'TCL', 'TK'))]:
            clean_env.pop(k, None)

        try:
            DETACHED_FLAGS = 0x08000000 | 0x00000200
            subprocess.Popen(
                [new_file_path, "/SILENT", "/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS", "/AUTOUPDATE=1"],
                creationflags=DETACHED_FLAGS,
                close_fds=True,
                env=clean_env,
            )
        except Exception:
            subprocess.Popen([new_file_path, "/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS", "/AUTOUPDATE=1"], env=clean_env)

        try:
            root_window.destroy()
        except Exception:
            pass
        sys.exit(0)


class UpdateDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, update_info: UpdateInfo):
        super().__init__(parent)
        self.parent = parent
        self.update_info = update_info
        self.title("Software Update Available")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        if parent and parent.state() != "withdrawn":
            try:
                self.transient(parent)
            except Exception:
                pass

        notes = (self.update_info.release_notes or "").strip()
        w = 500
        h = 380 if notes else 230
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = max(0, (sw - w) // 2)
        py = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{px}+{py}")
        set_dark_title_bar(self)

        self._build_ui()
        self.grab_set()

    def _build_ui(self):
        container = ttk.Frame(self, style="Root.TFrame", padding=(20, 16))
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="🚀  Update Ready to Install", style="Title.TLabel", font=(UI_FONT, 13, "bold")).pack(anchor="w")
        ttk.Label(
            container,
            text=f"A newer version (v{self.update_info.version}) is available. Current version is v{APP_VERSION}.",
            style="Sub.TLabel"
        ).pack(anchor="w", pady=(2, 12))

        # Notes Card (only shown if a clean change description exists)
        notes = (self.update_info.release_notes or "").strip()
        if notes:
            notes_card = ttk.Frame(container, style="Card.TFrame", padding=(12, 10))
            notes_card.pack(fill="both", expand=True, pady=(0, 12))

            ttk.Label(notes_card, text="RELEASE NOTES", style="CardTitle.TLabel", font=(UI_FONT, 9, "bold")).pack(anchor="w", pady=(0, 4))
            text_box = tk.Text(notes_card, bg=INPUT_BG, fg=TEXT_WHITE, relief="flat", wrap="word", height=6, font=(UI_FONT, 9))
            text_box.insert("1.0", notes)
            text_box.configure(state="disabled")
            text_box.pack(fill="both", expand=True)

        # Progress
        self.prog_var = tk.DoubleVar(value=0.0)
        self.prog_bar = ttk.Progressbar(container, variable=self.prog_var, maximum=100, style="Green.Horizontal.TProgressbar")
        self.prog_bar.pack(fill="x", pady=(0, 4))

        self.status_lbl = ttk.Label(container, text="Click 'Update Now' to download and install automatically.", style="Sub.TLabel")
        self.status_lbl.pack(anchor="w", pady=(0, 12))

        # Buttons
        btn_box = ttk.Frame(container, style="Root.TFrame")
        btn_box.pack(fill="x")

        self.btn_update = tk.Button(
            btn_box,
            text="⬇  Update Now",
            bg=ACCENT_GREEN,
            fg=TEXT_WHITE,
            activebackground=ACCENT_GREEN_HOVER,
            relief="flat",
            font=(UI_FONT, 9, "bold"),
            command=self._start_download,
            cursor="hand2",
            padx=16,
            pady=6,
        )
        self.btn_update.pack(side="left")

        self.btn_cancel = tk.Button(
            btn_box,
            text="Later",
            bg=BTN_SEC_BG,
            fg=TEXT_MAIN,
            activebackground=BTN_SEC_HOVER,
            relief="flat",
            font=(UI_FONT, 9),
            command=self.destroy,
            cursor="hand2",
            padx=12,
            pady=6,
        )
        self.btn_cancel.pack(side="right")

    def _start_download(self):
        self.btn_update.configure(state="disabled", text="Downloading...")
        self.btn_cancel.configure(state="disabled")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            target_dir = Path(tempfile.gettempdir()) / "EBillDownloaderUpdates"
            target_dir.mkdir(parents=True, exist_ok=True)
            local_file = target_dir / self.update_info.file_name

            resp = requests.get(self.update_info.download_url, stream=True, timeout=60)
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", self.update_info.file_size or 0))
            downloaded = 0

            with open(local_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = (downloaded / total_size) * 100
                            mb_cur = downloaded / (1024 * 1024)
                            mb_tot = total_size / (1024 * 1024)
                            self.after(0, lambda p=pct, c=mb_cur, t=mb_tot: self._update_ui_progress(p, c, t))

            self.after(0, lambda: self._on_download_complete(str(local_file)))
        except Exception as e:
            self.after(0, lambda err=e: self._on_download_error(str(err)))

    def _update_ui_progress(self, pct: float, cur: float, tot: float):
        self.prog_var.set(pct)
        self.status_lbl.configure(text=f"Downloading: {cur:.1f} MB / {tot:.1f} MB ({pct:.0f}%)")

    def _on_download_complete(self, file_path: str):
        self.status_lbl.configure(text="Download finished! Installing update...")
        install_and_restart(file_path, self.parent)

    def _on_download_error(self, err_msg: str):
        messagebox.showerror("Update Error", f"Failed to download update:\n{err_msg}", parent=self)
        self.btn_update.configure(state="normal", text="Retry")
        self.btn_cancel.configure(state="normal")
        self.status_lbl.configure(text=f"Download failed: {err_msg}")


# ──────────────────────────────────────────────────────────────
#  LICENSE ACTIVATION GATE DIALOG
# ──────────────────────────────────────────────────────────────
class LicenseGateDialog(tk.Toplevel):
    """VS Code Dark+ styled License Activation Gate & Subscription Dialog."""

    def __init__(self, parent: tk.Tk, initial_error: str = ""):
        super().__init__(parent)
        self.withdraw()
        self.parent = parent
        self.title("E-Bill Downloader — License Activation")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        try:
            if parent and parent.state() != "withdrawn":
                self.transient(parent)
        except Exception:
            pass

        self.activated = False
        self.license_info: dict | None = None
        self.device_id = get_device_id()
        self.queue = queue.Queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        w, h = 540, 620
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = max(0, (sw - w) // 2)
        py = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{px}+{py}")

        try:
            if sys.platform == "win32":
                icon_file = resource_path("assets/app.ico")
                if os.path.exists(icon_file):
                    self.iconbitmap(icon_file)
            png_file = resource_path("assets/app.png")
            if os.path.exists(png_file):
                self._icon_img = tk.PhotoImage(file=png_file)
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        set_dark_title_bar(self)
        self._build_ui(initial_error)
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass

        self._poll_queue()

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self.queue.get_nowait()
                if msg_type == "result":
                    self._on_activation_result(payload)
                elif msg_type == "error":
                    self._on_activation_error(payload)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(50, self._poll_queue)

    def _build_ui(self, initial_error: str):
        self.container = ttk.Frame(self, style="Root.TFrame", padding=(22, 16, 22, 16))
        self.container.pack(fill="both", expand=True)

        top_bar = ttk.Frame(self.container, style="Root.TFrame")
        top_bar.pack(fill="x", pady=(0, 12))

        ttk.Label(top_bar, text="E-Bill Downloader", style="Title.TLabel", font=(UI_FONT, 15, "bold")).pack(anchor="w")
        ttk.Label(top_bar, text="License Activation & Subscription Gate", style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        nav_frame = ttk.Frame(self.container, style="Root.TFrame")
        nav_frame.pack(fill="x", pady=(0, 12))

        self.btn_tab_activate = tk.Button(
            nav_frame,
            text="🔑  Enter Serial Key",
            font=(UI_FONT, 9, "bold"),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._show_activate_tab,
        )
        self.btn_tab_activate.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_tab_buy = tk.Button(
            nav_frame,
            text="🛒  Buy Subscription",
            font=(UI_FONT, 9, "bold"),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._show_buy_tab,
        )
        self.btn_tab_buy.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.tab_container = ttk.Frame(self.container, style="Root.TFrame")
        self.tab_container.pack(fill="both", expand=True)

        self.tab_activate = ttk.Frame(self.tab_container, style="Root.TFrame")
        self.tab_buy = ttk.Frame(self.tab_container, style="Root.TFrame")

        self._build_activate_tab(initial_error)
        self._build_buy_tab()

        self._show_activate_tab()

    def _build_activate_tab(self, initial_error: str):
        # Hardware ID Card
        hw_card = ttk.Frame(self.tab_activate, style="Card.TFrame", padding=(14, 10))
        hw_card.pack(fill="x", pady=(0, 10))

        ttk.Label(hw_card, text="YOUR HARDWARE IDENTIFIER (HWID)", font=(UI_FONT, 8, "bold"), foreground=TEXT_MUTED).pack(anchor="w")
        hw_row = ttk.Frame(hw_card, style="Card.TFrame")
        hw_row.pack(fill="x", pady=(4, 0))

        self.lbl_hwid = ttk.Label(hw_row, text=self.device_id, font=(MONO_FONT, 10, "bold"), foreground=TEXT_WHITE)
        self.lbl_hwid.pack(side="left", fill="x", expand=True)

        btn_copy = tk.Button(
            hw_row,
            text="📋 Copy",
            bg=BTN_SEC_BG,
            fg=TEXT_MAIN,
            activebackground=BTN_SEC_HOVER,
            relief="flat",
            font=(UI_FONT, 8),
            cursor="hand2",
            command=self._copy_hwid,
            padx=8,
            pady=2,
        )
        btn_copy.pack(side="right")

        # Serial Key Card
        key_card = ttk.Frame(self.tab_activate, style="Card.TFrame", padding=(14, 12))
        key_card.pack(fill="x", pady=(0, 10))

        ttk.Label(key_card, text="ENTER SERIAL KEY", font=(UI_FONT, 9, "bold"), foreground=TEXT_WHITE).pack(anchor="w")
        ttk.Label(key_card, text="Format: EB-XXXX-XXXX-XXXX (provided upon subscription purchase)", font=(UI_FONT, 8), foreground=TEXT_MUTED).pack(anchor="w", pady=(2, 8))

        self.key_var = tk.StringVar()
        self.entry_key = tk.Entry(
            key_card,
            textvariable=self.key_var,
            font=(MONO_FONT, 12, "bold"),
            bg=INPUT_BG,
            fg=TEXT_WHITE,
            insertbackground=TEXT_WHITE,
            relief="flat",
            justify="center",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_GREEN,
        )
        self.entry_key.pack(fill="x", ipady=6, pady=(0, 10))
        self.entry_key.bind("<Return>", lambda e: self._on_activate())

        self.btn_activate = tk.Button(
            key_card,
            text="⚡  ACTIVATE LICENSE",
            bg=ACCENT_GREEN,
            fg=TEXT_WHITE,
            activebackground=ACCENT_GREEN_HOVER,
            relief="flat",
            font=(UI_FONT, 10, "bold"),
            cursor="hand2",
            command=self._on_activate,
            pady=8,
        )
        self.btn_activate.pack(fill="x")

        # Status & Error feedback
        self.status_var = tk.StringVar(value=initial_error)
        self.lbl_status = ttk.Label(self.tab_activate, textvariable=self.status_var, style="Sub.TLabel", wraplength=480, foreground=ACCENT_RED if initial_error else TEXT_MUTED)
        self.lbl_status.pack(anchor="w", pady=(4, 0))

    def _build_buy_tab(self):
        plans_frame = ttk.Frame(self.tab_buy, style="Root.TFrame")
        plans_frame.pack(fill="both", expand=True)

        plans = [
            ("1 Month Subscription", "Rs. 300", "30 Days Validity  •  1 Single Device"),
            ("3 Months Subscription", "Rs. 700", "90 Days Validity  •  Up to 2 Devices"),
            ("6 Months Subscription", "Rs. 1,200", "180 Days Validity  •  Up to 2 Devices"),
            ("1 Year Subscription (Best Value)", "Rs. 2,000", "365 Days Validity  •  Up to 2 Devices"),
        ]

        for title, price, subtitle in plans:
            card = ttk.Frame(plans_frame, style="Card.TFrame", padding=(12, 8))
            card.pack(fill="x", pady=3)
            row = ttk.Frame(card, style="Card.TFrame")
            row.pack(fill="x")
            ttk.Label(row, text=title, font=(UI_FONT, 9, "bold"), foreground=TEXT_WHITE).pack(side="left")
            ttk.Label(row, text=price, font=(UI_FONT, 9, "bold"), foreground="#89d185").pack(side="right")
            ttk.Label(card, text=subtitle, font=(UI_FONT, 8), foreground=TEXT_MUTED).pack(anchor="w", pady=(2, 0))

        # WhatsApp CTA Card
        cta = ttk.Frame(self.tab_buy, style="Card.TFrame", padding=(14, 12))
        cta.pack(fill="x", pady=(10, 0))

        ttk.Label(cta, text="Contact Developer for Instant Activation:", font=(UI_FONT, 9, "bold"), foreground=TEXT_WHITE).pack(anchor="w")
        ttk.Label(cta, text="Send your payment receipt and HWID on WhatsApp to receive your serial key.", font=(UI_FONT, 8), foreground=TEXT_MUTED).pack(anchor="w", pady=(2, 8))

        btn_wa = tk.Button(
            cta,
            text="💬  Open WhatsApp Support (+92 333 9962474)",
            bg="#128C7E",
            fg=TEXT_WHITE,
            activebackground="#075E54",
            relief="flat",
            font=(UI_FONT, 9, "bold"),
            cursor="hand2",
            command=lambda: webbrowser.open(SUPPORT_WHATSAPP),
            pady=6,
        )
        btn_wa.pack(fill="x")

    def _show_activate_tab(self):
        self.tab_buy.pack_forget()
        self.tab_activate.pack(fill="both", expand=True)
        self.btn_tab_activate.configure(bg=CARD_BG, fg=TEXT_WHITE)
        self.btn_tab_buy.configure(bg=BG_DARK, fg=TEXT_MUTED)

    def _show_buy_tab(self):
        self.tab_activate.pack_forget()
        self.tab_buy.pack(fill="both", expand=True)
        self.btn_tab_buy.configure(bg=CARD_BG, fg=TEXT_WHITE)
        self.btn_tab_activate.configure(bg=BG_DARK, fg=TEXT_MUTED)

    def _copy_hwid(self):
        self.clipboard_clear()
        self.clipboard_append(self.device_id)
        self.status_var.set("Hardware ID copied to clipboard.")
        self.lbl_status.configure(foreground="#89d185")

    def _on_activate(self):
        key = self.key_var.get().strip().upper()
        if not key:
            self.status_var.set("Please enter a valid serial key.")
            self.lbl_status.configure(foreground=ACCENT_RED)
            return

        self.btn_activate.configure(state="disabled", text="Verifying Key...", bg="#1a5c28")
        self.status_var.set("Connecting to licensing server...")
        self.lbl_status.configure(foreground=TEXT_MUTED)

        threading.Thread(target=self._activate_worker, args=(key,), daemon=True).start()

    def _activate_worker(self, key: str):
        try:
            candidate_ids = get_candidate_device_ids()
            result = activate_license_remote(key, self.device_id, candidate_ids)
            self.queue.put(("result", (key, result)))
        except Exception as e:
            self.queue.put(("error", str(e)))

    def _on_activation_result(self, payload: tuple[str, dict]):
        key, result = payload
        self.btn_activate.configure(state="normal", text="⚡  ACTIVATE LICENSE", bg=ACCENT_GREEN)

        if result.get("valid"):
            result["serial_key"] = key
            save_local_license(result)
            self.activated = True
            self.license_info = result
            messagebox.showinfo(
                "Activation Successful",
                f"License activated successfully!\n\n"
                f"Plan: {format_plan_label(result.get('plan_type'))}\n"
                f"Expires: {format_expiry_date(result.get('expires_at'))}",
                parent=self
            )
            self.destroy()
        else:
            msg = result.get("message") or "Activation failed. Invalid or expired key."
            self.status_var.set(msg)
            self.lbl_status.configure(foreground=ACCENT_RED)

    def _on_activation_error(self, err_msg: str):
        self.btn_activate.configure(state="normal", text="⚡  ACTIVATE LICENSE", bg=ACCENT_GREEN)
        self.status_var.set(f"Connection error: {err_msg}")
        self.lbl_status.configure(foreground=ACCENT_RED)

    def _on_close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if self.parent:
            try:
                if self.parent.state() == "withdrawn":
                    self.parent.destroy()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────
#  ABOUT DIALOG
# ──────────────────────────────────────────────────────────────
class AboutDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, license_info: dict | None):
        super().__init__(parent)
        self.parent = parent
        self.license_info = license_info
        self.title("About E-Bill Downloader")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        if parent and parent.state() != "withdrawn":
            try:
                self.transient(parent)
            except Exception:
                pass

        w, h = 480, 360
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = max(0, (sw - w) // 2)
        py = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{px}+{py}")
        set_dark_title_bar(self)

        container = ttk.Frame(self, style="Root.TFrame", padding=(20, 16))
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="E-Bill Downloader", font=(UI_FONT, 14, "bold"), foreground=TEXT_WHITE).pack(anchor="w")
        ttk.Label(container, text=f"Version {APP_VERSION}  •  TN Developers Co.", font=(UI_FONT, 9), foreground=TEXT_MUTED).pack(anchor="w", pady=(2, 12))

        # License info card
        lic_card = ttk.Frame(container, style="Card.TFrame", padding=(14, 12))
        lic_card.pack(fill="x", pady=(0, 12))

        ttk.Label(lic_card, text="SUBSCRIPTION DETAILS", font=(UI_FONT, 8, "bold"), foreground=TEXT_MUTED).pack(anchor="w", pady=(0, 6))

        plan = format_plan_label(license_info.get("plan_type") if license_info else None)
        exp = format_expiry_date(license_info.get("expires_at") if license_info else None)
        s_key = license_info.get("serial_key", "Not Activated") if license_info else "Not Activated"

        details = [
            ("Subscription Plan:", plan),
            ("Serial Key:", s_key),
            ("Expires At:", exp),
        ]

        for k, v in details:
            r = ttk.Frame(lic_card, style="Card.TFrame")
            r.pack(fill="x", pady=2)
            ttk.Label(r, text=k, font=(UI_FONT, 8), foreground=TEXT_MUTED, width=16).pack(side="left")
            ttk.Label(r, text=v, font=(UI_FONT, 8, "bold"), foreground=TEXT_WHITE).pack(side="left", fill="x", expand=True)
            if k == "Serial Key:":
                self.copy_key_btn = tk.Button(
                    r,
                    text="📋 Copy",
                    bg=BTN_SEC_BG,
                    fg=TEXT_MAIN,
                    activebackground=BTN_SEC_HOVER,
                    activeforeground=TEXT_WHITE,
                    font=(UI_FONT, 8),
                    relief="flat",
                    cursor="hand2",
                    padx=8,
                    pady=1,
                    command=self._copy_serial_key,
                )
                self.copy_key_btn.pack(side="right")

                self.change_key_btn = tk.Button(
                    r,
                    text="🔑 Change Key",
                    bg=BTN_SEC_BG,
                    fg=TEXT_WHITE,
                    activebackground=BTN_SEC_HOVER,
                    activeforeground=TEXT_WHITE,
                    font=(UI_FONT, 8, "bold"),
                    relief="flat",
                    cursor="hand2",
                    padx=8,
                    pady=1,
                    command=self._change_serial_key,
                )
                self.change_key_btn.pack(side="right", padx=(0, 6))

        # Support card
        sup_card = ttk.Frame(container, style="Card.TFrame", padding=(14, 12))
        sup_card.pack(fill="x", pady=(0, 12))
        ttk.Label(sup_card, text="DEVELOPER SUPPORT", font=(UI_FONT, 8, "bold"), foreground=TEXT_MUTED).pack(anchor="w", pady=(0, 6))
        ttk.Label(sup_card, text="WhatsApp: +92 333 9962474  •  Email: tahir.naqash4@gmail.com", font=(UI_FONT, 8), foreground=TEXT_WHITE).pack(anchor="w")

        btn_box = ttk.Frame(container, style="Root.TFrame")
        btn_box.pack(fill="x")

        self.btn_check_update = tk.Button(
            btn_box,
            text="🔄  Check for Updates",
            bg=BTN_SEC_BG,
            fg=TEXT_MAIN,
            activebackground=BTN_SEC_HOVER,
            relief="flat",
            font=(UI_FONT, 9),
            command=self._check_update_manual,
            padx=12,
            pady=4,
            cursor="hand2"
        )
        self.btn_check_update.pack(side="left")

        tk.Button(
            btn_box,
            text="Close",
            bg=BTN_SEC_BG,
            fg=TEXT_MAIN,
            relief="flat",
            font=(UI_FONT, 9),
            command=self.destroy,
            padx=14,
            pady=4,
            cursor="hand2"
        ).pack(side="right")

        self.grab_set()

    def _copy_serial_key(self):
        lic = getattr(self.parent, "active_license", None) or self.license_info or load_local_license()
        key = lic.get("serial_key", "") if lic else ""
        if key and key != "Not Activated":
            self.clipboard_clear()
            self.clipboard_append(key)
            self.copy_key_btn.configure(text="✔ Copied!", fg="#89d185")
            self.after(2000, lambda: self.copy_key_btn.configure(text="📋 Copy", fg=TEXT_MAIN) if self.winfo_exists() and hasattr(self, "copy_key_btn") and self.copy_key_btn.winfo_exists() else None)

    def _change_serial_key(self):
        parent = self.parent
        self.destroy()
        gate = LicenseGateDialog(parent)
        parent.wait_window(gate)
        if gate.activated and gate.license_info:
            parent.active_license = gate.license_info
            messagebox.showinfo("License Activated", "Serial key updated successfully!", parent=parent)

    def _check_update_manual(self):
        self.btn_check_update.configure(state="disabled", text="Checking...")
        def worker():
            info = check_for_updates()
            def update_ui():
                if not self.winfo_exists():
                    return
                self.btn_check_update.configure(state="normal", text="🔄  Check for Updates")
                if info:
                    self.destroy()
                    UpdateDialog(self.parent, info)
                else:
                    messagebox.showinfo("Up to Date", f"You are running the latest version (v{APP_VERSION})!", parent=self)
            self.after(0, update_ui)
        threading.Thread(target=worker, daemon=True).start()


# ──────────────────────────────────────────────────────────────
#  CORE DOWNLOADER ENGINE (Selenium + PyMuPDF fitz + pypdf)
# ──────────────────────────────────────────────────────────────
class BillWorkerEngine:
    PDF_SCALE_X = 0.90
    PDF_SCALE_Y = 0.96
    PDF_IGNORED_CROP_TEXT = (
        "snap service temporarily unavailable",
        "sr. no.",
    )

    def __init__(self, job: dict, event_queue: queue.Queue, stop_event: threading.Event, pause_event: threading.Event):
        self.job = job
        self.queue = event_queue
        self.stop_event = stop_event
        self.pause_event = pause_event

    def log(self, message: str):
        self.queue.put(("log", message))

    def progress(self, cur: int, total: int, saved: int, not_found: int, errors: int):
        self.queue.put(("progress", (cur, total, saved, not_found, errors)))

    def _unique_pdf(self, folder: str, base: str) -> str:
        clean_base = re.sub(r'[\\/*?:"<>|]', "_", str(base).strip())
        p = os.path.join(folder, f"{clean_base}.pdf")
        if not os.path.exists(p):
            return p
        i = 1
        while True:
            p2 = os.path.join(folder, f"{clean_base} ({i}).pdf")
            if not os.path.exists(p2):
                return p2
            i += 1

    def _fit_pdf_to_a4(self, pdf_path: str, sr: str | None = None):
        """Scale and center captured PDF bill onto standard A4 page with optional Sr No stamp."""
        sys.modules.setdefault("pymupdf.layout", None)
        import fitz

        src = fitz.open(pdf_path)
        if not src.page_count:
            src.close()
            return

        src_page = src[0]
        content_rect = None

        for block in src_page.get_text("blocks"):
            if len(block) >= 5 and str(block[4]).strip():
                text = str(block[4]).strip().lower()
                if any(ignored in text for ignored in self.PDF_IGNORED_CROP_TEXT):
                    continue
                rect = fitz.Rect(block[:4])
                content_rect = rect if content_rect is None else content_rect | rect

        if content_rect is None or content_rect.is_empty:
            content_rect = src_page.rect
        else:
            content_rect = content_rect + (-8, -8, 8, 8)
            content_rect &= src_page.rect

        out = fitz.open()
        a4 = fitz.paper_rect("a4")
        page = out.new_page(width=a4.width, height=a4.height)

        if sr:
            stamp = f"Sr. No. {sr}"
            text_width = fitz.get_text_length(stamp, fontname="helv", fontsize=14)
            page.insert_text(
                fitz.Point(a4.width - text_width - 24, 24),
                stamp,
                fontsize=14,
                fontname="helv",
                color=(0, 0, 0),
            )
            usable = fitz.Rect(0, 36, a4.width, a4.height)
        else:
            usable = a4

        target_width = usable.width * self.PDF_SCALE_X
        target_height = usable.height * self.PDF_SCALE_Y
        target = fitz.Rect(
            usable.x0 + (usable.width - target_width) / 2,
            usable.y0 + (usable.height - target_height) / 2,
            usable.x0 + (usable.width + target_width) / 2,
            usable.y0 + (usable.height + target_height) / 2,
        )

        page.show_pdf_page(target, src, 0, clip=content_rect, keep_proportion=False)

        base, ext = os.path.splitext(pdf_path)
        tmp_path = f"{base}_tmp{ext}"
        out.save(tmp_path, garbage=4, deflate=True)
        out.close()
        src.close()
        del out, src
        gc.collect()

        for attempt in range(5):
            try:
                os.replace(tmp_path, pdf_path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)

    def run(self):
        try:
            self._execute()
        except Exception as e:
            self.log(f"❌ CRITICAL ERROR: {e}")
            self.queue.put(("error", str(e)))
        finally:
            self.queue.put(("finished", None))

    def _execute(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.common.by import By
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import TimeoutException
            from webdriver_manager.chrome import ChromeDriverManager
            from pypdf import PdfReader, PdfWriter
        except Exception as e:
            self.log(f"❌ Dependency import failure: {e}")
            return

        excel_path = self.job["excel_path"]
        out_folder = self.job["out_folder"]
        url = self.job["url"]
        headless = self.job["headless"]
        add_sr = self.job["add_sr"]
        separate = self.job["separate"]

        os.makedirs(out_folder, exist_ok=True)

        try:
            wb = load_workbook(excel_path)
            sh = wb.active
        except Exception as e:
            self.log(f"❌ Failed to open Excel workbook: {e}")
            return

        self.log(f"🚀 Initializing Chrome Web Driver (Headless: {headless})...")
        opts = ChromeOptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--log-level=3")

        driver = None
        try:
            try:
                driver_path = ChromeDriverManager().install()
                driver = webdriver.Chrome(service=Service(driver_path), options=opts)
            except Exception:
                driver = webdriver.Chrome(options=opts)
        except Exception as e:
            self.log(f"❌ Failed to start Chrome Driver: {e}")
            return

        total = max(0, sh.max_row - 1)
        done = 0
        saved_count = 0
        not_found_count = 0
        error_count = 0
        collected: list[tuple[int, str]] = []

        WAIT = 12
        MAX_ATTEMPTS = 3
        MIN_RENDER_WAIT = 5

        def page_text():
            try:
                return driver.find_element(By.TAG_NAME, "body").text
            except Exception:
                return ""

        def bill_state(ac_no):
            text = page_text()
            text_l = text.lower()
            if "bill not found" in text_l:
                return "not_found"
            if "does not belongs" in text_l:
                return "wrong_ac"

            has_old_print_button = bool(driver.find_elements(By.CSS_SELECTOR, ".auto-center.btn.btn-secondary"))
            has_print_command = bool(driver.find_elements(
                By.XPATH,
                "//*[self::button or self::a or self::input][contains("
                "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'print') "
                "or contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'print') "
                "or contains(translate(@onclick, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'print')]"
            ))

            bill_keywords = ["reference", "consumer", "billing month", "due date", "payable", "amount", "pesco"]
            keyword_hits = sum(1 for kw in bill_keywords if kw in text_l)
            ac_visible = ac_no in re.sub(r"\s+", "", text)

            if has_old_print_button or has_print_command:
                return "loaded"
            if ac_visible and keyword_hits >= 2:
                return "loaded"
            return "loading"

        def wait_until_render_ready(clicked_at):
            rem = MIN_RENDER_WAIT - (time.time() - clicked_at)
            if rem > 0:
                time.sleep(rem)
            try:
                WebDriverWait(driver, 5).until(lambda d: d.execute_script("""
                    const ready = document.readyState === 'complete';
                    const imagesReady = Array.from(document.images || []).every(img => img.complete);
                    return ready && imagesReady;
                """))
            except Exception:
                pass

        self.log(f"📋 Starting bill processing: {total} items found in Excel.")

        try:
            for r in range(2, sh.max_row + 1):
                if self.stop_event.is_set():
                    sh.cell(r, 3).value = "Stopped"
                    wb.save(excel_path)
                    self.log("🛑 Download stopped by user.")
                    break

                while self.pause_event.is_set():
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.3)

                if self.stop_event.is_set():
                    break

                ac = sh.cell(r, 1).value
                sr = sh.cell(r, 2).value
                if not ac:
                    break

                ac = str(ac).strip()
                sr_str = str(sr).strip() if sr is not None else ""
                sr_suffix = f" (Sr: {sr_str})" if sr_str and sr_str.upper() != "N/A" else ""
                self.log(f"[{done + 1}/{total}] Searching AC: {ac}{sr_suffix}")

                status = None
                bill_loaded = False

                for attempt in range(1, MAX_ATTEMPTS + 1):
                    driver.get(url)
                    time.sleep(1.5)
                    try:
                        wait = WebDriverWait(driver, 15)
                        box = wait.until(EC.element_to_be_clickable((By.ID, "searchTextBox")))
                        box.clear()
                        box.send_keys(ac)
                        clicked_at = time.time()
                        driver.find_element(By.ID, "btnSearch").click()

                        end = clicked_at + WAIT
                        state = "loading"
                        while time.time() < end:
                            state = bill_state(ac)
                            if state == "loaded" and time.time() - clicked_at < MIN_RENDER_WAIT:
                                state = "loading"
                            if state != "loading":
                                break
                            time.sleep(0.5)
                    except TimeoutException:
                        state = "loading"

                    if state == "not_found":
                        status = "Bill not Found"
                        not_found_count += 1
                        break
                    if state == "wrong_ac":
                        status = "Wrong AC No."
                        not_found_count += 1
                        break
                    if state == "loaded":
                        wait_until_render_ready(clicked_at)
                        bill_loaded = True
                        status = "Saved"
                        break

                    self.log(f"  Attempt {attempt}/{MAX_ATTEMPTS}: bill page loading timed out, retrying...")

                if status is None:
                    status = "Bill not loaded (timeout)"
                    error_count += 1

                if not bill_loaded:
                    sh.cell(r, 3).value = status
                    wb.save(excel_path)
                    done += 1
                    self.progress(done, total, saved_count, not_found_count, error_count)
                    self.log(f"  → Status: {status}")
                    continue

                # Print to PDF using Chrome CDP
                pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {
                    "printBackground": True,
                    "paperWidth": 8.27,
                    "paperHeight": 11.69,
                    "marginTop": 0,
                    "marginBottom": 0,
                    "marginLeft": 0,
                    "marginRight": 0,
                    "scale": self.PDF_SCALE_X
                })

                pdf_name = sr_str if sr_str else ac
                pdf_path = self._unique_pdf(out_folder, pdf_name)
                with open(pdf_path, "wb") as f:
                    f.write(base64.b64decode(pdf_data["data"]))

                try:
                    self._fit_pdf_to_a4(pdf_path, sr_str if add_sr and sr_str else None)
                except Exception as e:
                    self.log(f"  ⚠️ A4 format warning ({ac}): {e}")

                order_key = int(sr_str) if sr_str.isdigit() else 999999
                collected.append((order_key, pdf_path))

                sh.cell(r, 3).value = "Saved"
                wb.save(excel_path)
                saved_count += 1
                done += 1
                self.progress(done, total, saved_count, not_found_count, error_count)
                self.log(f"  ✔ PDF saved: {os.path.basename(pdf_path)}")

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        # Merge PDFs if Separate PDFs is unchecked
        if not separate and collected:
            self.log("📑 Merging individual PDFs into a single workbook PDF...")
            if add_sr:
                collected.sort(key=lambda x: x[0])

            base_name = os.path.splitext(os.path.basename(excel_path))[0]
            merged_path = self._unique_pdf(out_folder, f"{base_name}_Merged")

            writer = PdfWriter()
            for _, p in collected:
                try:
                    reader = PdfReader(p)
                    for page in reader.pages:
                        writer.add_page(page)
                except Exception as e:
                    self.log(f"  ⚠️ Error merging {p}: {e}")

            with open(merged_path, "wb") as f:
                writer.write(f)

            # Cleanup individual files
            for _, p in collected:
                try:
                    os.remove(p)
                except Exception:
                    pass

            self.log(f"✔ Combined PDF created: {os.path.basename(merged_path)}")

        self.log("🏁 Batch download process completed.")


# ──────────────────────────────────────────────────────────────
#  MAIN APPLICATION GUI (Tkinter VS Code Dark+ Theme)
# ──────────────────────────────────────────────────────────────
class EBillDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()  # Hidden until license verified
        self.title("E-Bill Downloader")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        w, h = 640, 630
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = max(0, (sw - w) // 2)
        py = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{px}+{py}")
        self.minsize(580, 540)

        # Application Icon
        self._icon_img = None
        try:
            if sys.platform == "win32":
                icon_file = resource_path("assets/app.ico")
                if os.path.exists(icon_file):
                    self.iconbitmap(icon_file)
            png_file = resource_path("assets/app.png")
            if os.path.exists(png_file):
                self._icon_img = tk.PhotoImage(file=png_file)
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        self._init_theme_styles()

        # State Variables
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.worker_thread: threading.Thread | None = None

        config = load_app_config()
        self.excel_var = tk.StringVar(value=config.get("last_excel", ""))
        self.url_var = tk.StringVar(value=config.get("bills_url", DEFAULT_URL))
        default_out = config.get("output_folder", os.path.join(os.environ.get("USERPROFILE", "C:"), "Desktop", "BillsPDF"))
        self.out_var = tk.StringVar(value=default_out)

        self.chk_sr_var = tk.BooleanVar(value=config.get("add_sr", False))
        self.chk_sep_var = tk.BooleanVar(value=config.get("separate_pdf", True))
        self.chk_headless_var = tk.BooleanVar(value=config.get("headless", True))

        self.total_var = tk.StringVar(value="0")
        self.ok_var = tk.StringVar(value="0")
        self.not_found_var = tk.StringVar(value="0")
        self.err_var = tk.StringVar(value="0")
        self.prog_text_var = tk.StringVar(value="0 / 0 bills")
        self.stats_var = tk.StringVar(value="Saved: 0  |  Not Found: 0  |  Errors: 0")
        self.status_var = tk.StringVar(value="Ready. Select an Excel file containing Account Numbers.")

        self.active_license: dict | None = None
        self.latest_update: UpdateInfo | None = None
        self.update_banner: tk.Frame | None = None

        # Verify License Gate
        if not self.ensure_licensed():
            try:
                if self.winfo_exists():
                    self.destroy()
            except Exception:
                pass
            return

        self.build_ui()
        set_dark_title_bar(self)
        self.update_idletasks()
        self.deiconify()

        self.after(100, self.drain_events)
        threading.Thread(target=self._bg_update_check, daemon=True).start()

    def _init_theme_styles(self):
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.style.configure(".", background=CARD_BG, foreground=TEXT_MAIN)
        self.style.configure("TFrame", background=BG_DARK)
        self.style.configure("Root.TFrame", background=BG_DARK)
        self.style.configure("Card.TFrame", background=CARD_BG)

        self.style.configure(
            "TLabelframe",
            background=CARD_BG,
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            relief="solid",
        )
        self.style.configure(
            "TLabelframe.Label",
            background=CARD_BG,
            foreground=TEXT_WHITE,
            font=(UI_FONT, 9, "bold"),
        )

        self.style.configure("TLabel", background=CARD_BG, foreground=TEXT_MAIN, font=(UI_FONT, 9))
        self.style.configure("Root.TLabel", background=BG_DARK, foreground=TEXT_MAIN, font=(UI_FONT, 9))
        self.style.configure("Title.TLabel", background=BG_DARK, foreground=TEXT_WHITE, font=(UI_FONT, 16, "bold"))
        self.style.configure("Sub.TLabel", background=BG_DARK, foreground=TEXT_MUTED, font=(UI_FONT, 9))
        self.style.configure("Status.TLabel", background=BG_DARK, foreground=TEXT_MAIN, font=(UI_FONT, 9))
        self.style.configure("CardTitle.TLabel", background=CARD_BG, foreground=TEXT_WHITE, font=(UI_FONT, 9, "bold"))
        self.style.configure("StatTitle.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=(UI_FONT, 9))
        self.style.configure("StatVal.TLabel", background=CARD_BG, foreground=TEXT_WHITE, font=(UI_FONT, 9, "bold"))
        self.style.configure("StatOk.TLabel", background=CARD_BG, foreground="#89d185", font=(UI_FONT, 9, "bold"))
        self.style.configure("StatWarn.TLabel", background=CARD_BG, foreground="#cca700", font=(UI_FONT, 9, "bold"))
        self.style.configure("StatErr.TLabel", background=CARD_BG, foreground="#f14c4c", font=(UI_FONT, 9, "bold"))

        self.style.configure(
            "TEntry",
            fieldbackground=INPUT_BG,
            foreground=TEXT_WHITE,
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            insertcolor=TEXT_WHITE,
        )

        self.style.configure(
            "TButton",
            background=BTN_SEC_BG,
            foreground=TEXT_MAIN,
            bordercolor=BORDER_COLOR,
            relief="flat",
            padding=(10, 4),
        )
        self.style.map(
            "TButton",
            background=[("active", BTN_SEC_HOVER), ("disabled", BTN_DISABLED_BG)],
            foreground=[("disabled", BTN_DISABLED_FG)],
        )

        self.style.configure(
            "TCheckbutton",
            background=CARD_BG,
            foreground=TEXT_WHITE,
            font=(UI_FONT, 9),
            indicatorbackground=INPUT_BG,
            indicatorforeground=ACCENT_GREEN,
            relief="flat",
        )
        self.style.map(
            "TCheckbutton",
            background=[("active", CARD_BG)],
            foreground=[("active", TEXT_WHITE), ("disabled", TEXT_MUTED)],
        )

        self.style.configure(
            "Green.Horizontal.TProgressbar",
            troughcolor=INPUT_BG,
            background=ACCENT_GREEN,
            bordercolor=BORDER_COLOR,
        )

    def ensure_licensed(self) -> bool:
        local_lic = load_local_license()
        device_id = get_device_id()
        initial_error = ""

        if local_lic and local_lic.get("serial_key"):
            exp_str = local_lic.get("expires_at")
            is_valid = False
            if exp_str:
                try:
                    clean_ts = str(exp_str).replace("Z", "+00:00")
                    exp_dt = datetime.fromisoformat(clean_ts)
                    if exp_dt > datetime.now(timezone.utc):
                        is_valid = True
                except Exception:
                    pass

            if is_valid:
                self.active_license = local_lic
                threading.Thread(target=self._bg_verify_license, daemon=True).start()
                return True

            try:
                candidate_ids = get_candidate_device_ids()
                res = verify_license_remote(local_lic["serial_key"], device_id, candidate_ids=candidate_ids)
                if res.get("valid"):
                    local_lic.update(res)
                    save_local_license(local_lic)
                    self.active_license = local_lic
                    return True
                else:
                    initial_error = res.get("message") or "License expired or invalid."
            except Exception as e:
                initial_error = f"License verification error: {e}"

        gate = LicenseGateDialog(self, initial_error=initial_error)
        self.wait_window(gate)

        if gate.activated and gate.license_info:
            self.active_license = gate.license_info
            return True

        return False

    def _bg_verify_license(self):
        try:
            local_lic = load_local_license()
            if not local_lic or not local_lic.get("serial_key"):
                return
            key = local_lic["serial_key"]
            device_id = get_device_id()
            candidate_ids = get_candidate_device_ids()
            res = verify_license_remote(key, device_id, candidate_ids=candidate_ids)
            if res.get("valid"):
                local_lic.update(res)
                save_local_license(local_lic)
                self.active_license = local_lic
            else:
                msg = res.get("message") or "Your license is no longer valid or has expired."
                self.after(0, lambda: self._on_license_revoked(msg))
        except Exception:
            pass

    def _on_license_revoked(self, reason: str):
        messagebox.showerror("License Expired", reason, parent=self)
        gate = LicenseGateDialog(self, initial_error=reason)
        self.wait_window(gate)
        if gate.activated and gate.license_info:
            self.active_license = gate.license_info
        else:
            self.destroy()

    def _bg_update_check(self):
        info = check_for_updates()
        if info:
            self.latest_update = info
            self.after(0, self._show_update_banner)

    def _show_update_banner(self):
        if self.update_banner or not self.latest_update:
            return
        self.update_banner = tk.Frame(self, bg=ACCENT_BLUE, pady=6, padx=12)
        self.update_banner.pack(side="top", fill="x", before=self.main_container)

        lbl_text = f"🚀  Update Available: Version {self.latest_update.version} is ready to install!"
        tk.Label(self.update_banner, text=lbl_text, bg=ACCENT_BLUE, fg=TEXT_WHITE, font=(UI_FONT, 9, "bold")).pack(side="left")

        btn_update = tk.Button(
            self.update_banner,
            text="Update Now",
            bg=TEXT_WHITE,
            fg=BG_DARK,
            font=(UI_FONT, 8, "bold"),
            relief="flat",
            command=self._open_update_dialog,
            cursor="hand2",
            padx=10,
            pady=2,
        )
        btn_update.pack(side="right", padx=(8, 0))

    def _open_update_dialog(self):
        if self.latest_update:
            UpdateDialog(self, self.latest_update)

    def build_ui(self):
        self.main_container = ttk.Frame(self, style="Root.TFrame", padding=(16, 8, 16, 8))
        self.main_container.pack(fill="both", expand=True)

        # Header bar
        header_bar = ttk.Frame(self.main_container, style="Root.TFrame")
        header_bar.pack(fill="x", pady=(0, 6))

        title_box = ttk.Frame(header_bar, style="Root.TFrame")
        title_box.pack(side="left")
        ttk.Label(title_box, text="E-Bill Downloader", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Downloads E-Bill into PDFs, Seperate/Multi PDFs & Adds Sr. No.", style="Sub.TLabel").pack(anchor="w")

        btn_box = ttk.Frame(header_bar, style="Root.TFrame")
        btn_box.pack(side="right", pady=4)

        tk.Button(
            btn_box,
            text="ℹ About",
            bg=ACCENT_ORANGE,
            fg=TEXT_WHITE,
            activebackground=ACCENT_ORANGE_HOVER,
            activeforeground=TEXT_WHITE,
            relief="flat",
            font=(UI_FONT, 8, "bold"),
            cursor="hand2",
            command=lambda: AboutDialog(self, self.active_license),
            padx=10,
            pady=3,
        ).pack(side="right", padx=(6, 0))

        # Inputs Card
        inputs_card = ttk.LabelFrame(self.main_container, text="  INPUT CONFIGURATION  ", padding=(12, 6))
        inputs_card.pack(fill="x", pady=(0, 6))

        # 1. Excel File
        r1 = ttk.Frame(inputs_card, style="Card.TFrame")
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="Excel File:", width=13).pack(side="left")
        entry_excel = tk.Entry(
            r1,
            textvariable=self.excel_var,
            bg=INPUT_BG,
            fg=TEXT_WHITE,
            readonlybackground=INPUT_BG,
            disabledbackground=INPUT_BG,
            disabledforeground=TEXT_WHITE,
            relief="flat",
            font=(UI_FONT, 9),
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_GREEN,
            state="readonly",
        )
        entry_excel.pack(side="left", fill="x", expand=True, padx=(4, 6), ipady=2)

        btn_excel_box = ttk.Frame(r1, style="Card.TFrame")
        btn_excel_box.pack(side="right")

        tk.Button(
            btn_excel_box,
            text="Browse...",
            bg=BTN_SEC_BG,
            fg=TEXT_MAIN,
            activebackground=BTN_SEC_HOVER,
            relief="flat",
            font=(UI_FONT, 9),
            cursor="hand2",
            command=self._browse_excel,
            padx=10,
            pady=2,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_excel_box,
            text="Template",
            bg=ACCENT_BLUE,
            fg=TEXT_WHITE,
            activebackground=ACCENT_BLUE_HOVER,
            activeforeground=TEXT_WHITE,
            relief="flat",
            font=(UI_FONT, 9, "bold"),
            cursor="hand2",
            command=self._download_template,
            padx=10,
            pady=2,
        ).pack(side="left")

        # 2. Bills URL
        r2 = ttk.Frame(inputs_card, style="Card.TFrame")
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="Bills URL:", width=13).pack(side="left")
        self.entry_url = tk.Entry(
            r2,
            textvariable=self.url_var,
            bg=INPUT_BG,
            fg=TEXT_WHITE,
            relief="flat",
            font=(UI_FONT, 9),
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_GREEN,
        )
        self.entry_url.pack(side="left", fill="x", expand=True, padx=(4, 6), ipady=2)
        self.entry_url.bind("<Return>", lambda e: self._save_url())

        btn_url_box = ttk.Frame(r2, style="Card.TFrame")
        btn_url_box.pack(side="right")

        self.btn_save_url = tk.Button(
            btn_url_box,
            text="Save",
            bg=ACCENT_GREEN,
            fg=TEXT_WHITE,
            activebackground=ACCENT_GREEN_HOVER,
            activeforeground=TEXT_WHITE,
            relief="flat",
            font=(UI_FONT, 9, "bold"),
            cursor="hand2",
            command=self._save_url,
            padx=12,
            pady=2,
        )
        self.btn_save_url.pack(side="left")

        # 3. Output Folder
        r3 = ttk.Frame(inputs_card, style="Card.TFrame")
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="Output Folder:", width=13).pack(side="left")
        entry_out = tk.Entry(
            r3,
            textvariable=self.out_var,
            bg=INPUT_BG,
            fg=TEXT_WHITE,
            readonlybackground=INPUT_BG,
            disabledbackground=INPUT_BG,
            disabledforeground=TEXT_WHITE,
            relief="flat",
            font=(UI_FONT, 9),
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_GREEN,
            state="readonly",
        )
        entry_out.pack(side="left", fill="x", expand=True, padx=(4, 6), ipady=2)

        tk.Button(
            r3,
            text="Change...",
            bg=BTN_SEC_BG,
            fg=TEXT_MAIN,
            activebackground=BTN_SEC_HOVER,
            relief="flat",
            font=(UI_FONT, 9),
            cursor="hand2",
            command=self._browse_output_folder,
            padx=12,
            pady=2,
        ).pack(side="right")

        # Options & Progress Summary (Side-by-side mid-frame as in Bill Scrapper)
        mid_frame = ttk.Frame(self.main_container, style="Root.TFrame")
        mid_frame.pack(fill="x", pady=(0, 6))

        # Left: Download Options
        options_card = ttk.LabelFrame(mid_frame, text="  DOWNLOAD OPTIONS  ", padding=(10, 8))
        options_card.pack(side="left", fill="both", expand=True, padx=(0, 4))

        ttk.Checkbutton(options_card, text="Add Sr. No. on Bill", variable=self.chk_sr_var).pack(anchor="w", pady=(4, 6))
        ttk.Checkbutton(options_card, text="Separate PDFs (Individual)", variable=self.chk_sep_var).pack(anchor="w", pady=(0, 4))

        # Right: Progress Summary
        stats_box = ttk.LabelFrame(mid_frame, text="  PROGRESS SUMMARY  ", padding=(10, 6))
        stats_box.pack(side="right", fill="both", expand=True, padx=(4, 0))

        ttk.Label(stats_box, text="Total:", style="StatTitle.TLabel").grid(row=0, column=0, sticky="w", padx=(4, 2), pady=2)
        ttk.Label(stats_box, textvariable=self.total_var, style="StatVal.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 10), pady=2)

        ttk.Label(stats_box, text="Downloaded:", style="StatTitle.TLabel").grid(row=0, column=2, sticky="w", padx=(4, 2), pady=2)
        ttk.Label(stats_box, textvariable=self.ok_var, style="StatOk.TLabel").grid(row=0, column=3, sticky="w", padx=(0, 4), pady=2)

        ttk.Label(stats_box, text="Not Found:", style="StatTitle.TLabel").grid(row=1, column=0, sticky="w", padx=(4, 2), pady=2)
        ttk.Label(stats_box, textvariable=self.not_found_var, style="StatWarn.TLabel").grid(row=1, column=1, sticky="w", padx=(0, 10), pady=2)

        ttk.Label(stats_box, text="Errors:", style="StatTitle.TLabel").grid(row=1, column=2, sticky="w", padx=(4, 2), pady=2)
        ttk.Label(stats_box, textvariable=self.err_var, style="StatErr.TLabel").grid(row=1, column=3, sticky="w", padx=(0, 4), pady=2)

        # Controls & Action Buttons
        btn_action_box = ttk.Frame(self.main_container, style="Root.TFrame")
        btn_action_box.pack(fill="x", pady=(0, 6))

        self.btn_start = tk.Button(
            btn_action_box,
            text="▶  START DOWNLOAD",
            bg=ACCENT_GREEN,
            fg=TEXT_WHITE,
            activebackground=ACCENT_GREEN_HOVER,
            activeforeground=TEXT_WHITE,
            relief="flat",
            font=(UI_FONT, 10, "bold"),
            cursor="hand2",
            command=self._toggle_start_stop,
            padx=18,
            pady=5,
        )
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_pause = tk.Button(
            btn_action_box,
            text="⏸  PAUSE",
            bg=ACCENT_ORANGE,
            fg="#000000",
            activebackground=ACCENT_ORANGE_HOVER,
            activeforeground="#000000",
            disabledforeground="#555555",
            relief="flat",
            font=(UI_FONT, 10, "bold"),
            cursor="hand2",
            command=self._toggle_pause_resume,
            state="disabled",
            padx=14,
            pady=5,
        )
        self.btn_pause.pack(side="left")

        # Progress bar & Status line
        prog_bar_box = ttk.Frame(self.main_container, style="Root.TFrame")
        prog_bar_box.pack(fill="x", pady=(0, 6))

        self.prog_bar = ttk.Progressbar(prog_bar_box, style="Green.Horizontal.TProgressbar", maximum=100)
        self.prog_bar.pack(fill="x", ipady=2, pady=(0, 2))

        status_lbl = ttk.Label(prog_bar_box, textvariable=self.status_var, style="Status.TLabel")
        status_lbl.pack(anchor="w")

        # Logs Card
        logs_card = ttk.LabelFrame(self.main_container, text="  EXECUTION LOGS  ", padding=(10, 5))
        logs_card.pack(fill="both", expand=True, pady=(0, 6))

        log_top = ttk.Frame(logs_card, style="Card.TFrame")
        log_top.pack(fill="x", pady=(0, 3))
        ttk.Label(log_top, text="Real-time activity and network status:", font=(UI_FONT, 8), foreground=TEXT_MUTED).pack(side="left")
        tk.Button(
            log_top,
            text="Clear Logs",
            bg=BTN_SEC_BG,
            fg=TEXT_MAIN,
            activebackground=BTN_SEC_HOVER,
            relief="flat",
            font=(UI_FONT, 8),
            cursor="hand2",
            command=self._clear_logs,
            padx=8,
            pady=1,
        ).pack(side="right")

        self.txt_logs = tk.Text(
            logs_card,
            bg=INPUT_BG,
            fg=TEXT_WHITE,
            font=(MONO_FONT, 9),
            relief="flat",
            wrap="word",
            state="disabled",
            height=6,
        )
        self.txt_logs.pack(fill="both", expand=True)

        # Bottom status bar
        status_bar = ttk.Frame(self.main_container, style="Root.TFrame")
        status_bar.pack(fill="x")
        ttk.Label(status_bar, textvariable=self.status_var, style="Sub.TLabel").pack(side="left")

    def _save_url(self):
        url = self.url_var.get().strip()
        if not url:
            url = DEFAULT_URL
            self.url_var.set(url)
        save_app_config({"bills_url": url})
        self.status_var.set(f"Bills URL saved: {url}")
        if hasattr(self, "btn_save_url"):
            self.btn_save_url.configure(text="✔ Saved", bg="#2ea043")
            self.after(1500, lambda: self.btn_save_url.configure(text="Save", bg=ACCENT_GREEN) if self.winfo_exists() and self.btn_save_url.winfo_exists() else None)

    def _reset_url(self):
        self.url_var.set(DEFAULT_URL)
        save_app_config({"bills_url": DEFAULT_URL})
        self.status_var.set("Bills URL reset to default.")
        if hasattr(self, "btn_save_url"):
            self.btn_save_url.configure(text="✔ Saved", bg="#2ea043")
            self.after(1500, lambda: self.btn_save_url.configure(text="Save", bg=ACCENT_GREEN) if self.winfo_exists() and self.btn_save_url.winfo_exists() else None)

    def _download_template(self):
        default_name = "EBill_Sample_Template.xlsx"
        desktop_dir = os.path.join(os.environ.get("USERPROFILE", "C:"), "Desktop")
        dest_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Excel Template",
            initialfile=default_name,
            initialdir=desktop_dir if os.path.exists(desktop_dir) else None,
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook (*.xlsx)", "*.xlsx"), ("All Files (*.*)", "*.*")],
        )
        if not dest_path:
            return

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Bill Accounts"

            headers = ["Account Number", "Sr No", "Status"]
            ws.append(headers)

            # Styling header
            header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
            header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
            header_align = Alignment(horizontal="center", vertical="center")

            for col_num in range(1, 4):
                cell = ws.cell(row=1, column=col_num)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_align

            # Sample rows for user guidance
            samples = [
                ("01234567890123", 1, ""),
                ("01234567890124", 2, ""),
                ("01234567890125", 3, ""),
            ]
            for row in samples:
                ws.append(list(row))

            for r in range(2, 5):
                ws.cell(row=r, column=1).number_format = "@"
                ws.cell(row=r, column=1).alignment = Alignment(horizontal="left")
                ws.cell(row=r, column=2).alignment = Alignment(horizontal="center")

            ws.column_dimensions["A"].width = 24
            ws.column_dimensions["B"].width = 12
            ws.column_dimensions["C"].width = 18

            wb.save(dest_path)
            self.excel_var.set(dest_path)
            save_app_config({"last_excel": dest_path})
            self.status_var.set(f"Excel template saved: {os.path.basename(dest_path)}")

            ans = messagebox.askyesno(
                "Template Saved",
                f"Excel template generated successfully!\n\n"
                f"Saved to: {dest_path}\n\n"
                f"It has been selected as your active Excel input file.\n"
                f"Would you like to open it now in Excel?",
                parent=self
            )
            if ans:
                try:
                    os.startfile(dest_path)
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to generate template:\n{e}", parent=self)

    def _browse_excel(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select Excel File",
            filetypes=[("Excel Files (*.xlsx)", "*.xlsx"), ("All Files (*.*)", "*.*")]
        )
        if path:
            self.excel_var.set(path)
            save_app_config({"last_excel": path})

    def _browse_output_folder(self):
        path = filedialog.askdirectory(parent=self, title="Select Output Folder")
        if path:
            self.out_var.set(path)
            save_app_config({"output_folder": path})

    def _open_output_folder(self):
        folder = self.out_var.get().strip()
        if folder and os.path.exists(folder):
            try:
                os.startfile(folder)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open folder:\n{e}", parent=self)
        else:
            messagebox.showwarning("Folder Not Found", "The output folder does not exist yet.", parent=self)

    def _clear_logs(self):
        self.txt_logs.configure(state="normal")
        self.txt_logs.delete("1.0", "end")
        self.txt_logs.configure(state="disabled")

    def _append_log(self, msg: str):
        self.txt_logs.configure(state="normal")
        self.txt_logs.insert("end", f"{msg}\n")
        self.txt_logs.see("end")
        self.txt_logs.configure(state="disabled")

    def _toggle_start_stop(self):
        if self.btn_start.cget("text").startswith("▶"):
            excel = self.excel_var.get().strip()
            if not excel or not os.path.exists(excel):
                messagebox.showerror("Missing Excel File", "Please select a valid Excel (.xlsx) file first.", parent=self)
                return

            out = self.out_var.get().strip()
            if not out:
                messagebox.showerror("Missing Output Folder", "Please specify an output folder.", parent=self)
                return

            url = self.url_var.get().strip() or DEFAULT_URL
            save_app_config({
                "bills_url": url,
                "add_sr": self.chk_sr_var.get(),
                "separate_pdf": self.chk_sep_var.get(),
                "headless": self.chk_headless_var.get(),
            })

            self.total_var.set("0")
            self.ok_var.set("0")
            self.not_found_var.set("0")
            self.err_var.set("0")
            self.prog_bar["value"] = 0

            self.stop_event.clear()
            self.pause_event.clear()

            self.btn_start.configure(text="■  STOP DOWNLOAD", bg=ACCENT_RED, activebackground=ACCENT_RED_HOVER)
            self.btn_pause.configure(state="normal", text="⏸  PAUSE")
            self.status_var.set("Processing bills...")

            job = {
                "excel_path": excel,
                "out_folder": out,
                "url": url,
                "headless": True,
                "add_sr": self.chk_sr_var.get(),
                "separate": self.chk_sep_var.get(),
            }

            engine = BillWorkerEngine(job, self.events, self.stop_event, self.pause_event)
            self.worker_thread = threading.Thread(target=engine.run, daemon=True)
            self.worker_thread.start()
        else:
            self.stop_event.set()
            self.btn_start.configure(state="disabled", text="Stopping...")
            self.status_var.set("Stopping background worker...")

    def _toggle_pause_resume(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.configure(text="⏸  PAUSE")
            self.status_var.set("Resuming processing...")
            self._append_log("▶ Worker resumed.")
        else:
            self.pause_event.set()
            self.btn_pause.configure(text="▶  RESUME")
            self.status_var.set("Worker paused.")
            self._append_log("⏸ Worker paused.")

    def drain_events(self):
        try:
            while True:
                msg_type, payload = self.events.get_nowait()
                if msg_type == "log":
                    self._append_log(payload)
                elif msg_type == "progress":
                    cur, total, saved, not_found, errors = payload
                    self.total_var.set(str(total))
                    self.ok_var.set(str(saved))
                    self.not_found_var.set(str(not_found))
                    self.err_var.set(str(errors))
                    self.prog_text_var.set(f"{cur} / {total} bills")
                    self.stats_var.set(f"Saved: {saved}  |  Not Found: {not_found}  |  Errors: {errors}")
                    if total > 0:
                        pct = (cur / total) * 100
                        self.prog_bar["value"] = pct
                elif msg_type == "error":
                    self.status_var.set(f"Error: {payload}")
                elif msg_type == "finished":
                    self._on_worker_finished()
        except queue.Empty:
            pass

        if self.winfo_exists():
            self.after(50, self.drain_events)

    def _on_worker_finished(self):
        self.btn_start.configure(state="normal", text="▶  START DOWNLOAD", bg=ACCENT_GREEN, activebackground=ACCENT_GREEN_HOVER)
        self.btn_pause.configure(state="disabled", text="⏸  PAUSE")
        self.status_var.set("Completed.")

        # Notification dialog
        ans = messagebox.askyesno(
            "Download Completed",
            "E-Bill Downloader has finished processing your bills!\n\nWould you like to open the output folder now?",
            parent=self
        )
        if ans:
            self._open_output_folder()


# ──────────────────────────────────────────────────────────────
#  APPLICATION ENTRY POINT
# ──────────────────────────────────────────────────────────────
def start_app():
    app = EBillDownloaderApp()
    try:
        if app.winfo_exists():
            app.mainloop()
    except Exception:
        pass


if __name__ == "__main__":
    start_app()
