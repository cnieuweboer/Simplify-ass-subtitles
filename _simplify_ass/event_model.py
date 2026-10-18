"""Core event records shared by engine subsystems.

Document and pipeline callers retain ownership of cache installation, evidence
proof/invalidation and measurement policy. These records keep their existing
mutability, factories and immutable evidence/context containers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ass_overrides import OverrideContinuation


@dataclass(frozen=True)
class EventEvidence:
    """Historical source evidence, separate from resolved ASS formatting.

    Contours describe the original scene-space outline; opaque spans describe
    authored source visibility in absolute seconds. Neither claims coverage
    or opacity throughout a later replacement's interval. Immutable values
    may be shared across a proven edit without sharing mutable state.
    """
    original_contour_points: tuple[tuple[float, float], ...] | None = None
    opaque_spans: tuple[tuple[float, float], ...] | None = None
    # Sampled/frozen frame support before paint normalization or interval extension.
    # Each entry is (absolute start, absolute end, primary/outline/shadow alpha).
    frame_pose_intervals: tuple[tuple[float,float,tuple[float,float,float]], ...] | None = None

    def __post_init__(self):
        if self.original_contour_points is not None:
            object.__setattr__(self, 'original_contour_points',
                tuple(tuple(point) for point in self.original_contour_points))
        if self.opaque_spans is not None:
            object.__setattr__(self, 'opaque_spans',
                tuple(tuple(span) for span in self.opaque_spans))
        if self.frame_pose_intervals is not None:
            object.__setattr__(self, 'frame_pose_intervals',tuple(
                (start,end,tuple(alpha)) for start,end,alpha in self.frame_pose_intervals))


@dataclass(frozen=True)
class DocumentMeasurementContext:
    """Document geometry and the wrapping policy active at this phase.

    Canvas is present only when both authored PlayRes dimensions are valid;
    unit-scaling fallbacks do not establish viewport coverage. Script wrapping
    is inactive during text processing and activated at the measurement
    boundary. Explicit ASS q remains in formatting and takes precedence.
    Immutable context survives event edits, including text/style replacement.
    """
    canvas: tuple[float, float] | None = None
    script_wrap_mode: int | None = None


@dataclass
class Event:
    """Authored records and an optional resolved formatting/history cache.

    Defaults and the style catalog are document-owned, borrowed read-only.
    Timing-only successors may share the read-only-by-convention state cache;
    formatting edits use a new buffer. Cache owners install state and
    continuation together. Empty state requires a fresh complete evaluation.
    Measurement and evidence have independent replacement/lifetime rules.
    """
    kind: str
    layer: str
    start: str
    end: str
    style: str
    name: str
    margin_l: str
    margin_r: str
    margin_v: str
    effect: str
    text: str
    start_s: float
    end_s: float
    source_index: int
    state: dict = field(default_factory=dict, compare=False)
    defaults: dict = field(default_factory=dict, compare=False, repr=False)
    styles: dict = field(default_factory=dict, compare=False, repr=False)
    lyric: bool = False
    row: int = 0
    unit: float = 1.0
    evidence: EventEvidence = field(default_factory=EventEvidence, compare=False, repr=False)
    measurement: DocumentMeasurementContext = field(
        default_factory=DocumentMeasurementContext, compare=False, repr=False)
    continuation: OverrideContinuation = field(
        default_factory=OverrideContinuation, compare=False, repr=False)

    @property
    def duration(self) -> float:
        return self.end_s - self.start_s

    def fields(self) -> list[str]:
        return [
            self.layer, self.start, self.end, self.style, self.name,
            self.margin_l, self.margin_r, self.margin_v, self.effect, self.text,
        ]
