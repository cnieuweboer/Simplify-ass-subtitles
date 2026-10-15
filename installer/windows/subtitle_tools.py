#!/usr/bin/env python3
"""Select a subtitle tool and forward its command-line options."""

import os
from pathlib import Path
import subprocess
import sys


OPTIONS = (
    ("Simplify subtitles", "simplify_subtitles.py"),
    ("Remove subtitles", "remove_subtitles.py"),
    ("Set or remove default/forced flags", "subtitle_flags.py"),
    ("Synchronize fonts", "sync_fonts.py"),
    ("Update", "subtitle_tools_update.py"),
)
WINDOWS = os.name == "nt"


def choose():
    allowed = ("1", "2", "3", "4", "5", "q")
    prompt = "Choose 1-5 (q to cancel): "
    if WINDOWS and sys.stdin.isatty():
        import msvcrt
        print(prompt, end="", flush=True)
        while True:
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue
            if key == "\x03":
                raise KeyboardInterrupt
            if key.lower() in allowed:
                print(key.lower(), flush=True)
                return key.lower()
    while True:
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            return "q"
        if not answer:
            return "q"
        if answer in allowed:
            return answer


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    print("Subtitle tools", flush=True)
    for number, (label, _) in enumerate(OPTIONS, 1):
        print(f"  {number}. {label}", flush=True)
    print("  q. Cancel", flush=True)
    try:
        selected = choose()
        if selected == "q":
            return 0
        script = Path(__file__).resolve().parent / OPTIONS[int(selected) - 1][1]
        if not script.is_file():
            print(f"Missing installed tool: {script}. Run subtitle_tools_update or reinstall.")
            return 2
        if selected == "5":
            command = [sys.executable, str(script)]
            if arguments:
                print("Update uses this installation; media-processing options are ignored.", flush=True)
        else:
            command = [sys.executable, str(script), "--input", str(Path.cwd()), *arguments]
        process = subprocess.Popen(command)
        try:
            return process.wait()
        except KeyboardInterrupt:
            # The console also sends Ctrl+C to the tool; let its cleanup finish.
            print("\nStopping selected tool...", flush=True)
            try:
                process.wait()
            except KeyboardInterrupt:
                process.kill()
                process.wait()
            return 130
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as error:
        print(f"Could not start selected tool: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
