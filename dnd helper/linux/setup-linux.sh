#!/bin/sh
set -eu
# Default: this installer is copied beside the Python tools.
# Or provide their folder explicitly: sh setup-linux.sh /path/to/tools
installer_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -gt 0 ]; then target_dir=$1; else target_dir=$installer_dir; fi
python3 - "$target_dir" <<'PY'
from pathlib import Path
import sys

directory = Path(sys.argv[1]).expanduser().resolve()
if not directory.is_dir():
    raise SystemExit("Choose an existing folder containing the Python tools.")

WRAPPER = r'''#!/bin/sh
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 2
script="$script_dir/__TOOL__.py"
status=0
if [ ! -f "$script" ]; then
    printf 'Missing Python script: %s\n' "$script"
    status=2
else
    if [ "$#" -eq 0 ]; then set -- "$script_dir"; fi
    for folder in "$@"; do
        if [ ! -d "$folder" ]; then
            printf 'Drop a folder containing MKVs: %s\n' "$folder"
            status=2
            break
        fi
    done
    if [ "$status" -eq 0 ]; then
        for folder in "$@"; do
            python3 "$script" "$folder" || status=1
        done
    fi
fi
if [ -t 0 ]; then
    printf '\nPress Enter to close: '
    read -r answer || true
fi
exit "$status"
'''

def desktop_quote(value):
    value = value.replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    return '"' + value.replace("\\", "\\\\") + '"'

created = 0
for tool, label in (("subtitle_flags", "Subtitle flags"),
                    ("remove_subtitles", "Remove subtitles"), ("sync_fonts", "Sync fonts"),
                    ("simplify_subtitles", "Simplify subtitles")):
    if not (directory / (tool + ".py")).is_file():
        continue
    wrapper = directory / (tool + ".sh")
    wrapper.write_text(WRAPPER.replace("__TOOL__", tool), encoding="utf-8")
    wrapper.chmod(0o755)
    launcher = directory / (tool + ".desktop")
    launcher.write_text(
        "[Desktop Entry]\nType=Application\n" + f"Name={label}\n"
        "Comment=Drop folders containing MKVs here\n"
        f"Exec=/bin/sh {desktop_quote(str(wrapper))} %f\n"
        "Terminal=true\nIcon=video-x-generic\nMimeType=inode/directory;\n"
        "Categories=AudioVideo;\n", encoding="utf-8")
    launcher.chmod(0o755)
    print(f"Created: {launcher}")
    created += 1
if not created:
    raise SystemExit("No subtitle_flags.py, remove_subtitles.py, sync_fonts.py, or simplify_subtitles.py found.")
print("Allow launching/trust the desktop launchers if your file manager asks.")
print("Rerun setup after moving the folder.")
PY
