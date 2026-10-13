#!/usr/bin/env python3
"""Launch standalone MKV tools from dropped folders; create Linux launchers."""

import argparse
from pathlib import Path
import subprocess
import sys


TOOLS = {
    "subtitle_flags": "Subtitle flags",
    "remove_subtitles": "Remove subtitles",
    "sync_fonts": "Sync fonts",
}
HELPER_DIR = Path(__file__).resolve().parent
ROOT = HELPER_DIR.parent


def desktop_quote(value):
    # Escape both the desktop-entry value and Exec's quoted argument syntax.
    value = value.replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    return '"' + value.replace("\\", "\\\\") + '"'


def install_linux():
    directory = HELPER_DIR / "linux"
    directory.mkdir(exist_ok=True)
    for tool, label in TOOLS.items():
        launcher = directory / (tool + ".desktop")
        command = " ".join((desktop_quote(sys.executable),
                            desktop_quote(str(HELPER_DIR / "dnd_helper.py")),
                            tool, "--pause", "%F"))
        launcher.write_text(
            "[Desktop Entry]\nType=Application\n" + f"Name={label}\n"
            "Comment=Drop folders containing MKVs here\n"
            f"Exec={command}\nTerminal=true\nIcon=video-x-generic\n"
            "MimeType=inode/directory;\nCategories=AudioVideo;\n", encoding="utf-8")
        launcher.chmod(0o755)
        print(f"Created: {launcher}")
    print("Allow launching/trust each launcher if your file manager asks.")
    print("If your desktop does not support drops, use Open With or a terminal.")
    return 0


def run_tool(tool, paths):
    script = ROOT / (tool + ".py")
    if not script.is_file():
        print(f"ERROR: Missing script: {script}. Keep 'dnd helper' beside the Python tools.")
        return 2
    folders = []
    for value in paths or [str(ROOT)]:
        folder = Path(value).expanduser().resolve()
        if not folder.is_dir():
            print(f"ERROR: Drop a folder containing MKVs: {value}")
            return 2
        if folder not in folders:
            folders.append(folder)
    status = 0
    for folder in folders:
        print(f"\n{TOOLS[tool]}: {folder}", flush=True)
        result = subprocess.run([sys.executable, str(script), str(folder)], cwd=folder)
        if result.returncode:
            status = 1
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=[*TOOLS, "install-linux"])
    parser.add_argument("folders", nargs="*", help="dropped folders; default: beside the tools")
    parser.add_argument("--pause", action="store_true", help="keep the terminal open when finished")
    args = parser.parse_intermixed_args(argv)
    try:
        if sys.version_info < (3, 10):
            print("ERROR: Install Python 3.10 or newer.")
            return 2
        if args.tool == "install-linux":
            return install_linux()
        return run_tool(args.tool, args.folders)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except OSError as error:
        print(f"ERROR: {error}")
        return 2
    finally:
        if args.pause and sys.stdin.isatty():
            try:
                input("\nPress Enter to close: ")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
