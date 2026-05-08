# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""OS-aware log file conveniences shared across commands."""

import os
import subprocess
import sys
import tempfile


def default_log_directory() -> str:
    """Return the default directory for log files based on the current OS."""
    if sys.platform in ("darwin", "win32"):
        return tempfile.gettempdir()
    return os.path.expanduser("~/Documents")


def open_live_log_viewer(log_file_path: str):
    """Open a platform-native live log viewer for the given file.

    macOS: Console.app via `open -a Console <path>` — natively follows live log files.
    Windows: PowerShell + `Get-Content -Wait`.

    Returns (success: bool, message: str).
    """
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Console", log_file_path])
            return True, "Opened live log viewer in Console.app"

        if sys.platform == "win32":
            command = f'Get-Content -Path "{log_file_path}" -Wait'
            subprocess.Popen(
                [
                    "powershell",
                    "-NoExit",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                ]
            )
            return True, "Opened live log viewer in PowerShell"

        return (
            False,
            "Live log viewer auto-open is currently supported on macOS and Windows only",
        )
    except Exception as e:
        return False, f"Failed to open live log viewer: {e}"
