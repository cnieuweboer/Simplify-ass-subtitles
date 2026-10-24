"""Shared row evidence and phase-row results; producers retain their policies."""
from __future__ import annotations

from dataclasses import dataclass, field

from .event_model import Event


@dataclass
class TextRow:
    """Shared text, geometry and cue provenance for reconstruction and FX.

    Source rows retain their authored interval and alternate paint rows.
    Reconstructed/virtual rows carry the same anchors into effect removal;
    that stage never has to rediscover their fragment layout.
    """
    base: Event
    pieces: list[tuple[Event, str, tuple[float, float]]]
    paint_rows: list[list[Event]] = field(default_factory=list)
    source_anchors: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    foreground: list[Event] = field(default_factory=list)
    confirmed: bool = False
    virtual: bool = False
    # Optional protected cue core proved by source phase correspondence.
    # The overlap pass preserves every activation point inside this interval.
    # Timing proofs travel in returned row successors; passes borrow input rows.
    phase_core: tuple[float, float] | None = None
    # Exact retained paint successors owned by this foreground cue.
    owned_backing: tuple[Event,...] = ()

    @property
    def anchors(self) -> list[tuple[str, float]]:
        return [(text, pos[0]) for _, text, pos in self.pieces]


@dataclass(frozen=True)
class TextPhaseRowsResult:
    """Accepted captions, protected row evidence and caller-applied visibility.

    Events and input visibility are borrowed. Callers adopt rows and apply
    the sparse delta before reconstruction or protected timing decisions.
    """
    events: list[Event]
    removed_count: int
    rows: list[TextRow]
    visibility_updates: dict[int,str]


@dataclass(frozen=True)
class CoveredFragmentRemoval:
    """Retained events, independent row successors and the removed-effect count.

    Callers adopt rows for both fade-family collection and overlap trimming.
    Existing phase cores survive unchanged; a new core is added only when
    complete source glyph timing proves an authored cue or one shared fade.
    Event references remain borrowed; row containers belong to this result.
    """
    events: list[Event]
    rows: list[TextRow]
    removed_effects: int


def _index_source_fragment_visibility(row: TextRow) -> dict:
    """Group layered source paint rows by their existing opaque-span profile."""
    first = row.base
    phases = {}
    for paint_row in row.paint_rows:
        profile = paint_row[0].evidence.opaque_spans
        if profile is None:
            profile = ((first.start_s,first.end_s),)
        phases.setdefault(profile,[]).append(paint_row)
    return phases
