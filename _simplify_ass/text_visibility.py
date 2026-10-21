"""Canonical existing result shared by independent text-visibility producers."""
from __future__ import annotations
from dataclasses import dataclass
from .event_model import Event


@dataclass(frozen=True)
class TextVisibilityResult:
    """Retained text events, a removal count and accepted visibility updates.

    Passes borrow the input visibility map. Callers adopt events and apply
    visibility_updates before the next consumer. The delta contains accepted
    caption assignments, including equal-value writes; source history remains.
    """
    events: list[Event]
    removed_count: int
    visibility_updates: dict[int,str]
