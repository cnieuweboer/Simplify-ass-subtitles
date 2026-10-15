#!/usr/bin/env python3
"""Install the Windows PATH launchers and Python tools from this checkout."""

import argparse
from pathlib import Path
import shutil
import tempfile


TOOLS = ("simplify_subtitles", "remove_subtitles", "subtitle_flags", "sync_fonts")


def install(repository, target):
    launchers = repository / "installer" / "windows" / "bin"
    tool_dir = target / "simplify-ass"
    bin_dir = target / "bin"
    files = [(repository / (tool + ".py"), tool_dir / (tool + ".py")) for tool in TOOLS]
    files.append((repository / "simplify_ass.py", tool_dir / "simplify_ass.py"))
    files.extend((launchers / (tool + ".cmd"), bin_dir / (tool + ".cmd")) for tool in TOOLS)
    # Check the complete source set before creating or updating anything.
    for source, destination in files:
        if not source.is_file():
            raise RuntimeError(f"Missing installer source: {source}. Download or clone the complete repository first.")
        if destination.is_dir():
            raise RuntimeError(f"A folder occupies an installed file's path: {destination}")
    bin_dir.mkdir(parents=True, exist_ok=True)
    tool_dir.mkdir(parents=True, exist_ok=True)
    for source, destination in files:
        if source.resolve() == destination.resolve():
            continue
        # Replace individual files only after their copies are complete.
        with tempfile.NamedTemporaryFile(prefix=".install-", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            shutil.copy2(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return bin_dir, tool_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, help="installation root (default: C:\\Tools)")
    parser.add_argument("--target", type=Path, help="installation root instead of C:\\Tools")
    args = parser.parse_args(argv)
    if args.folder is not None and args.target is not None:
        parser.error("Specify the installation root positionally or with --target, not both.")
    target = (args.target or args.folder or Path(r"C:\Tools")).expanduser().resolve()
    repository = Path(__file__).resolve().parents[2]
    try:
        bin_dir, tool_dir = install(repository, target)
    except (OSError, RuntimeError) as error:
        print(f"Installation failed: {error}")
        return 1
    print(f"Installed Python tools: {tool_dir}")
    print(f"Installed CMD launchers: {bin_dir}")
    print(f"\nAdd this folder to your user PATH, then open a new terminal:\n  {bin_dir}")
    print("PATH was not changed. Add only the bin folder, not simplify-ass.")
    print("\nRequired: Python 3.10+ and MKVToolNix on PATH.")
    print("Install Python dependencies with your chosen interpreter:")
    print("  py -3 -m pip install Pillow fonttools uharfbuzz")
    print("Use python instead of py -3 if that is your Python command.")
    print("\nCommands default to the current folder. Override it with -i / --input.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
