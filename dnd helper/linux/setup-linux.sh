#!/bin/sh
set -eu
helper_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 "$helper_dir/dnd_helper.py" install-linux
