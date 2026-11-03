"""Truth Table to Logic Circuit Synthesizer - Windows Setup Wizard
===================================================================
A standalone Windows installer with custom icons, desktop shortcut,
start menu integration, and uninstaller.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


APP_NAME = "Truth Table to Logic Circuit Synthesizer"
SHORT_NAME = "TruthTableSynthesizer"
EXE_NAME = "TruthTableSynthesizer.exe"
VERSION = "1.0.0"


def get_bundle_dir() -> str:
    """Return the base directory for resources (dev or PyInstaller _MEIPASS)."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def default_install_dir() -> str:
    """Return the default Windows user application directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "AppData", "Local")
    return os.path.join(local_app_data, "Programs", SHORT_NAME)


def create_windows_shortcut(
    target_path: str,
    shortcut_path: str,
    icon_path: str | None = None,
    description: str = "",
    working_dir: str | None = None,
) -> bool:
    """Create a Windows .lnk shortcut using WScript.Shell via PowerShell or win32com."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(shortcut_path)), exist_ok=True)
        # Try win32com first
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            sc = shell.CreateShortCut(shortcut_path)
            sc.TargetPath = target_path
            sc.WorkingDirectory = working_dir or os.path.dirname(target_path)
            if icon_path and os.path.exists(icon_path):
                sc.IconLocation = f"{icon_path},0"
            if description:
                sc.Description = description
            sc.save()
            return True
        except Exception:
            pass

        # Fallback to PowerShell
        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{shortcut_path}'); "
            f"$s.TargetPath = '{target_path}'; "
            f"$s.WorkingDirectory = '{working_dir or os.path.dirname(target_path)}'; "
        )
        if icon_path and os.path.exists(icon_path):
            ps_cmd += f"$s.IconLocation = '{icon_path},0'; "
        if description:
            ps_cmd += f"$s.Description = '{description}'; "
        ps_cmd += "$s.Save()"

        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return res.returncode == 0
    except Exception as exc:
        print(f"Warning: Could not create shortcut '{shortcut_path}': {exc}")
        return False


def perform_installation(
    target_dir: str,
    desktop_shortcut: bool = True,
    start_shortcut: bool = True,
    progress_callback=None,
) -> tuple[bool, str]:
    """Extract or copy application files, create shortcuts and uninstaller."""
    bundle_dir = get_bundle_dir()

    def update(pct: float, msg: str):
        if progress_callback:
            progress_callback(pct, msg)

    try:
        update(5, "Preparing target directory...")
        os.makedirs(target_dir, exist_ok=True)

        payload_zip = os.path.join(bundle_dir, "payload.zip")
        dist_app_dir = os.path.join(bundle_dir, "dist", SHORT_NAME)
        local_app_dir = os.path.join(bundle_dir, SHORT_NAME)

        # 1. Extract payload or copy files
        if os.path.isfile(payload_zip):
            update(15, "Extracting application package...")
            with zipfile.ZipFile(payload_zip, "r") as zf:
                members = zf.infolist()
                total = len(members)
                for i, m in enumerate(members):
                    zf.extract(m, target_dir)
                    if i % 10 == 0:
                        update(15 + int((i / max(1, total)) * 55), f"Extracting {m.filename}...")
        elif os.path.isdir(dist_app_dir):
            update(20, "Copying compiled application binaries...")
            shutil.copytree(dist_app_dir, target_dir, dirs_exist_ok=True)
        elif os.path.isdir(local_app_dir):
            update(20, "Copying application binaries...")
            shutil.copytree(local_app_dir, target_dir, dirs_exist_ok=True)
        else:
            # Source mode fallback: copy python scripts & assets
            update(20, "Installing application scripts and assets...")
            for fn in ["truth_table_gui.py", "truth_table_system.py", "README.md"]:
                src = os.path.join(bundle_dir, fn)
                if os.path.exists(src):
                    shutil.copy2(src, target_dir)

        # 2. Ensure assets directory exists in target
        update(75, "Installing icon assets...")
        target_assets = os.path.join(target_dir, "assets")
        os.makedirs(target_assets, exist_ok=True)

        src_assets = os.path.join(bundle_dir, "assets")
        if os.path.isdir(src_assets):
            shutil.copytree(src_assets, target_assets, dirs_exist_ok=True)

        target_ico = os.path.join(target_assets, "icon.ico")
        target_exe = os.path.join(target_dir, EXE_NAME)

        # If EXE does not exist in target (source fallback), create a batch launcher
        if not os.path.exists(target_exe):
            launcher_bat = os.path.join(target_dir, "TruthTableSynthesizer.bat")
            with open(launcher_bat, "w", encoding="utf-8") as f:
                f.write('@echo off\ncd /d "%~dp0"\npython truth_table_gui.py %*\n')
            target_exe = launcher_bat

        # 3. Create Desktop Shortcut
        user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        desktop_dir = os.path.join(user_profile, "Desktop")
        desktop_lnk = os.path.join(desktop_dir, f"{APP_NAME}.lnk")

        if desktop_shortcut:
            update(82, "Creating Desktop shortcut with custom icon...")
            create_windows_shortcut(
                target_path=target_exe,
                shortcut_path=desktop_lnk,
                icon_path=target_ico,
                description=APP_NAME,
                working_dir=target_dir,
            )

        # 4. Create Start Menu Shortcut
        app_data = os.environ.get("APPDATA", os.path.join(user_profile, "AppData", "Roaming"))
        start_dir = os.path.join(app_data, r"Microsoft\Windows\Start Menu\Programs", APP_NAME)
        start_lnk = os.path.join(start_dir, f"{APP_NAME}.lnk")
        uninstall_lnk = os.path.join(start_dir, "Uninstall Truth Table Synthesizer.lnk")

        if start_shortcut:
            update(88, "Creating Start Menu shortcut...")
            os.makedirs(start_dir, exist_ok=True)
            create_windows_shortcut(
                target_path=target_exe,
                shortcut_path=start_lnk,
                icon_path=target_ico,
                description=APP_NAME,
                working_dir=target_dir,
            )

        # 5. Generate Uninstaller
        update(94, "Creating uninstaller...")
        uninstall_bat = os.path.join(target_dir, "Uninstall.bat")
        with open(uninstall_bat, "w", encoding="utf-8") as f:
            f.write(f"""@echo off
title Uninstalling {APP_NAME}...
echo ============================================================================
echo   Uninstalling {APP_NAME}
echo ============================================================================
echo.
echo Removing Desktop shortcut...
del /f /q "{desktop_lnk}" 2>nul
echo Removing Start Menu shortcuts...
del /f /q "{start_dir}\\*.lnk" 2>nul
rmdir /s /q "{start_dir}" 2>nul
echo Removing application files...
cd /d "%~dp0.."
timeout /t 1 /nobreak >nul
rmdir /s /q "{target_dir}" 2>nul
echo.
echo {APP_NAME} has been uninstalled successfully.
echo.
pause
""")

        if start_shortcut:
            create_windows_shortcut(
                target_path=uninstall_bat,
                shortcut_path=uninstall_lnk,
                icon_path=target_ico,
                description=f"Uninstall {APP_NAME}",
                working_dir=target_dir,
            )

        update(100, "Installation complete!")
        return True, target_exe

    except Exception as exc:
        return False, str(exc)


class InstallerWizardGUI:
    """Modern Tkinter Setup Wizard GUI."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} Setup")
        self.root.geometry("560x420")
        self.root.resizable(False, False)

        # Center on screen
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - 560) // 2)
        y = max(0, (sh - 420) // 2)
        self.root.geometry(f"560x420+{x}+{y}")

        # Set window icon
        bundle_dir = get_bundle_dir()
        ico_path = os.path.join(bundle_dir, "assets", "icon.ico")
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        # Variables
        self.target_dir_var = tk.StringVar(value=default_install_dir())
        self.desktop_var = tk.BooleanVar(value=True)
        self.start_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self) -> None:
        # Header banner (dark slate)
        header = tk.Frame(self.root, bg="#0f172a", height=80)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_lbl = tk.Label(
            header,
            text=f"⚡ {APP_NAME}",
            font=("Segoe UI", 13, "bold"),
            bg="#0f172a",
            fg="#f8fafc",
        )
        title_lbl.pack(anchor="w", padx=20, pady=(16, 2))

        sub_lbl = tk.Label(
            header,
            text=f"Version {VERSION}  •  Automatic Simplest Circuit Synthesis & Wiring CAD",
            font=("Segoe UI", 9),
            bg="#0f172a",
            fg="#94a3b8",
        )
        sub_lbl.pack(anchor="w", padx=20)

        # Main content area
        content = tk.Frame(self.root, padx=24, pady=16)
        content.pack(fill="both", expand=True)

        dest_frame = tk.LabelFrame(
            content,
            text=" Installation Directory ",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=10,
        )
        dest_frame.pack(fill="x", pady=(0, 14))

        entry = ttk.Entry(dest_frame, textvariable=self.target_dir_var, font=("Segoe UI", 9))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ttk.Button(dest_frame, text="Browse...", command=self._browse_dir)
        browse_btn.pack(side="right")

        opts_frame = tk.LabelFrame(
            content,
            text=" Shortcut Options ",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=10,
        )
        opts_frame.pack(fill="x", pady=(0, 14))

        cb1 = ttk.Checkbutton(
            opts_frame,
            text="Create Desktop Shortcut with custom icon",
            variable=self.desktop_var,
        )
        cb1.pack(anchor="w", pady=2)

        cb2 = ttk.Checkbutton(
            opts_frame,
            text="Create Start Menu Program Folder and Shortcut",
            variable=self.start_var,
        )
        cb2.pack(anchor="w", pady=2)

        cb3 = ttk.Checkbutton(
            opts_frame,
            text="Launch Truth Table Synthesizer when installation finishes",
            variable=self.launch_var,
        )
        cb3.pack(anchor="w", pady=2)

        # Progress bar
        self.prog_lbl = tk.Label(
            content,
            text="Click 'Install' to begin installation.",
            font=("Segoe UI", 9),
            fg="#475569",
        )
        self.prog_lbl.pack(anchor="w", pady=(0, 4))

        self.progress = ttk.Progressbar(content, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x")

        # Bottom action bar
        bot = tk.Frame(self.root, bg="#f1f5f9", height=50)
        bot.pack(fill="x", side="bottom")
        bot.pack_propagate(False)

        self.cancel_btn = ttk.Button(bot, text="Cancel", command=self.root.destroy)
        self.cancel_btn.pack(side="right", padx=(6, 20), pady=12)

        self.install_btn = ttk.Button(bot, text="Install Now", command=self._start_install)
        self.install_btn.pack(side="right", padx=6, pady=12)

    def _browse_dir(self) -> None:
        sel = filedialog.askdirectory(initialdir=self.target_dir_var.get())
        if sel:
            self.target_dir_var.set(os.path.join(sel, SHORT_NAME))

    def _start_install(self) -> None:
        self.install_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")

        def worker():
            def progress(pct, msg):
                self.root.after(0, lambda: self._update_progress(pct, msg))

            ok, res = perform_installation(
                target_dir=self.target_dir_var.get(),
                desktop_shortcut=self.desktop_var.get(),
                start_shortcut=self.start_var.get(),
                progress_callback=progress,
            )
            self.root.after(0, lambda: self._on_finish(ok, res))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, pct: float, msg: str) -> None:
        self.progress["value"] = pct
        self.prog_lbl.config(text=msg)

    def _on_finish(self, ok: bool, res: str) -> None:
        if ok:
            self.prog_lbl.config(text="✓ Installation successfully completed!", fg="#16a34a")
            self.install_btn.config(text="Finish", state="normal", command=self._finish_and_launch)
            self.cancel_btn.config(state="disabled")
            self._installed_exe = res
        else:
            self.prog_lbl.config(text=f"Installation failed: {res}", fg="#dc2626")
            self.install_btn.config(text="Retry", state="normal", command=self._start_install)
            self.cancel_btn.config(state="normal")
            messagebox.showerror("Installation Error", f"Installation encountered an error:\n\n{res}")

    def _finish_and_launch(self) -> None:
        if self.launch_var.get() and hasattr(self, "_installed_exe") and os.path.exists(self._installed_exe):
            try:
                subprocess.Popen([self._installed_exe], cwd=os.path.dirname(self._installed_exe))
            except Exception as exc:
                print(f"Could not auto-launch app: {exc}")
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} Installer")
    parser.add_argument("--silent", "-s", action="store_true", help="Install silently without GUI prompt")
    parser.add_argument("--dir", type=str, default=default_install_dir(), help="Target installation directory")
    parser.add_argument("--no-desktop", action="store_true", help="Do not create Desktop shortcut")
    parser.add_argument("--no-start", action="store_true", help="Do not create Start Menu shortcut")
    parser.add_argument("--launch", action="store_true", help="Launch application after silent installation")

    args = parser.parse_args()

    if args.silent:
        print(f"Installing {APP_NAME} to: {args.dir}")
        ok, res = perform_installation(
            target_dir=args.dir,
            desktop_shortcut=not args.no_desktop,
            start_shortcut=not args.no_start,
            progress_callback=lambda p, m: print(f"[{p:3.0f}%] {m}"),
        )
        if ok:
            print("Installation complete!")
            if args.launch and os.path.exists(res):
                subprocess.Popen([res], cwd=os.path.dirname(res))
            sys.exit(0)
        else:
            print(f"Installation failed: {res}", file=sys.stderr)
            sys.exit(1)

    app = InstallerWizardGUI()
    app.run()


if __name__ == "__main__":
    main()

