#!/usr/bin/env python3
"""Update an installed set of subtitle tools from GitHub main."""

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.request import Request, urlopen


REPOSITORY = "cnieuweboer/Simplify-ass-subtitles"
API = f"https://api.github.com/repos/{REPOSITORY}"
RAW = f"https://raw.githubusercontent.com/{REPOSITORY}"
TOOLS = ("simplify_subtitles", "subtitle_tracks", "subtitle_properties", "sync_fonts")
MAX_DOWNLOAD = 16 * 1024 * 1024


def download(url):
    request = Request(url, headers={"User-Agent": "subtitle-tools-update"})
    with urlopen(request, timeout=30) as response:
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise RuntimeError("GitHub response exceeds the download limit")
    return data


def commit_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise RuntimeError("GitHub returned an invalid revision")
    return value


def selected_file(path):
    parts = PurePosixPath(path).parts
    if not parts or ".." in parts or "\\" in path or PurePosixPath(path).is_absolute():
        return False
    return ((len(parts) == 1 and path.endswith(".py"))
            or (len(parts) == 3 and parts[:2] == ("installer", "windows") and path.endswith(".py"))
            or (len(parts) == 4 and parts[:3] == ("installer", "windows", "bin") and path.endswith(".cmd")))


def fetch_checkout(directory):
    revision = json.loads(download(API + "/commits/main"))
    sha = commit_sha(revision["sha"])
    tree_sha = commit_sha(revision["commit"]["tree"]["sha"])
    tree = json.loads(download(API + f"/git/trees/{tree_sha}?recursive=1"))
    if tree.get("truncated"):
        raise RuntimeError("GitHub returned an incomplete repository file list")
    files = {entry["path"]: entry for entry in tree["tree"]
             if entry.get("type") == "blob" and entry.get("mode") in ("100644", "100755")
             and selected_file(entry["path"])}
    required = ({tool + ".py" for tool in (*TOOLS, "simplify_ass")}
                | {f"installer/windows/{name}.py" for name in ("install", "subtitle_tools_update", "subtitle_tools")}
                | {f"installer/windows/bin/{tool}.cmd" for tool in (*TOOLS, "subtitle_tools_update", "subtitle_tools")})
    if not required.issubset(files):
        raise RuntimeError("GitHub revision is missing required tool or launcher files")
    print(f"GitHub revision: {sha[:12]}", flush=True)
    print(f"Downloading {len(files)} files...", flush=True)
    for name, entry in sorted(files.items()):
        data = download(RAW + f"/{sha}/{name}")
        digest = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if digest != entry["sha"]:
            raise RuntimeError(f"GitHub content verification failed: {name}")
        if name.endswith(".py"):
            compile(data.decode("utf-8-sig"), name, "exec")
        destination = directory.joinpath(*PurePosixPath(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return sha


def update(target):
    markers = [target / "simplify-ass" / (tool + ".py") for tool in (*TOOLS, "simplify_ass")]
    if not any(path.is_file() for path in markers):
        raise RuntimeError(f"No subtitle-tools installation found in {target}. Run the installer first.")
    print(f"Updating installation: {target}", flush=True)
    with tempfile.TemporaryDirectory(prefix="subtitle-tools-download-") as temporary:
        checkout = Path(temporary)
        sha = fetch_checkout(checkout)
        spec = importlib.util.spec_from_file_location("subtitle_tools_downloaded_installer",
                                                    checkout / "installer/windows/install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.install(checkout, target)
    print(f"Updated subtitle tools to {sha[:12]}. PATH and unrelated files were left unchanged.")
    return sha


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    default = here.parent if here.name == "simplify-ass" else Path(r"C:\Tools")
    parser.add_argument("--target", type=Path, default=default, help="installation root (default: this installation)")
    args = parser.parse_args(argv)
    try:
        update(args.target.expanduser().resolve())
    except KeyboardInterrupt:
        print("\nUpdate cancelled.")
        return 130
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, SyntaxError) as error:
        print(f"Update failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
