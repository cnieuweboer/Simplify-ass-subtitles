"""Identify a standalone historical engine or a current multi-file engine."""
from pathlib import Path
import hashlib


def runtime_manifest(engine):
    """Return sorted sibling-relative source hashes, excluding generated caches.

    Historical engines without a sibling implementation package retain their
    single-file identity. Callers compare complete manifests before/after runs
    to detect edits, additions and removals, not just changes to the entry point.
    """
    engine = Path(engine).resolve()
    package = engine.parent / "_simplify_ass"
    files = [engine]
    if package.is_dir():
        files.extend(package.rglob("*.py"))
    return {p.relative_to(engine.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}
