"""Master Build Script: Generates icons, compiles the application, and builds
the standalone Windows Setup installer (TruthTableSynthesizer_Setup.exe).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile

from create_icons import generate_all_icons


def log(msg: str) -> None:
    print(f"\n[BUILD] {msg}")


def main() -> None:
    root_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root_dir)

    # 1. Generate Icons
    log("Step 1: Generating multi-resolution icon assets (.ico & .png)...")
    generate_all_icons("assets")
    ico_path = os.path.join("assets", "icon.ico")
    assert os.path.exists(ico_path), "icon.ico was not created!"

    # 2. Compile Application Executable with PyInstaller (if not already compiled or out of date)
    dist_app = os.path.join("dist", "TruthTableSynthesizer")
    exe_file = os.path.join(dist_app, "TruthTableSynthesizer.exe")

    if not os.path.exists(exe_file):
        log("Step 2: Compiling TruthTableSynthesizer.exe with PyInstaller...")
        cmd_app = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--onedir",
            "--windowed",
            "--name", "TruthTableSynthesizer",
            "--icon", ico_path,
            "--add-data", f"assets{os.pathsep}assets",
            "truth_table_gui.py",
        ]
        res = subprocess.run(cmd_app, check=True)
    else:
        log("Step 2: Found existing compiled TruthTableSynthesizer.exe.")

    # Copy assets into dist_app folder as well
    dist_assets = os.path.join(dist_app, "assets")
    os.makedirs(dist_assets, exist_ok=True)
    shutil.copy2(os.path.join("assets", "icon.ico"), os.path.join(dist_assets, "icon.ico"))
    shutil.copy2(os.path.join("assets", "icon.png"), os.path.join(dist_assets, "icon.png"))

    # 3. Create payload.zip from dist/TruthTableSynthesizer
    log("Step 3: Creating compressed payload.zip from application binaries...")
    payload_zip = "payload.zip"
    with zipfile.ZipFile(payload_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(dist_app):
            for file in files:
                full_p = os.path.join(root, file)
                rel_p = os.path.relpath(full_p, dist_app)
                zf.write(full_p, rel_p)

    payload_size_mb = os.path.getsize(payload_zip) / (1024 * 1024)
    print(f"  -> Created payload.zip ({payload_size_mb:.2f} MB)")

    # 4. Compile the Standalone Installer Setup EXE
    log("Step 4: Compiling TruthTableSynthesizer_Setup.exe with PyInstaller...")
    cmd_setup = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "TruthTableSynthesizer_Setup",
        "--icon", ico_path,
        "--add-data", f"{payload_zip}{os.pathsep}.",
        "--add-data", f"assets{os.pathsep}assets",
        "installer_wizard.py",
    ]
    subprocess.run(cmd_setup, check=True)

    # 5. Create Portable ZIP distribution
    log("Step 5: Packaging Portable ZIP distribution...")
    portable_zip = os.path.join("dist", "TruthTableSynthesizer_v1.0.0_Portable.zip")
    with zipfile.ZipFile(portable_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(dist_app):
            for file in files:
                full_p = os.path.join(root, file)
                rel_p = os.path.join("TruthTableSynthesizer", os.path.relpath(full_p, dist_app))
                zf.write(full_p, rel_p)
    print(f"  -> Created {portable_zip}")

    # Clean temporary payload.zip
    if os.path.exists(payload_zip):
        os.remove(payload_zip)

    log("=" * 64)
    log("BUILD COMPLETE! Installer & Distribution Files Created:")
    log(f"  1. GUI Installer Setup : {os.path.abspath('dist/TruthTableSynthesizer_Setup.exe')}")
    log(f"  2. Portable Folder     : {os.path.abspath('dist/TruthTableSynthesizer')}")
    log(f"  3. Portable ZIP        : {os.path.abspath(portable_zip)}")
    log("=" * 64)


if __name__ == "__main__":
    main()

