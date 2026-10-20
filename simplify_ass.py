#!/usr/bin/env python3
"""Simplify ASS/SSA subtitles for limited renderers.

Requires Python 3.10 or newer.

Standard simplification reduces text effects and reconstructs caption supports.
Legacy simplification is deprecated; its static-sign/vector pipeline remains for
reference and compatibility. Processing without optional font measurements
requires only the standard library. Font measurements use Pillow and fonttools.
If RAQM is absent (for example on Windows), uharfbuzz provides shaping fallback:
    python -m pip install Pillow fonttools uharfbuzz
    python simplify_ass.py input.ass --level 1 --font-mkv episode.mkv
Or supply extracted fonts with --fonts-dir FOLDER. Exact installed fonts and
fonts/ beside the script or input are also searched. No font substitution or
word dictionary is used. The MKV option requires MKVToolNix in PATH.

Ambiguous fragments keep their positions; drawing budgets are opt-in.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.exit("simplify_ass.py requires Python 3.10 or newer "
             f"(running {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}).")

import argparse
import collections
import codecs
from bisect import bisect_left, bisect_right
import math
import logging
import re
import statistics
import time
import unicodedata
from dataclasses import dataclass, replace as dataclass_replace, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

from _simplify_ass.ass_overrides import (
    OverrideContinuation, OverrideEvaluation, tokenize_override, resolve_event_style,
    parse_styles, apply_font_size, apply_override, evaluate_effective_state,
    effective_state, OVERRIDE_RE, TAG_NAMES, TAG_RE, NUMBER, DEFAULT_STATE, STYLE_TAGS,
)
from _simplify_ass.font_metrics import (
    FontFace, FontCapabilities, FontLineInkMetrics, FontMetrics,
)
from _simplify_ass.font_outlines import FontOutlineMatcher, fit_cubic_points
from _simplify_ass.glyph_placement import (
    fit_fragment_anchor, authored_glyph_positions, matches_authored_glyph_positions,
)

from _simplify_ass.transform_sampling import (
    font_size_transform_needs_replay, transform_weight, interpolate_transform_value,
    _commit_transform_continuation, sample_transform_state, sample_transform_states,
)

from _simplify_ass.event_model import Event, EventEvidence, DocumentMeasurementContext
from _simplify_ass.frame_echoes import (
    FrameEchoContext,
    FrameEchoFamily,
    FrameEchoFrame,
    FrameEchoHold,
    FrameEchoPaintProfile,
    _advance_flattened_frame_echo,
    _blocked_frame_echo_times,
    _collapse_frame_echo_family,
    _frame_echo_candidates,
    _frame_echo_follows_motion,
    _frame_echo_is_exit,
    _frame_echo_paint_profile,
    _index_frame_echo_families,
    _isolated_frame_echo_times,
    _match_flattened_frame_echo,
    _match_stacked_frame_echo,
    _prepare_frame_echo_family,
    _profile_frame_echo,
    _recorded_frame_echo_motion,
    _replace_frame_echo,
    collapse_frame_text_echoes,
)
from _simplify_ass.effect_validation import parse_effect_transform, parse_effect_move
from _simplify_ass.event_operations import event_override_tokens
from _simplify_ass.scrolling_blocks import (
    ScrollingBlockMatch,
    _match_scrolling_block,
    _profile_scrolling_track,
    _scrolling_pose_is_translational,
    _scrolling_profile_position,
    _scrolling_profiles_are_coherent,
    _scrolling_profiles_are_distinct,
    collect_scrolling_tracks,
    drop_overloaded_scrolling_blocks,
    scroll_track_crosses_canvas,
)
from _simplify_ass.drawing_geometry import (
    coverage_geometry, polygon_covers_box, drawing_polygon,
    fit_rectangular_contour, normalize_drawing_alignment,
    flatten_rectangular_border, detach_drawing_edge_slivers,
    simplify_drawing_contour,
)
from _simplify_ass.static_compaction import (
    _finished_static_key, _join_finished_static_headers, compact_static_overrides
)
from _simplify_ass.event_operations import (
    event_evaluation, replace_event, _frame_pose_key, state_key,
)
from _simplify_ass.frame_pose import (
    _frame_paint_alphas, _frame_pose_intervals, _visible_pose_support,
    _preserve_frame_pose_support, _representative_frame_pose,
)
from _simplify_ass.static_objects import (
    StaticSpanSignature, geometry_key, static_object_key,
    _merge_static_phase_round, merge_static_timed_copies,
)
from _simplify_ass.caption_geometry import (
    NUM, POS_RE, caption_bounds, get_pos, inline_layout_key, set_pos,
    text_height, placement_key, text_layout_key, compatible_text_layout,
)
from _simplify_ass.text_freezing import (
    FrozenBlock, SAFE_SIMPLE_TAGS, _freeze_inputs, freeze_block, safe_override,
    simplify_text, simplify_visual_text,
)
from _simplify_ass.caption_rendering import (
    MAX_PROVED_CAPTION_BORDER, SourceCaptionPaint, _source_caption_paint,
    render_simplified_caption, render_tag,
)
from _simplify_ass.subtitle_document import (
    SubtitleDocument, EVENT_FIELDS, GENERATED_MARKER, parse_time, format_time,
    peak_concurrent_events, parse_dialogue, read_subtitle, script_resolution,
    parse_subtitle_document, read_subtitle_document, _resolve_document_state,
    mark_generated, render_subtitle_document, write_subtitle_document,
    load_subtitle_events,
)
from _simplify_ass.static_selection import (
    StaticStateContext, StaticStateEvidence, StaticStateSamples,
    StaticPoseEvidence, StaticStateSelection, unrotated_text_state,
    upright_text_state, upright_transform_pose, _prepare_static_state_evidence,
    _static_state_geometry_is_settled, _vote_static_state_holds,
    _record_static_opaque_span, _sample_static_state_intervals,
    _choose_static_state_geometry, _static_state_has_rotation,
    _apply_static_upright_fallback, _protect_sustained_static_geometry,
    _static_state_colour_spans, _vote_static_state_colours,
    _apply_static_state_colour_vote, select_static_state,
)

from _simplify_ass.complete_line_jitter import (
    JitterTextFamily, CompleteLineJitterResult, _index_complete_line_jitter,
    _prove_complete_line_jitter, _complete_line_jitter_families,
    _complete_line_jitter_core_overlap, _group_complete_line_jitter_stacks,
    _render_complete_line_jitter, flatten_complete_line_jitter,
)

from _simplify_ass.masked_glyphs import (
    MaskedGlyphContext, ParsedGlyphMask, MaskedGlyphModel, MaskedGlyphProof,
    _canonicalize_mask_contours, _prepare_masked_glyphs,
    _index_masked_texture_peers, _parse_glyph_mask, _match_masked_shadow_texture,
    _masked_glyph_candidates, _masked_placement_matches, _same_masked_text_copy,
    _masked_glyph_outline, _prepare_masked_outline_model, _fit_masked_outline_segment,
    _match_masked_glyph_contours, _match_masked_glyph_bases,
    _remove_masked_texture_companions, _apply_masked_glyph_proof,
    _follow_proven_shadow_mask_phases, _close_masked_glyph_fonts,
    remove_masked_glyph_effects,
)

from _simplify_ass.karaoke_completion import (
    KaraokeCompletionSourcePhase, KaraokeCompletionProfile,
    _karaoke_completion_identity, _karaoke_completion_cue_start,
    _karaoke_completion_paint, _index_retained_karaoke_completion_rows,
    _select_karaoke_completion_rows, _index_karaoke_completion_sources,
    _karaoke_completion_source_phases, _profile_karaoke_completion_source_phase,
    _prove_karaoke_completion_transition, _match_karaoke_completion_profiles,
    _prove_ordered_karaoke_completion_sweep, _replace_karaoke_completion_paint,
    normalize_karaoke_completion_paint,
)

from _simplify_ass.caption_paint_sampling import (
    _settled_caption_paint_samples, _pool_source_caption_paint,
)

from _simplify_ass.backed_glyph_pulses import (
    BackedPulseContext, BackedPulseRow, _eligible_backed_glyph_state,
    _parse_backed_glyph_effects, _prepare_backed_glyph_pulses,
    _group_backed_glyph_rows, _backed_glyph_pose, _backed_frames_converge,
    _collect_backed_row_holds, _backed_row_has_conflicts, _select_backed_row_pose,
    _backed_sizes_are_positive, _backed_foreground_coverage,
    _backed_transform_returns, _prove_backed_foreground_pulses,
    _extend_backed_pulse_tails, _proved_backed_row_paint,
    _propose_backed_pulse_row, _apply_backed_pulse_proposals,
    collapse_backed_glyph_pulses,
)

from _simplify_ass.event_operations import literal_font_spans
from _simplify_ass.effect_validation import opaque_text_effect_state

from _simplify_ass.moving_glyphs import (
    _moving_glyph_source_families, _moving_glyph_geometry, _moving_glyph_paint,
    _index_moving_glyph_sources, _index_retained_moving_glyphs, _retained_moving_glyph,
    _group_moving_glyph_sequences, _moving_glyph_group_fits, _matching_moving_glyph_fades,
    _prove_moving_glyph_chain, _match_moving_glyph_prefix, _collect_moving_glyph_overlays,
    _match_moving_glyph_exit, _render_moving_glyph_caption, _propose_moving_glyph_sequence,
    _apply_moving_glyph_proposals, collapse_moving_glyph_sequences, MovingGlyphContext,
    MovingGlyphChain,
)

__version__ = "2026.10.20.242"


class _FontTimestampFilter(logging.Filter):
    """Hide harmless fontTools 'head' date warnings from embedded fonts."""

    def filter(self, record):
        return not (record.levelno == logging.WARNING and
                    record.msg in {
                        "'%s' timestamp seems very low; regarding as unix timestamp",
                        "'%s' timestamp out of range; ignoring top bytes",
                    })


logging.getLogger("fontTools.ttLib.tables._h_e_a_d").addFilter(_FontTimestampFilter())


@dataclass(frozen=True, kw_only=True)
class SimplifyConfig:
    """Named, immutable settings shared by a subtitle simplification batch.

    legacy simplification is deprecated and retained for compatibility.
    """
    level: int = 1
    max_blur: float = 0.0
    short_duration: float = 0.16
    short_gap: float = 0.08
    max_drawing_chars: int = 0
    max_vectors_per_cue: int = 0
    encoding: str | None = None
    scroll_concurrency_limit: int = 32
    color_phase_min_hold: float = 1.0
    color_phase_change_interval: float = 0.0

    def __post_init__(self):
        for name in ('color_phase_min_hold','color_phase_change_interval'):
            value=getattr(self,name)
            if not math.isfinite(value) or value<0:
                raise ValueError(name+' must be finite and nonnegative.')


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
class RowReconstructionContext:
    """Inputs and original-neighbor indexes shared during one reconstruction.

    Visibility is a pass-local overlay on borrowed caller evidence. Neighbor
    indexes stay fixed while pending edits accumulate separately. Font
    caches are borrowed from metrics; reporting belongs to the caller.
    """
    eligible: list[Event]
    neighbors: dict[tuple,tuple]
    comments: dict[str,list[tuple[Event,str]]]
    visible_map: collections.ChainMap[int,str]
    space_map: dict[tuple,set[float]]
    font_metrics: FontMetrics | None
    animated_sources: set[int]
    source_events: dict[int,Event] | None
    font_report: FontProcessingReport | None = None


@dataclass
class RowReconstructionEdits:
    """Pending replacements and evidence local to one reconstruction call."""
    removed: set[int] = field(default_factory=set)
    replacements: dict[int,Event] = field(default_factory=dict)
    row_evidence: dict[int,TextRow] = field(default_factory=dict)
    visibility_updates: dict[int,str] = field(default_factory=dict)
    chain_families: set[tuple] = field(default_factory=set)
    coextensive_rows: set[int] = field(default_factory=set)
    duplicate_count: int = 0
    merged_count: int = 0


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
class SharedIntervalRowsResult:
    """Retained row/tail events, operation counts and pending visibility.

    The pass owns an overlay for all rounds. Callers apply its delta only
    after successful completion; source-history entries are never removed.
    """
    events: list[Event]
    rows_joined: int
    tails_retained: int
    visibility_updates: dict[int,str]


@dataclass(frozen=True)
class AuthoredLyricRowsResult:
    """Matched source IDs, new row proof and resolved source-cache successors.

    Inputs are borrowed. Only unresolved, evaluated sources appear in the
    update delta; aliases in the source map share one successor. Callers apply
    those updates before later source-state readers. Existing caches are reused.
    """
    removed_sources: set[int]
    row_additions: list[TextRow]
    source_updates: dict[int,Event]


@dataclass(frozen=True)
class FullLineCopyResult:
    """Retained captions, removal count and caller-applied source/row updates.

    Row additions include both moving authored rows and static scaffold rows.
    No caller-owned event, source map or row-evidence container is modified.
    """
    events: list[Event]
    removed_count: int
    row_additions: list[TextRow]
    source_updates: dict[int,Event]


@dataclass(frozen=True)
class RowReconstructionResult:
    """Reconstructed events, final row evidence, counts and visibility updates.

    Callers adopt events/rows and apply visibility_updates to their shared map
    before the next pass. Removed fragment entries remain source history;
    only proved caption text is updated. Row bases carry final caption timing,
    while pieces retain the source intervals used to prove those captions.
    """
    events: list[Event]
    merged_count: int
    duplicate_count: int
    rows: list[TextRow]
    visibility_updates: dict[int,str]


@dataclass(frozen=True)
class RowJoinCandidate:
    """A row whose geometry, timing and original-neighbor checks passed."""
    run: list[Event]
    ordered: list[Event]
    xs: list[float]
    ys: list[float]
    start: float
    end: float
    shared_interval: bool
    y: float


@dataclass(frozen=True)
class RowCaptionFit:
    """Proven text spacing and static layout to send to the shared renderer."""
    text: str
    x: float
    sx: float
    sy: float
    alignment: int
    tracking: float | None
    measured: bool


@dataclass(frozen=True)
class TranslatedPhaseContext:
    """Original events, measured movement profiles and the eligible phase pool."""
    visible: Mapping[int,str]
    metric: FontMetrics
    profiles: list[tuple]
    pool: dict[str,list[Event]]
    allids: dict[int,Event]
    font_report: FontProcessingReport | None = None


@dataclass(frozen=True)
class TranslatedCueLayout:
    """Authored cue geometry selected from translation or held-text evidence."""
    cue: Event
    text: str
    window: float
    seeds: list[tuple]
    sample: Event
    key: tuple
    delta: float
    y: float
    positions: list[tuple[str,float]]


@dataclass(frozen=True)
class TranslatedCueModel:
    """One complete glyph model with a cache owned by this cue alone."""
    layout: TranslatedCueLayout
    center: float
    xs: list[float]
    initial_start: float
    spans: tuple
    span_cache: dict[tuple,list[tuple[int,int]]] = field(default_factory=dict,compare=False)


@dataclass(frozen=True)
class TranslatedCuePhases:
    """Matched held text, entrance fragments and proved movement pulses."""
    stable: list[tuple[Event,tuple[int,int]]]
    entrances: list[tuple[Event,tuple[int,int]]]
    pulses: list[tuple[Event,tuple[int,int]]]


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


@dataclass(frozen=True)
class CoveredFragmentContext:
    """Original row evidence, timing indexes and caches owned by one removal pass.

    Row models are borrowed and read-only. Selected timing proofs are returned
    separately. The maps and caches are temporary and never stored on events.
    """
    visible: dict[int,str]
    animated: set[int]
    sources: dict[int,Event] | None
    metric: FontMetrics | None
    anchors: dict[int,list[tuple[str,float]]]
    models: dict[int,TextRow]
    layouts: dict[int,tuple]
    rows: dict[str,list[Event]]
    virtual: set[int]
    static_glyphs: dict[int,list[tuple[Event,str,tuple]]]
    row_indexes: dict[str,tuple | None]
    span_indexes: dict[tuple,tuple] = field(default_factory=dict,compare=False)
    shadow_sources: dict[int,bool] = field(default_factory=dict,compare=False)
    shadow_rows: set[int] = field(default_factory=set,compare=False)
    shadow_layers: dict[int,int] = field(default_factory=dict,compare=False)
    shadow_poses: dict[int,Event] = field(default_factory=dict,compare=False)


@dataclass(frozen=True)
class SharedIntervalContext:
    """Pass-owned visibility overlay, order/layer indexes and caption-bound cache."""
    visible: MutableMapping[int,str]
    metric: FontMetrics
    paint_tags: set[str]
    boxes: dict[int,tuple | None]
    order_index: dict[int,int]
    by_layer: dict[int,list[Event]]
    layer_indices: dict[int,list[int]]
    font_report: FontProcessingReport | None = None


@dataclass(frozen=True)
class SharedIntervalProposal:
    """A font-proven common row interval with its original safe placement slots."""
    members: frozenset[int]
    ordered: list[Event]
    first_start: Event
    first_end: Event
    body: str
    text: str
    valid_slots: list[Event]
    member_boxes: list[tuple]


@dataclass
class SharedIntervalEdits:
    """Generated rows/tails, original-slot replacements and accepted placement evidence."""
    next_index: int
    claimed: set[int] = field(default_factory=set)
    slots: dict[int,list[Event]] = field(default_factory=dict)
    accepted: list[tuple] = field(default_factory=list)
    rows: int = 0
    tails: int = 0






@dataclass(frozen=True)
class FadedCueContext:
    """Private retained-cue indexes and source-proven family cores for one pass."""
    provenance: dict[int,list[TextRow]]
    groups: dict[tuple,dict[tuple,list[Event]]]
    family_proofs: dict[tuple,tuple]


@dataclass(frozen=True)
class FadedCueEvidence:
    """Collision-boundary fragment fade endpoints and priority shadow phases."""
    phase_slots: dict[tuple,dict[tuple,set[float]]]
    shadow_phases: set[tuple]


@dataclass(frozen=True)
class FragmentPhaseContext:
    """Private eligible fragments, touching phase indexes and font metric for one pass."""
    eligible: list[Event]
    words: dict[int,str]
    geometry: dict[int,tuple]
    positions: dict[int,tuple[float,float]]
    endings: dict[tuple,list[Event]]
    anchored_starts: dict[tuple,list[Event]]
    anchored_ends: dict[tuple,list[Event]]
    metric: FontMetrics
    font_report: FontProcessingReport | None = None


@dataclass(frozen=True)
class FragmentPhaseProfile:
    """A proved fragment-to-word chain and its authored activation boundaries."""
    caption_sample: Event
    members: list[Event]
    start_s: float
    activation_s: float
    terminal_start_s: float
    joined_fragments: bool


@dataclass(frozen=True)
class StackedTextContext:
    """Private copy groups and collision indexes with the original paint/source inputs."""
    groups: dict[tuple,list[Event]]
    kept: list[Event]
    collision_peers: dict[str,list[Event]]
    paint: set[str]
    animated_sources: set[int] | None
    source_events: dict[int,Event] | None
    font_metrics: FontMetrics | None = None
    glow_paint: dict[int,GlowPulsePaint] = field(default_factory=dict)
    owned_glow_fragments: set[int] = field(default_factory=set)
    glow_captions: dict[int,Event] = field(default_factory=dict)
    glow_collapsed: dict[int,list[int]] = field(default_factory=dict)
    matched_backing_fades: dict[frozenset[int],MatchedBackingFade] = field(default_factory=dict)
    # Producer-owned unequal-lifetime stacks, consumed without repeating proof.
    contained_paint: dict[frozenset[int],tuple] = field(default_factory=dict)


@dataclass(frozen=True)
class StackedTextResult:
    events: list[Event]
    removed_count: int
    phase_merged: int
    rows: list[TextRow]


@dataclass(frozen=True)
class BackingFadePhase:
    """Candidate paint planes; the family must still prove a readable fade."""
    foreground: Event
    backing: Event
    alpha: int
    paint: tuple[SourceCaptionPaint,...]
    surface: tuple[tuple[float,...],...]


@dataclass(frozen=True)
class MatchedBackingFade:
    """Owned immutable span paint; borrowed planes retain each phase's geometry."""
    foreground: Event
    backing: Event
    literal: str
    paint: tuple[SourceCaptionPaint,...]
    alpha: int


@dataclass(frozen=True)
class GlowPulsePaint:
    """Source-proved returning highlight and persistent contour, owned by one stack."""
    fill: str
    outline: str
    fragments: frozenset[int]
    scale: tuple[float,float]
    outline_alpha: int = 0


@dataclass(frozen=True)
class StackedTextProof:
    """The existing animated shadow, static shadow and solid-fill admission results."""
    shadow_text: bool
    static_shadow_text: bool
    solid_stack: bool


@dataclass(frozen=True)
class OutlineStripEvidence:
    """One family's strip partition, initial paint, weights and source tokens.

    Original sources remain borrowed and unchanged. Token entries retain their
    exact source object and use its identity, so a replacement with the same
    source index cannot inherit parsing. Reuse expires with this family's proof,
    rather than retaining every source token until the entire pass finishes.
    """
    strips: tuple[tuple[Event,tuple,dict],...]
    weights: tuple[float,...]
    animated: bool = False
    source_tokens: dict[int,tuple[Event,tuple[tuple[str,str],...]]] = field(
        default_factory=dict,compare=False,repr=False)

    def tokens_for(self, source: Event) -> tuple[tuple[str,str],...]:
        entry = self.source_tokens.get(id(source))
        if entry is None:
            entry = source,tuple(event_override_tokens(source))
            self.source_tokens[id(source)] = entry
        return entry[1]


@dataclass(frozen=True)
class TextEffectSequenceContext:
    """Original pass inputs and the exact-position versus scale-trail mode."""
    visible_map: dict[int,str]
    styles: dict
    animated_sources: set[int]
    scale_trails: bool
    source_events: dict[int,Event] | None
    font_metrics: FontMetrics | None
    font_report: FontProcessingReport | None = None
    lyric_boundaries: LyricBoundaryIndex | None = None


@dataclass(frozen=True)
class TextEffectSequenceGeometry:
    """Cached positions, heights and non-scale layouts for one copy bucket."""
    positions: dict[int,tuple]
    heights: dict[int,float]
    layouts: dict[int,tuple]


@dataclass(frozen=True)
class TextEffectSequenceProfile:
    """Admitted members, visible paint samples and the complete caption interval."""
    members: list[Event]
    visible_candidates: list[Event]
    clipped: bool
    trail: bool
    start_s: float
    end_s: float


@dataclass(frozen=True)
class SlicedTextIndex:
    """Temporary indexes of held captions, clipped strips and fading size pulses."""
    holds: dict
    tiles: dict
    pulses: dict


@dataclass(frozen=True)
class SlicedTextEvent:
    """One resolved source event and its original movement, transform and layout evidence."""
    event: Event
    moves: list[str]
    transforms: list[str]
    pos: tuple | None
    key: tuple


@dataclass(frozen=True)
class ShrinkingRowSource:
    """Resolved source text with its original move and transform evidence."""
    event: Event
    text: str
    moves: list[str]
    transforms: list[str]


@dataclass(frozen=True)
class ShrinkingRowIndex:
    """Private complete-row groups and held-caption boundary index for one pass."""
    groups: dict
    caption_index: dict


@dataclass(frozen=True)
class ShrinkingRowProposal:
    """A complete shrinking source row and its unique held-caption owner."""
    start_s: float
    end_s: float
    layer: str
    peers: list
    held: Event


@dataclass(frozen=True)
class ProgressiveRevealPrefix:
    """Literal-span proof with its visible prefix, common layout and foreground paint."""
    literal: str
    prefix: str
    layout: tuple
    foreground: dict


@dataclass(frozen=True)
class ProgressiveRevealBand:
    """The existing text height and complete vertical extent of a thin strip group."""
    height: float
    top: float
    bottom: float


@dataclass(frozen=True)
class ProgressiveRevealCaption:
    """Selected held foreground source and its rendered complete caption body."""
    event: Event
    body: str


@dataclass(frozen=True)
class SourceFragmentRowContext:
    """Original row geometry, contiguous fragment index and private per-row matching cache."""
    row: TextRow
    first: Event
    chosen: list[Event]
    height: float
    anchors: dict
    span_index: tuple
    gaps: list[int]
    syllables: dict
    top_layer: int
    layout_tags: set[str]


@dataclass(frozen=True)
class SourceFragmentCandidate:
    """One admitted source with its position, initial anchors, resolved state and delayed flag."""
    event: Event
    pos: tuple
    nearby: list
    state: dict
    delayed: bool


@dataclass(frozen=True)
class SourceFragmentEvidence:
    """Existing paint candidates and distinct animated word/anchor evidence for one row."""
    candidates: list[Event]
    evidence: set


@dataclass(frozen=True)
class SourceFragmentRemoval:
    """Working events, independently writable rows and the effect-removal count.

    Row geometry, timing, visibility and source provenance remain historical
    evidence even when their paint sources are removed from the working list.
    The caller adopts rows before reconstruction; supplied rows are borrowed.
    """
    events: list[Event]
    rows: list[TextRow]
    removed_effects: int
    paint_families: list[TextRow] = field(default_factory=list)


@dataclass(frozen=True)
class BoundaryGlyphPhase:
    """Classified authored entrance/exit with its boundary, anchor, state and glyph."""
    phase: str
    boundary: float
    pos: tuple
    state: dict
    glyph: str
    continuation: OverrideContinuation


@dataclass(frozen=True)
class BoundaryGlyphIndex:
    """Per-call effect groups, caption candidates and source/protection membership."""
    groups: dict
    captions: dict
    caption_candidates: list
    boundary_sources: set[int]
    protected: set[int]


@dataclass(frozen=True)
class VectorTextFitContext:
    """Per-call font measurement, blur policy and positive/negative outline-fit cache."""
    metric: FontMetrics
    max_blur: float
    cache: dict
    font_report: FontProcessingReport | None = None


@dataclass(frozen=True)
class SupportingDrawingContext:
    """Per-call border policy, counters, paint tags and retained original-contour evidence."""
    scaled_borders: bool
    counts: dict
    paint_tags: set
    original_contours: dict


@dataclass(frozen=True)
class SupportingDrawingCandidate:
    """Normalized candidate with frozen text, readable text and pre-simplification contour."""
    event: Event
    frozen_text: str
    visible: str
    original_points: list | None


@dataclass(frozen=True)
class SupportingDrawingCoverage:
    """Proven clip union and its distinct rectangles/coincident paint groups."""
    union: tuple | None
    clip_groups: dict
    rectangles: list


@dataclass(frozen=True)
class FullLineCopyProof:
    """Complete fragment ownership evidence and the selected foreground column representatives."""
    ordered: list[Event]
    fragments: list[Event]
    assembled: str
    shadow_only: bool


@dataclass
class TextProcessingResult:
    """Finished text/vector events and counters, before backdrop reconstruction."""
    events: list[Event]
    statistics: dict[str,object]


@dataclass
class CollectedSourceText:
    """Collected rows plus explicitly resolved successors of borrowed events.

    The caller adopts events for working formatting. Row events separately
    own sampled paint and immutable authored visibility; the input map and
    its events are never modified by collection.
    """
    events: dict[int,Event]
    rows: list[TextRow]
    words: dict[int,str]
    positions: dict[int,tuple[float,float] | None]


@dataclass
class PreparedSourceText:
    """Source evidence retained until effect and timing decisions finish."""
    events: dict[int,Event]
    timing_sources: dict[int,Event]
    rows: list[TextRow]
    effects_removed: int
    vector_captions: int
    paint_timelines: tuple = ()


@dataclass
class FrozenTextEvents:
    """Existing caption/vector lists and maps produced by effect freezing."""
    captions: list[Event]
    vectors: list[Event]
    backdrops: list
    visible: dict[int,str]
    spaces: dict
    blanks: list[Event]
    statistics: dict[str,int]


@dataclass(frozen=True)
class CaptionPanelOwnership:
    """A measured enclosing relationship; borrowed panel and caption records."""
    panel: Event
    caption: Event


@dataclass
class CaptionSupportResult:
    """Selected supports, their caption associations and output ordering."""
    events: list[Event]
    kept: list[Event]
    fallback: list[Event]
    associated: dict
    removed_textures: set[int]
    counts: dict[str,int]
    # None accepts older direct constructors; production always supplies proof.
    ownership: list[CaptionPanelOwnership] | None = None


def animated_shadow_painted_source(e: Event, sources: dict[int,Event] | None,
                                   animated: set[int]) -> bool:
    """Recognize source text painted exclusively by an animated shadow."""
    original = (sources or {}).get(e.source_index)
    if original is None or original.kind != 'Dialogue' or e.source_index not in animated:
        return False
    evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
    state = evaluated.formatting
    if (state.get('1a',0) < 254 or state.get('3a',0) < 254 or
            state.get('borderstyle',1) != 1 or
            state.get('p',0) or any(k in state for k in ('clip','iclip','org')) or
            get_pos(original.text) is None or re.search(r'\\move\s*\(',original.text,re.I) or
            inline_layout_key(dataclass_replace(original,state=state,continuation=evaluated.continuation)) or
            not any(abs(state.get(k,state.get('shad',0))) > 0 for k in ('xshad','yshad'))):
        return False
    return not any(tag in {'alpha','1a','3a','r'}
                   for name,value in event_override_tokens(original) if name == 't'
                   for tag,_ in tokenize_override(value.strip('()')))


def positioned_row_geometry(ordered: list[Event], *,
                              min_x_step: float | None = None
                              ) -> tuple[list[float],list[float]] | None:
    """Validate anchors in supplied reading order and return their coordinates.

    A row needs distinct increasing x anchors and a total vertical spread of
    at most 15% of its shortest text height. The default horizontal tolerance
    is the smallest event unit; virtual-row evidence supplies its first unit.
    Eligibility, font fitting and timing remain the caller's responsibility.
    """
    if len(ordered) < 2:
        return None
    positions = [get_pos(e.text) for e in ordered]
    if any(pos is None for pos in positions):
        return None
    xs = [pos[0] for pos in positions]
    ys = [pos[1] for pos in positions]
    tolerance = min(e.unit for e in ordered) if min_x_step is None else min_x_step
    if (any(b-a <= tolerance for a,b in zip(xs,xs[1:])) or
            max(ys)-min(ys) > .15*min(text_height(e) for e in ordered)):
        return None
    return xs,ys


def split_positioned_row_runs(events: Iterable[Event]) -> list[list[Event]]:
    """Split positioned candidates at gaps above twice the adjacent height.

    Stable x ordering retains tied-anchor source order. Geometry validation
    and cue ownership are separate: this grouping step proves neither.
    """
    runs = []
    for e in sorted(events,key=lambda e:get_pos(e.text)[0]):
        if (not runs or get_pos(e.text)[0]-get_pos(runs[-1][-1].text)[0] >
                2*min(text_height(e),text_height(runs[-1][-1]))):
            runs.append([])
        runs[-1].append(e)
    return runs


def x_key(e: Event) -> float:
    return round(get_pos(e.text)[0] / e.unit, 1) * e.unit


def assign_layout(events: list[Event], visible_map: dict[int, str]) -> None:
    """Cluster baselines by font height, then recognize repeated fragment rows."""
    positions = {e.source_index: get_pos(e.text) for e in events}
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind == "Dialogue" and positions[e.source_index] is not None:
            groups.setdefault((e.style,e.name), []).append(e)
    row_id = 0
    for group in groups.values():
        rows: list[list[Event]] = []
        for e in sorted(group, key=lambda item:positions[item.source_index][1]):
            y = positions[e.source_index][1]
            if not rows or abs(y-((positions[rows[-1][(len(rows[-1])-1)//2].source_index][1] + positions[rows[-1][len(rows[-1])//2].source_index][1])/2)) > .20*min(text_height(e),text_height(rows[-1][0])):
                rows.append([])
            rows[-1].append(e)
        for row in rows:
            row_id += 1
            for e in row:
                e.row = row_id
            cues: dict[tuple, list[Event]] = {}
            for e in row:
                cues.setdefault((e.start,e.end),[]).append(e)
            seeds = []
            for cue in cues.values():
                pieces = {}
                for e in cue:
                    text = visible_map.get(e.source_index, "")
                    if text:
                        pieces.setdefault(x_key(e), []).append(e)
                # Repeated layers at multiple positions are evidence of a
                # fragmented effect; short words alone are not.
                if len(pieces) >= 2 and all(
                    len({visible_map[e.source_index] for e in group}) == 1
                    and len(group) >= 2 for group in pieces.values()):
                    seeds.extend(cue)
            evidence = {}
            for seed in seeds:
                evidence.setdefault((x_key(seed), visible_map.get(seed.source_index, "")), []).append(seed)
            for e in row:
                text = visible_map.get(e.source_index, "")
                e.lyric = any(min(e.end_s, seed.end_s) > max(e.start_s, seed.start_s)
                    for seed in evidence.get((x_key(e), text), ()))


def event_identity_for_dedup(e: Event, visible: str) -> tuple:
    pos = get_pos(e.text)
    rounded_pos = None if pos is None else (round(pos[0] / e.unit, 1) * e.unit, round(pos[1] / e.unit, 1) * e.unit)
    return (
        e.layer, e.start, e.end, e.style, e.name,
        e.margin_l, e.margin_r, e.margin_v,
        visible, rounded_pos, text_layout_key(e), e.text,
    )


def has_translucent_paint(e: Event) -> bool:
    """Keep compositing evidence whenever a literal span uses partial alpha.

    Check all paint channels conservatively, including styles and inline
    resets. The cached final state cannot describe an earlier painted span.
    Animated alpha is also unsafe until the normal freezing pass resolves it.
    Fully hidden channels cannot accumulate visible paint.
    """
    default = resolve_event_style(e.styles, e.style, e.defaults or DEFAULT_STATE)
    state = default.copy()
    continuation = OverrideContinuation()
    for part in re.split(r'(\{[^}]*\})', e.text):
        if part.startswith('{') and part.endswith('}'):
            for name, value in tokenize_override(part[1:-1]):
                if name in {'t', 'fad', 'fade', 'k', 'kf', 'ko', 'kt'}:
                    return True
                continuation = apply_override(state,name,value,e.styles,default,continuation)
        elif part and any(state.get(f'{channel}a', 0) not in (0, 255)
                          for channel in range(1, 5)):
            return True
    return False


def deduplicate_layers(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Collapse positioned duplicates without losing translucent compositing."""
    seen: dict[tuple, Event] = {}
    output: list[Event] = []
    removed = 0
    for e in events:
        if e.kind != "Dialogue":
            output.append(e)
            continue
        visible = visible_map.get(e.source_index, "")
        # Equal unpositioned text records can render on separate rows because
        # the renderer resolves collisions. Keep their original multiplicity;
        # later paint-copy stages require their own evidence before merging.
        # Drawings do not participate in text collision placement.
        if get_pos(e.text) is None and not e.state.get("p", 0):
            output.append(e)
            continue
        key = event_identity_for_dedup(e, visible)
        if key in seen and not has_translucent_paint(e):
            removed += 1
            continue
        seen[key] = e
        output.append(e)
    return output, removed


def reduce_static_sign_copies(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Remove proven redundant nonlyrics, then select representative sign paint.

    Lyrics still need their source/row context. The final invocation of the
    same redundancy proof receives the finished records after reconstruction.
    Effect-layer paint selection is deliberately confined to this early stage.
    """
    events, redundant = remove_redundant_text_copies(events, pending_lyrics=True)
    events, effects = select_static_sign_paint(events, visible_map)
    return events, redundant + effects


def select_static_sign_paint(events: list[Event], visible_map: dict[int, str]) -> tuple[list[Event], int]:
    """Choose representative fill from nonlyric, near-coincident effect copies.

    Unlike strict redundancy, this deliberately permits different paint/layers
    and the existing small size variation. Emphasis and spacing must agree.
    """
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind != "Dialogue" or e.lyric or get_pos(e.text) is None:
            continue
        visible = visible_map.get(e.source_index, "")
        if visible:
            groups.setdefault((e.style, e.name, e.margin_l, e.margin_r,
                               e.margin_v, visible), []).append(e)

    def alpha(e: Event) -> int:
        return e.state.get("1a",0)

    def rank(e: Event) -> tuple:
        return (alpha(e), -int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
                -e.duration, e.source_index)

    removed: set[int] = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        # Partial alpha still contributes beneath another copy. Preserve it
        # for the paint reconstruction stages rather than calling it covered.
        group = [e for e in group if not has_translucent_paint(e)]
        if len(group) < 2:
            continue
        ranks = {e.source_index: rank(e) for e in group}
        positions = {e.source_index: get_pos(e.text) for e in group}
        heights = {e.source_index: text_height(e) for e in group}
        # A covering copy must be within 6% of THIS event's height in x,
        # because the original bound uses the smaller of the two heights.
        # The sorted window is only a candidate index. Only retained records
        # provide coverage; removed anchors cannot authorize further drift.
        finite = all(math.isfinite(positions[e.source_index][0]) and
                     math.isfinite(heights[e.source_index]) for e in group)
        by_x = sorted(group,key=lambda e: positions[e.source_index][0]) if finite else group
        xs = [positions[e.source_index][0] for e in by_x] if finite else None
        for e in sorted(group, key=rank):
            x, y = positions[e.source_index]
            radius = math.nextafter(.06*heights[e.source_index],math.inf)
            # Expand the radius and endpoints by one floating-point step so
            # subtraction rounding (including cancellation) cannot exclude a
            # pair accepted by the original distance test.
            left = bisect_left(xs,math.nextafter(x-radius,-math.inf)) if xs is not None else 0
            right = bisect_right(xs,math.nextafter(x+radius,math.inf)) if xs is not None else len(by_x)
            for index in range(left,right):
                other = by_x[index]
                if (other is e or other.source_index in removed
                        or ranks[other.source_index] >= ranks[e.source_index]):
                    continue
                ox, oy = positions[other.source_index]
                if (_near_containing_text_copy(e, other, heights[e.source_index],
                                               heights[other.source_index])
                        and compatible_text_layout(e, other)
                        and all(e.state.get(k) == other.state.get(k) for k in
                                ('b', 'i', 'u', 's', 'fsp', 'q', 'org', 'pbo',
                                 'borderstyle', 'encoding'))):
                    removed.add(e.source_index)
                    break
    return [e for e in events if e.source_index not in removed], len(removed)


@dataclass(frozen=True)
class LyricBoundaryIndex:
    """Original surrounding-row signatures, borrowed through fragment reduction.

    This pass-local evidence survives glyph joins without claiming a new source
    lifetime. It expires after sequence merging and does not cross serialization.
    """
    starts: dict[tuple, set[tuple]]
    ends: dict[tuple, set[tuple]]
    touching: frozenset[tuple]
    caption_handoffs: frozenset[tuple]


def _index_lyric_boundaries(events: list[Event], visible_map: dict[int,str], *,
                            phase_groups: dict[int,int] | None = None) -> LyricBoundaryIndex:
    """Capture changes in the complete surrounding lyric before reducing pieces."""
    starts: dict[tuple, set[tuple]] = {}
    ends: dict[tuple, set[tuple]] = {}
    caption_starts: dict[tuple,set[tuple]] = {}
    caption_ends: dict[tuple,set[tuple]] = {}
    intervals: dict[tuple,list[tuple[float,float]]] = {}
    lyric_lanes = {(e.style,e.name,e.row) for e in events
                  if e.kind == 'Dialogue' and get_pos(e.text) is not None and
                  (e.lyric if phase_groups is None else e.source_index in phase_groups)}
    for e in events:
        pos = get_pos(e.text)
        row = (e.style, e.name, e.layer, e.row)
        lane = (e.style,e.name,e.row)
        # Eligibility limits edits, not neighboring context. An ordinary
        # single-plane next cue can still end an established lyric family.
        if e.kind != 'Dialogue' or pos is None or lane not in lyric_lanes:
            continue
        intervals.setdefault(lane,[]).append((e.start_s,e.end_s))
        glyph = (round(pos[0] / e.unit, 1) * e.unit, visible_map.get(e.source_index,''))
        caption_starts.setdefault((*lane, round(e.start_s, 2)), set()).add(glyph)
        caption_ends.setdefault((*lane, round(e.end_s, 2)), set()).add(glyph)
        admitted = e.lyric if phase_groups is None else e.source_index in phase_groups
        if admitted:
            starts.setdefault((*row, round(e.start_s, 2)), set()).add(glyph)
            ends.setdefault((*row, round(e.end_s, 2)), set()).add(glyph)
    touching = frozenset(key for key in starts.keys() & ends.keys()
                         if starts[key] != ends[key])
    handoffs = set()
    def literal(signature):
        return ''.join(''.join(word.split()) for x,word in sorted(signature))
    caption_changes = {key for key in caption_starts.keys() & caption_ends.keys()
                       if literal(caption_starts[key]) != literal(caption_ends[key])}
    for row,spans in intervals.items():
        # A complete row changes together. An ongoing letter means that a
        # touching subset may just be another staggered phase of the same cue.
        # Prefix maxima answer this without rescanning the row per boundary.
        ordered = sorted(spans)
        times = [a for a,b in ordered]
        maximum_ends = []
        for a,b in ordered:
            maximum_ends.append(max(b,maximum_ends[-1] if maximum_ends else b))
        for key in caption_changes:
            if key[:-1] != row or len(caption_starts[key])<2 or len(caption_ends[key])<2:
                continue
            at = key[-1]
            previous = bisect_left(times,at-1e-6)-1
            if previous>=0 and maximum_ends[previous]<=at+1e-6:
                handoffs.add(key)
    return LyricBoundaryIndex(starts,ends,touching,frozenset(handoffs))


def _crosses_lyric_boundary(index: LyricBoundaryIndex, current: Event, e: Event, *,
                             complete_only: bool = False) -> bool:
    """Keep repeated letters separate at touching or briefly overlapping lyrics."""
    row = (e.style,e.name,e.layer,e.row)
    boundary = (*row,round(e.start_s,2))
    if complete_only:
        # Later mergers reduce styling/frame sequences, including legitimate
        # staggered glyph changes. Only a complete caption handoff owns a veto.
        return ((current.style,current.name,current.row)==(e.style,e.name,e.row) and
                abs(e.start_s-current.end_s)<=.011 and
                (e.style,e.name,e.row,round(e.start_s,2)) in index.caption_handoffs)
    ending = index.ends.get((*row,round(current.end_s,2)),set())
    beginning = index.starts.get(boundary,set())
    changed_row = (e.start_s > current.start_s and e.end_s > current.end_s and
                   len(ending)>1 and len(beginning)>1 and ending != beginning and
                   current.end_s-e.start_s <= .2*min(current.duration,e.duration))
    return changed_row or (abs(e.start_s-current.end_s)<=.011 and boundary in index.touching)


def coalesce_lyric_phases(events: list[Event], visible_map: dict[int, str], *,
                          phase_groups: dict[int,int] | None = None,
                          lyric_boundaries: LyricBoundaryIndex | None = None) -> tuple[list[Event], int]:
    """Join glyph phases with sustained colours, keeping lyric rows separate."""
    boundaries = lyric_boundaries or _index_lyric_boundaries(events,visible_map,phase_groups=phase_groups)
    groups: dict[tuple,list[Event]] = {}
    output = []
    for e in events:
        pos = get_pos(e.text)
        visible = visible_map.get(e.source_index,'')
        admitted = e.lyric if phase_groups is None else e.source_index in phase_groups
        if e.kind != 'Dialogue' or not admitted or pos is None:
            output.append(e)
            continue
        if OVERRIDE_RE.search(e.text,re.match(r"(?:\{[^}]*\})*",e.text).end()):
            # A final state cannot describe differently painted inline spans.
            # Retain them, but still record their surrounding row boundaries.
            output.append(e)
            continue
        key = (e.style, e.name, e.layer, e.margin_l, e.margin_r, e.margin_v,
               round(pos[0] / e.unit, 1) * e.unit, round(pos[1] / e.unit, 1) * e.unit, visible, text_layout_key(e), placement_key(e))
        if phase_groups is not None:
            key += (phase_groups[e.source_index],)
        groups.setdefault(key, []).append(e)
    removed = 0
    for group in groups.values():
        group.sort(key=lambda e: (e.start_s, e.end_s, e.source_index))
        current = group[0]
        paint_events = [current]
        runs = []
        for e in group[1:]:
            if (e.start_s <= current.end_s + 0.011 and
                    not _crosses_lyric_boundary(boundaries,current,e)):
                end = max(current.end_s, e.end_s)
                current = replace_event(current, end=format_time(end), end_s=end,
                                  source_index=min(current.source_index, e.source_index))
                paint_events.append(e)
                removed += 1
            else:
                runs.append((current,paint_events))
                current = e
                paint_events = [e]
        runs.append((current,paint_events))
        for caption,phases in runs:
            # Select once from original intervals, not from successively
            # extended representatives whose colours would get extra votes.
            if any(phase.state.get(k) != caption.state.get(k)
                   for phase in phases for k in ("1c","3c","4c")):
                state = select_static_state(caption.state,[],set(),caption.styles,
                    caption.defaults,paint_events=phases,continuation=caption.continuation).state
                tags = ''.join(render_tag(k,state[k]) for k in ("1c","3c","4c")
                               if k in state and state[k] != caption.state.get(k))
                if tags:
                    text = caption.text
                    prefix_end = re.match(r"(?:\{[^}]*\})*",text).end()
                    if prefix_end:
                        text = text[:prefix_end-1]+tags+text[prefix_end-1:]
                    else:
                        text = '{'+tags+'}'+text
                    caption = replace_event(caption,text=text)
            output.append(_preserve_frame_pose_support(phases[0],caption,phases)
                          if len(phases)>1 else caption)
    return sorted(output, key=lambda e: e.source_index), removed


def collapse_matching_lyric_layers(events: list[Event],
                                   visible_map: dict[int, str],
                                   font_metrics: FontMetrics | None = None) -> tuple[list[Event], int]:
    """Remove complete lyric copies only after exact-font text/anchor proof.

    Keep authored capitalization and spacing, layout and paint. Matching rows
    may supply a readable entrance or exit beyond the retained full caption.
    Event formatting, visibility and font catalogs are borrowed read-only.
    """
    if font_metrics is None or not font_metrics.available:
        return events, 0

    def eligible(e: Event) -> bool:
        word = visible_map.get(e.source_index, '')
        pos = get_pos(e.text)
        return (e.kind == 'Dialogue' and e.lyric and not e.effect and word and
                pos is not None and OVERRIDE_RE.sub('', e.text) == word and
                not inline_layout_key(e) and not e.state.get('p', 0) and
                e.state.get('borderstyle', 1) == 1 and e.state.get('1a', 0) == 0 and
                not any(k in e.state for k in ('clip', 'iclip', 'org')) and
                unrotated_text_state(e.state) and
                all(math.isfinite(v) for v in (*pos, e.start_s, e.end_s, e.unit)) and
                all(math.isfinite(e.state.get(k, DEFAULT_STATE[k]))
                    for k in ('fs', 'fscx', 'fscy', 'fsp', 'an', 'fax', 'fay')) and
                all(e.state.get(k, DEFAULT_STATE[k]) > 0 for k in ('fs', 'fscx', 'fscy')) and
                e.state.get('an', 2) in range(1, 10) and
                all(abs(e.state.get(k, 0)) <= .001 for k in ('fax', 'fay')) and
                e.unit > 0 and e.duration > 0 and
                not any(c in word for c in ('\\', '\n', '\r', '\t')) and
                static_object_key(e, e.styles) is not None)

    lines = [e for e in events if eligible(e)]
    groups: dict[tuple, list[Event]] = {}
    # Ineligible members must not disappear from a phase's completeness proof.
    for e in events:
        if e.kind == 'Dialogue' and e.lyric and get_pos(e.text) is not None and visible_map.get(e.source_index):
            groups.setdefault((e.start, e.end, e.style, e.name, e.row), []).append(e)

    removed: set[int] = set()
    extended: dict[int, Event] = {}
    for (start, end, style, name, _band), group in groups.items():
        if any(not eligible(e) or e.source_index in removed or e.source_index in extended for e in group):
            continue
        positions: dict[float, list[Event]] = {}
        for e in group:
            positions.setdefault(x_key(e), []).append(e)
        if (len(positions) < 3 or any(len({visible_map[e.source_index] for e in col}) != 1
                                      for col in positions.values())):
            continue
        columns = [positions[x] for x in sorted(positions)]
        ids = {e.source_index for e in group}
        proposals = []
        for line in lines:
            if (line.source_index in ids or line.source_index in removed or line.row != _band or
                    placement_key(line) != placement_key(group[0]) or
                    line.style != style or line.name != name):
                continue
            overlap = min(line.end_s, group[0].end_s) - max(line.start_s, group[0].start_s)
            if overlap + 1e-9 < 0.8 * min(line.duration, group[0].duration):
                continue
            literal = visible_map[line.source_index]
            model = authored_glyph_positions(font_metrics, line.state, literal,
                                             get_pos(line.text)[0], line.unit)
            if model is None:
                continue
            cursor = glyph_cursor = 0
            errors = []
            for column in columns:
                word = visible_map[column[0].source_index]
                # Spaces omitted BETWEEN fragments are verified by their
                # authored advances. Spaces within a fragment remain literal.
                while cursor < len(literal) and literal[cursor].isspace():
                    cursor += 1
                if not literal.startswith(word, cursor):
                    break
                target = model[glyph_cursor:glyph_cursor + sum(not c.isspace() for c in word)]
                if not target:
                    break
                valid = True
                for e in column:
                    if (text_layout_key(e) != text_layout_key(line) or e.measurement != line.measurement or
                            placement_key(e) != placement_key(line) or
                            any(e.state.get(k, DEFAULT_STATE.get(k)) != line.state.get(k, DEFAULT_STATE.get(k))
                                for k in ('1c', '3c', '1a', '3a'))):
                        valid = False; break
                    pos = get_pos(e.text)
                    actual = authored_glyph_positions(font_metrics, e.state, word, pos[0], e.unit)
                    tolerance = .25 * min(e.unit, line.unit)
                    if (actual is None or len(actual) != len(target) or
                            abs(pos[1] - get_pos(line.text)[1]) > tolerance or
                            any(a != b or abs(x-y) > tolerance for (a,x),(b,y) in zip(actual,target))):
                        valid = False; break
                    errors.extend(abs(x-y) for (_,x),(_,y) in zip(actual,target))
                if not valid:
                    break
                cursor += len(word)
                glyph_cursor += len(target)
            else:
                if not literal[cursor:].strip() and glyph_cursor == len(model):
                    proposals.append((max(errors), line.source_index, line))
        if proposals:
            # Nearby identical full-copy layers are equivalent witnesses;
            # prefer the exact anchor deterministically, independent of order.
            line = min(proposals, key=lambda item: item[:2])[2]
            removed.update(ids)
            previous = extended.get(line.source_index, line)
            earlier = min(previous.start_s, group[0].start_s)
            later = max(previous.end_s, group[0].end_s)
            extended[line.source_index] = replace_event(line, start=format_time(earlier),
                end=format_time(later), start_s=earlier, end_s=later)

    output = [extended.get(e.source_index, e) for e in events if e.source_index not in removed]
    return output, len(removed)


def collapse_full_lyric_copies(events: list[Event],
                               visible_map: dict[int, str]) -> TextVisibilityResult:
    """Collapse overlapping full-line copies and return accepted caption text.

    A private overlay preserves pending text for later clusters without
    changing the borrowed map or copying its history.
    """
    visibility_updates: dict[int,str] = {}
    visible_map = collections.ChainMap(visibility_updates,visible_map)
    def norm(value: str) -> str:
        return "".join(value.split()).casefold()

    grouped: dict[tuple[str, str, str, int | None], list[Event]] = {}
    for e in events:
        visible = visible_map.get(e.source_index, "")
        if (e.kind == "Dialogue" and e.lyric and
                bool(norm(visible))):
            pos = get_pos(e.text)
            band = e.row if pos is not None else None
            grouped.setdefault((e.style, e.name, norm(visible), band, get_pos(e.text), placement_key(e)), []).append(e)

    removed: set[int] = set()
    replacements: dict[int, Event] = {}
    for group in grouped.values():
        for e in group:
            if e.source_index in removed:
                continue
            cluster = [other for other in group if other.source_index not in removed and
                       min(e.end_s, other.end_s) - max(e.start_s, other.start_s) >=
                       0.8 * min(e.duration, other.duration)]
            if len(cluster) < 2:
                continue
            # Prefer the author's spaced lyric when both a generated row and a
            # full-line copy exist, rather than keeping the inferred spacing.
            best = max(cluster, key=lambda item: (
                visible_map[item.source_index].count(" "),
                item.effect == "", -item.source_index))
            first = min(cluster, key=lambda item: item.source_index)
            earlier = min(item.start_s for item in cluster)
            later = max(item.end_s for item in cluster)
            state = select_static_state(best.state,[],set(),best.styles,best.defaults,
                                        paint_events=cluster,continuation=best.continuation).state
            text = render_simplified_caption(state, visible_map[best.source_index],
                                      outline_states=[e.state for e in cluster],measurement=best.measurement,
                                      source_paint=_source_caption_paint(state,[best.state]) if
                                      max(best.state.get(k,best.state.get('bord',0)) for k in ('xbord','ybord')) > 0 and
                                      best.state.get('3a',0) < 255 else
                                      _source_caption_paint(state,[e.state for e in cluster]))
            caption = replace_event(
                first, layer="0", start=format_time(earlier), end=format_time(later),
                start_s=earlier, end_s=later, effect="",
                text=text)
            replacements[first.source_index] = _preserve_frame_pose_support(best,caption,cluster)
            visibility_updates[first.source_index] = visible_map[best.source_index]
            removed.update(item.source_index for item in cluster if item != first)

    return TextVisibilityResult([replacements.get(e.source_index, e) for e in events
            if e.source_index not in removed],len(removed),visibility_updates)


def _frame_sequence_paint_owner(events: list[Event]) -> Event:
    """Keep the frame freezer's visible-paint rule independent of source pose."""
    paint = {id(e):_frame_paint_alphas(e) for e in events}
    channel = next((c for c in range(3) if any(a[c]<254 for a in paint.values())),0)
    return min(events,key=lambda e:(paint[id(e)][channel],-e.duration,e.source_index))


def _near_static_frame_fits(reference: Event, candidate: Event, *, allow_inline: bool = False) -> bool:
    """Bound jitter against one source anchor; never follow cumulative drift."""
    pose = {'pos','fscx','fscy','frz'}
    position,pos = get_pos(reference.text),get_pos(candidate.text)
    sx,sy = reference.state.get('fscx',100),reference.state.get('fscy',100)
    if (position is None or pos is None or sx<=0 or sy<=0 or
            reference.state.get('p',0) or (not allow_inline and (inline_layout_key(reference) or
            inline_layout_key(candidate))) or state_key(reference,pose)!=state_key(candidate,pose)):
        return False
    height = text_height(reference)
    width = abs(reference.state.get('fs',20)*sx/100)*max(1,len(OVERRIDE_RE.sub('',reference.text)))
    radius = math.dist(pos,candidate.state.get('org',pos))+math.hypot(width,height)
    angle = math.radians(math.remainder(candidate.state.get('frz',0)-reference.state.get('frz',0),360))
    error = (math.dist(pos,position)+abs(candidate.state.get('fscx',100)-sx)/sx*width+
             abs(candidate.state.get('fscy',100)-sy)/sy*height+2*radius*abs(math.sin(angle/2)))
    return error<=.02*height


def _literal_paint_ranges(events: list[Event]) -> list[tuple] | None:
    """Align resolved paint by exact literal offsets, independent of tag splitting.

    Geometry/ownership admission belongs to the caller. Inputs are borrowed;
    drawings, animation or different literals cannot establish correspondence.
    """
    streams,boundaries,literal = [],{0},None
    for e in events:
        obj = static_object_key(e,e.styles,allow_unpositioned=True)
        if obj is None or any(drawing for _,drawing,_ in obj[-1]):
            return None
        runs,cursor,words = [],0,''
        for signature,_,payload in obj[-1]:
            end = cursor+len(payload)
            runs.append((cursor,end,dict(signature.formatting)))
            boundaries.add(end);cursor=end;words+=payload
        if literal is not None and words != literal:
            return None
        literal=words;streams.append(runs)
    if not literal:
        return None
    points=sorted(boundaries);indices=[0]*len(streams);result=[]
    for start,end in zip(points,points[1:]):
        states=[]
        for i,runs in enumerate(streams):
            while runs[indices[i]][1]<=start:
                indices[i]+=1
            states.append(runs[indices[i]][2])
        result.append((literal[start:end],states))
    return result


def _literal_source_paint(state: dict, sources: list[dict], *, own_contour: bool,
                          measurement: DocumentMeasurementContext = DocumentMeasurementContext()) -> dict:
    """Apply existing contour/fallback policy to one corresponding literal range."""
    if (state.get('1a',0)>=255 and
            (max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord'))<=0 or state.get('3a',0)>=255) and
            (max(abs(state.get(k,state.get('shad',0))) for k in ('xshad','yshad'))<=0 or state.get('4a',0)>=255)):
        # Known absence of paint is complete evidence, not an uncertain contour
        # requiring contrast repair. The literal still supplies its advance.
        return {**state,'1a':255,'3c':'000000','3a':0,'bord':0,'xbord':0,'ybord':0,
                'shad':0,'xshad':0,'yshad':0,'blur':0,'be':0}
    stroke = max(state.get(k,state.get('bord',0)) for k in ('xbord','ybord'))>0 and state.get('3a',0)<255
    proof = _source_caption_paint(state,[state] if own_contour and stroke else sources)
    body = render_simplified_caption(state,'',outline_states=sources,source_paint=proof,measurement=measurement)
    selected = effective_state(body,DEFAULT_STATE,{})
    # Complete authored span evidence retains its base transparency. A coupled
    # source fade settles at that base, rather than becoming an opaque stroke.
    selected['1a']=state.get('1a',0)
    if proof is not None and max(proof.border)>0 and state.get('1a',0)==state.get('3a',0):
        selected['3a']=state.get('1a',0)
    return selected


def _render_literal_paint(e: Event, ranges: list[tuple], paints: list[dict],
                          paint_tags: set[str], *, strip_clip: bool = False) -> str:
    """Replay authored geometry/resets, emitting proved paint at exact offsets."""
    boundaries=[];cursor=0
    for fragment,_ in ranges:
        cursor+=len(fragment);boundaries.append(cursor)
    live=e.defaults.copy();continuation=OverrideContinuation()
    output=[];cursor=index=0
    def value(state,tag):
        return state.get(tag,state.get(tag[1:],0) if tag in
            {'xbord','ybord','xshad','yshad'} else DEFAULT_STATE.get(tag,0))
    for part in re.split(r'(\{[^}]*\})',e.text):
        if part.startswith('{') and part.endswith('}'):
            tokens=[(k,v) for k,v in tokenize_override(part[1:-1])
                    if k not in paint_tags and not (strip_clip and k in {'clip','iclip'})]
            block=''.join('\\'+k+v for k,v in tokens)
            if block:output.append('{'+block+'}')
            for k,v in tokens:
                continuation=apply_override(live,k,v,e.styles,e.defaults,continuation)
        elif part:
            offset=0
            while offset<len(part):
                while boundaries[index]<=cursor:index+=1
                end=min(len(part)-offset,boundaries[index]-cursor)
                tags=''
                for k in CAPTION_PAINT_TAGS:
                    if k in paint_tags and k not in {'2c','2a','4c','4a'} and value(live,k)!=value(paints[index],k):
                        tag=render_tag(k,value(paints[index],k));tags+=tag
                        continuation=apply_override(live,k,tag[len(k)+1:],e.styles,e.defaults,continuation)
                if tags:output.append('{'+tags+'}')
                output.append(part[offset:offset+end]);offset+=end;cursor+=end
    return ''.join(output)


def _normalize_inline_frame_paint(events: list[Event]) -> list[Event] | None:
    """Settle corresponding span paint, preserving intentional spatial variation."""
    ranges=_literal_paint_ranges(events)
    if ranges is None:return None
    paint=set(CAPTION_PAINT_TAGS)|{'alpha','c'}
    # Preserve existing geometry eligibility: every span of an event must have
    # the same resolved layout. Equivalent paint resets are now admissible.
    for i,e in enumerate(events):
        layouts={state_key(dataclass_replace(e,state=states[i]),paint) for _,states in ranges}
        if len(layouts)!=1:return None
    palettes,blocked={1:{},3:{}},set()
    for fragment,states in ranges:
        for e,state in zip(events,states):
            if state.get('1a',0)>=255:continue
            for channel in (1,3):
                color=str(state.get(f'{channel}c','')).upper()
                if (not re.fullmatch(r'[0-9A-F]{6}',color) or state.get(f'{channel}a',0)>=254 or
                        channel==3 and (state.get('borderstyle',1)!=1 or
                        max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord'))<=0)):
                    blocked.add(channel);continue
                votes=palettes[channel]
                votes[color]=votes.get(color,0)+round(e.duration,6)*len(fragment)
    representatives={c:_bounded_text_color(votes) for c,votes in palettes.items() if c not in blocked}
    paints=[]
    for fragment,states in ranges:
        states=[{**state,**{f'{c}c':color for c,color in representatives.items() if color is not None}}
                for state in states]
        visible=[(e,s) for e,s in zip(events,states) if s.get('1a',0)<255]
        if not visible:
            if any(any(a<255 for a in _frame_paint_alphas(dataclass_replace(e,state=state)))
                   for e,state in zip(events,states)):
                return None
            # Authored invisible glyphs can provide spacing. Preserve their
            # advance and absence of paint instead of inventing a visible glyph.
            paints.append(_literal_source_paint(states[0],states,own_contour=False))
            continue
        chosen,state=min(visible,key=lambda p:(p[1].get('1a',0),-round(p[0].duration,6),p[0].source_index))
        # Visible temporal color/contour changes are not evidence of a fade.
        # Keep those phases rather than freeze a gradient or flashing outline.
        if len({s.get('1c') for _,s in visible})>1:return None
        sources=[s for _,s in visible]
        proof=_source_caption_paint(state,sources)
        if proof is None and any(max(s.get(k,s.get('bord',0)) for k in ('xbord','ybord'))>0
                                 and s.get('3a',0)<255 for s in sources):
            return None
        selected=_literal_source_paint(state,sources,own_contour=False,measurement=chosen.measurement)
        if selected.get('pos')!=state.get('pos'):return None
        paints.append(selected)
    normalized=[]
    fragments=[fragment for fragment,_ in ranges];literal=''.join(fragments)
    for i,e in enumerate(events):
        state=ranges[0][1][i]
        if any(k in state for k in ('clip','iclip')):return None
        header=render_simplified_caption(state,'',source_paint=_source_caption_paint(state,[state]),
                                         measurement=e.measurement)
        if effective_state(header,e.defaults,e.styles).get('pos')!=state.get('pos'):return None
        # All spans have proved uniform geometry. Resolve equivalent resets
        # once, then attach paint by exact literal offsets rather than keeping
        # incidental phase tag splitting in the frame identity.
        span_tags=tuple(k for k in CAPTION_PAINT_TAGS if k not in {'2c','2a','4c','4a'})
        text=render_caption_spans(header,fragments,literal,paints,span_tags,e,exact=True)
        normalized.append(replace_event(e,text=text))
    # Reuse the final bounded palette policy; never chain nearby colors or
    # collapse a wider gradient. Hidden/unused channels retain its veto rules.
    normalized,_=normalize_near_text_colors(normalized)
    for i,(source,caption) in enumerate(zip(events,normalized)):
        if source.evidence.frame_pose_intervals is not None:
            intervals=_frame_pose_intervals(source)
        else:
            # Geometry is uniform, but visibility need not be. Hand source
            # exposure to v200's selector before restored exit paint can vote
            # as though every hidden letter had actually been displayed.
            weights=[len(''.join(fragment.split())) for fragment,_ in ranges]
            total=sum(weights)
            alphas=tuple(sum(weight*_frame_paint_alphas(dataclass_replace(source,state=states[i]))[c]
                for weight,(_,states) in zip(weights,ranges))/total if total else 255 for c in range(3))
            intervals=((source.start_s,source.end_s,alphas),)
        normalized[i]=dataclass_replace(caption,evidence=dataclass_replace(
            caption.evidence,frame_pose_intervals=intervals))
    return normalized


def merge_frame_animation(events: list[Event], visible_map: dict[int, str],
                          max_piece_duration: float = 0.16,
                          max_gap: float = 0.08,
                          min_pieces: int = 3,
                          merge_near_static: bool = False, *,
                          lyric_boundaries: LyricBoundaryIndex | None = None) -> tuple[list[Event], int]:
    # Group before joining: source-file event ordering is not rendering order.
    boundaries = lyric_boundaries or _index_lyric_boundaries(events,visible_map)
    groups: dict[tuple,list[Event]] = {}
    output=[]
    for e in events:
        visible=visible_map.get(e.source_index, "")
        if e.kind != "Dialogue" or not visible:
            output.append(e)
            continue
        groups.setdefault((e.style,e.name,e.layer,visible),[]).append(e)
    removed=0
    for group in groups.values():
        inline_paint_sources=set()
        ordered=sorted(group,key=lambda e:(e.start_s,e.end_s,e.source_index)) if merge_near_static else []
        if (merge_near_static and
                any(inline_layout_key(e) for e in group) and
                sum(e.duration<=max_piece_duration and
                    bool(re.search(r"\\(?:alpha|[1-4]a)&HFF&",e.text,re.I))
                    for e in group)>=2 and
                all(b.start_s>=a.end_s-1e-6 for a,b in zip(ordered,ordered[1:]))):
            families=[]
            for e in ordered:
                if not families or e.start_s>families[-1][-1].end_s+max_gap+1e-6:
                    families.append([])
                families[-1].append(e)
            group=[]
            for family in families:
                eligible=(any(inline_layout_key(e) for e in family) and
                    sum(e.duration<=max_piece_duration and
                        bool(re.search(r"\\(?:alpha|[1-4]a)&HFF&",e.text,re.I)) for e in family)>=2)
                normalized=_normalize_inline_frame_paint(family) if eligible else None
                if normalized is not None:
                    inline_paint_sources.update(e.source_index for e in normalized)
                group.extend(normalized if normalized is not None else family)
        frozen,count=freeze_vector_sequences(group,max_piece_duration,max_gap,
                                             near_static=merge_near_static,
                                             inline_paint_sources=frozenset(inline_paint_sources),
                                             lyric_boundaries=boundaries)
        output.extend(frozen)
        removed+=count
    return sorted(output,key=lambda e:e.source_index),removed


def freeze_vector_sequences(events: list[Event], short_duration: float = 0.16,
                            max_gap: float = 0.011,
                            near_static: bool = False, *,
                            inline_paint_sources: frozenset[int] = frozenset(),
                            lyric_boundaries: LyricBoundaryIndex | None = None) -> tuple[list[Event], int]:
    """Freeze frame-by-frame drawings, including their longer static hold.

    Match actual paths and static paint, not style names or colors specific
    to a show. Overlapping copies are ambiguous and remain separate.
    inline_paint_sources is a pass-local producer proof: those source identities
    have uniform resolved geometry and settled per-literal paint. Descendants
    retain a contributing identity; ordinary inline guards stay unchanged.
    """
    frame_removed=0
    if near_static:
        # First retain the established treatment of actual moving frames.
        # Its frozen holds can then be joined when only tracking jitter differs.
        events,frame_removed=freeze_vector_sequences(events,short_duration,max_gap,
                                                     inline_paint_sources=inline_paint_sources,
                                                     lyric_boundaries=lyric_boundaries)
    changing = {"pos","fscx","fscy","frz","frx","fry","fax","fay",
                "1a","2a","3a","4a"}
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        placement=placement_key(e)
        if e.source_index in inline_paint_sources and inline_layout_key(e):
            # The producer proved uniform geometry separately from span paint.
            # Match every settled paint range; raw inline tag spelling must not
            # block the existing motion proof. No general inline guard is relaxed.
            obj=static_object_key(e,e.styles,allow_unpositioned=True)
            pose={'pos','fscx','fscy','frz','frx','fry','fax','fay'}
            ranges=tuple((tuple((k,v) for k,v in sig.formatting if k not in pose),drawing,literal)
                         for sig,drawing,literal in obj[-1])
            placement=placement[:-1]+(('proved-span-paint',ranges),)
        key = (e.kind,e.layer,e.name,geometry_key(e.text),state_key(e,changing),placement)
        groups.setdefault(key,[]).append(e)

    output: list[Event] = []
    removed = frame_removed

    def emit(run: list[Event], settled: bool = False) -> None:
        nonlocal removed
        if (len(run) < 2 or not settled and
                (len(run) < 3 or
                 sum(e.duration <= short_duration + 1e-6 for e in run) < 2 or
                 len({e.text for e in run}) < 2)
                or any(b.start_s < a.end_s - 1e-6 for a, b in zip(run, run[1:]))):
            output.extend(run)
            return
        chosen,intervals = _representative_frame_pose(run)
        if settled and not all(_near_static_frame_fits(chosen,e,
                allow_inline=chosen.source_index in inline_paint_sources and e.source_index in inline_paint_sources) for e in run):
            # The fixed admission anchor prevents drift. The actual selected
            # pose must independently meet the same final displacement bound.
            output.extend(run)
            return
        paint_owner = _frame_sequence_paint_owner(run)
        if not inline_layout_key(chosen):
            # These frames already share static paint except alpha. Retain the
            # established unfaded paint without giving its pose extra dwell.
            alpha_tags = ''.join(render_tag(k,paint_owner.state.get(k,0))
                for k in ('1a','2a','3a','4a')
                if chosen.state.get(k,0)!=paint_owner.state.get(k,0))
            if alpha_tags:
                prefix = re.match(r'(?:\{[^}]*\})*',chosen.text).end()
                chosen = replace_event(chosen,text=chosen.text[:prefix]+'{'+alpha_tags+'}'+chosen.text[prefix:])
        output.append(replace_event(chosen, start=run[0].start, start_s=run[0].start_s,
                              end=run[-1].end, end_s=run[-1].end_s,
                              source_index=min(e.source_index for e in run),
                              evidence=dataclass_replace(chosen.evidence,frame_pose_intervals=intervals)))
        removed += len(run) - 1

    for group in groups.values():
        ordered = sorted(group, key=lambda e: (e.start_s, e.end_s, e.source_index))
        # Build time-connected components first so simultaneous identical
        # shapes cannot accidentally be connected to one another's frames.
        components: list[list[Event]] = []
        latest_end = -1.0
        for e in ordered:
            if (not components or e.start_s > latest_end + max_gap + 1e-6 or
                    lyric_boundaries is not None and
                    _crosses_lyric_boundary(lyric_boundaries,components[-1][-1],e,complete_only=True)):
                components.append([])
                latest_end = e.end_s
            components[-1].append(e)
            latest_end = max(latest_end, e.end_s)
        for component in components:
            if any(b.start_s < a.end_s - 1e-6 for a, b in zip(component, component[1:])):
                output.extend(component)
                continue
            if near_static:
                # A tracked sign may jump between several stable placements.
                # Merge bounded jitter within each hold, without requiring the
                # entire time-connected component to have one static pose.
                run=[]
                reference=None
                for candidate in component:
                    settled=(bool(run) and abs(candidate.start_s-run[-1].end_s)<=1e-6 and
                             _near_static_frame_fits(reference,candidate,
                                allow_inline=reference.source_index in inline_paint_sources and candidate.source_index in inline_paint_sources))
                    if run and not settled:
                        emit(run,True)
                        run=[]
                    if not run:
                        reference=candidate
                    run.append(candidate)
                emit(run,True)
                continue
            run: list[Event] = []
            has_hold = False
            for e in component:
                is_hold = e.duration > short_duration + 1e-6
                if is_hold and has_hold:
                    emit(run)
                    run, has_hold = [], False
                run.append(e)
                has_hold |= is_hold
            emit(run)
    return sorted(output, key=lambda e: e.source_index), removed


def reduce_vector_layers(events: list[Event]) -> tuple[list[Event], int]:
    # No arbitrary two-layer limit. Only remove exact opaque duplicates.
    seen, result = set(), []
    for e in sorted(events,key=lambda x:(-int(x.layer) if x.layer.lstrip("-").isdigit() else 0,x.source_index)):
        key = (e.start,e.end,geometry_key(e.text),state_key(e),placement_key(e))
        opaque = all(e.state.get(f"{c}a",0)==0 for c in (1,3,4))
        if opaque and key in seen:
            continue
        if opaque:
            seen.add(key)
        result.append(e)
    return sorted(result,key=lambda e:e.source_index),len(events)-len(result)


def remove_covered_vector_glows(events: list[Event]) -> tuple[list[Event], int]:
    """Deprecated: legacy simplification only; retained for reference.

    Remove a lower shape only when the same footprint is painted opaquely.

    Partial transparency is not evidence of coverage. Different stroke widths,
    transforms, offsets, or drawing modes are retained.
    """
    paint = {f"{c}{kind}" for c in range(1,5) for kind in "ca"}
    groups: dict[tuple,list[Event]] = {}
    for e in events:
        groups.setdefault((e.start,e.end,geometry_key(e.text),state_key(e,paint),placement_key(e)),[]).append(e)
    removed = set()
    for group in groups.values():
        ordered = sorted(group,key=lambda e:(int(e.layer) if e.layer.lstrip("-").isdigit() else 0,e.source_index),reverse=True)
        opaque_above = False
        for e in ordered:
            if opaque_above:
                removed.add(e.source_index)
            opaque_above |= all(e.state.get(f"{c}a",0)==0 for c in (1,3,4))
    return [e for e in events if e.source_index not in removed],len(removed)


def remove_fully_covered_vectors(events: list[Event], scaled_borders: bool = True):
    """Deprecated: legacy simplification only; retained for reference."""
    geometry = {e.source_index: g for e in events
                if (g := coverage_geometry(e, scaled_borders)) is not None}
    covers = [e for e in events if e.source_index in geometry and geometry[e.source_index][2]]
    removed = set()
    for lower in events:
        info = geometry.get(lower.source_index)
        if info is None:
            continue
        order = (int(lower.layer), lower.source_index)
        box = info[1]
        for upper in covers:
            if ((int(upper.layer), upper.source_index) <= order
                    or upper.start_s > lower.start_s or upper.end_s < lower.end_s):
                continue
            polygon = geometry[upper.source_index][0]
            xs,ys = zip(*polygon)
            if not (min(xs) < box[0] and min(ys) < box[1]
                    and max(xs) > box[2] and max(ys) > box[3]):
                continue
            if polygon_covers_box(polygon, box):
                removed.add(lower.source_index)
                break
    return [e for e in events if e.source_index not in removed], len(removed)


def drawing_extent(e: Event) -> float:
    # Control-point bounds are a conservative estimate for Bezier curves.
    # This is used only for an explicitly requested vector count budget.
    vals = [v for v in geometry_key(e.text) if isinstance(v,float)]
    if len(vals)<4 or len(vals)%2:
        return float("inf")  # Unrecognized geometry must not be lowest priority.
    xs,ys = vals[::2],vals[1::2]
    scale = 2**max(0,e.state.get("p",1)-1)
    return (max(xs)-min(xs))*(max(ys)-min(ys))*abs(e.state.get("fscx",100)*e.state.get("fscy",100))/10000/scale**2


def cap_vector_cues(events: list[Event], limit: int) -> tuple[list[Event], int]:
    if limit<=0:
        return events,0
    groups: dict[tuple,list[Event]] = {}
    for e in events:
        groups.setdefault((e.start,e.end),[]).append(e)
    result=[]
    for group in groups.values():
        result.extend(sorted(group,key=drawing_extent,reverse=True)[:limit])
    return sorted(result,key=lambda e:e.source_index),len(events)-len(result)


def rectangle_clip(e: Event):
    value = e.state.get("clip", "")
    if "iclip" in e.state or not re.fullmatch(r"\(\s*" + NUMBER + r"(?:\s*,\s*" + NUMBER + r"){3}\s*\)", value):
        return None
    coords = tuple(map(float, re.findall(NUMBER, value)))
    return coords if coords[0] < coords[2] and coords[1] < coords[3] else None


def join_text_clip_tiles(events: list[Event]) -> tuple[list[Event], int]:
    """Deprecated: legacy simplification only; retained for reference.

    Join adjacent rectangular clips with identical text and paint.

    Rectangles must exactly tile a larger rectangle. No gaps, overlaps,
    color approximation or transparency changes are allowed.
    """
    groups, output, layers = {}, [], {}
    for e in events:
        if e.kind == "Dialogue":
            layers.setdefault(e.layer, []).append(e)
        rect = rectangle_clip(e)
        if (e.kind != "Dialogue" or rect is None or inline_layout_key(e)
                or e.state.get("p", 0) or get_pos(e.text) is None):
            output.append(e)
            continue
        key = (e.start,e.end,e.layer,e.name,e.margin_l,e.margin_r,e.margin_v,
               OVERRIDE_RE.sub("",e.text),state_key(e,{"clip"}))
        groups.setdefault(key, []).append((e,rect))
    removed = 0
    for group in groups.values():
        ids = {e.source_index for e,r in group}
        low,high = min(ids),max(ids)
        first = group[0][0]
        if any(low < peer.source_index < high and peer.source_index not in ids
               and min(peer.end_s,first.end_s)>max(peer.start_s,first.start_s)
               for peer in layers[first.layer]):
            output.extend(e for e,r in group)
            continue
        changed = True
        while changed:
            changed = False
            for axis in (0,1):
                other = 1-axis
                group.sort(key=lambda pair:(pair[1][other],pair[1][other+2],pair[1][axis]))
                joined = []
                for event,rect in group:
                    if joined:
                        previous,pr = joined[-1]
                        if pr[other]==rect[other] and pr[other+2]==rect[other+2] and pr[axis+2]==rect[axis]:
                            union = list(pr); union[axis+2] = rect[axis+2]; union=tuple(union)
                            value = "("+",".join(f"{v:g}" for v in union)+")"
                            text = re.sub(r"\\clip\([^)]*\)",lambda _: "\\clip"+value,previous.text)
                            state = previous.state.copy(); state["clip"]=value
                            joined[-1]=(replace_event(previous,text=text,state=state,
                                source_index=min(previous.source_index,event.source_index)),union)
                            removed += 1; changed = True
                            continue
                    joined.append((event,rect))
                group = joined
        output.extend(e for e,r in group)
    return sorted(output,key=lambda e:e.source_index),removed


def reduce_text_layers(events: list[Event], visible_map: dict[int, str],
                       blockers: list[Event] | None = None) -> tuple[list[Event], int]:
    """Deprecated: legacy simplification only; retained for reference.

    Flatten identical opaque text into its foreground and one outline.

    Layout, clipping and literal line breaks must match. Translucent paints,
    mixed spans and differing outline colors remain separate.
    """
    groups = {}
    for e in events:
        if (e.kind != "Dialogue" or inline_layout_key(e) or e.state.get("p",0)
                or get_pos(e.text) is None or not e.layer.lstrip("-").isdigit()):
            groups.setdefault((e.source_index,),[]).append(e)
            continue
        key=(e.start,e.end,e.name,get_pos(e.text),OVERRIDE_RE.sub("",e.text),
             text_layout_key(e),placement_key(e))
        groups.setdefault(key,[]).append(e)
    peers = events + (blockers or [])
    output=[]
    for group in groups.values():
        if len(group)<2:
            output.extend(group); continue
        # A single output cannot preserve independently positioned shadows
        # or the accumulation of translucent paints.
        if any(any(e.state.get(k,0) for k in ("shad","xshad","yshad","blur","be"))
               or e.state.get("1a",0) not in (0,255) for e in group):
            output.extend(group); continue
        fills=[e for e in group if e.state.get("1a",0)==0]
        if not fills:
            output.extend(group); continue
        foreground=max(fills,key=lambda e:(int(e.layer),e.source_index))
        ids={e.source_index for e in group}
        low=min((int(e.layer),e.source_index) for e in group)
        high=max((int(e.layer),e.source_index) for e in group)
        if any(peer.kind=="Dialogue" and peer.source_index not in ids
               and peer.layer.lstrip("-").isdigit()
               and low < (int(peer.layer),peer.source_index) < high
               and min(peer.end_s,foreground.end_s)>max(peer.start_s,foreground.start_s)
               for peer in peers):
            output.extend(group); continue
        contours=[]
        for e in group:
            bx=e.state.get("xbord",e.state.get("bord",0))
            by=e.state.get("ybord",e.state.get("bord",0))
            if max(bx,by)>0 and e.state.get("3a",0)<255:
                contours.append((e,bx,by))
        if (any(e.state.get("3a",0)!=0 for e,x,y in contours)
                or len({e.state.get("3c","000000") for e,x,y in contours})>1):
            output.extend(group); continue
        bx=max((x for e,x,y in contours),default=0)
        by=max((y for e,x,y in contours),default=0)
        # Crossed anisotropic outlines do not equal one larger outline.
        if contours and not any(x==bx and y==by for e,x,y in contours):
            output.extend(group); continue
        if contours:
            color=contours[0][0].state.get("3c","000000")
            tags=f"\\xbord{bx:g}\\ybord{by:g}\\3c&H{color}&\\3a&H00&"
            text=foreground.text
            if text.startswith("{"):
                end=text.index("}"); text=text[:end]+tags+text[end:]
            else:
                text="{"+tags+"}"+text
            state=foreground.state.copy()
            state.update(xbord=bx,ybord=by,**{"3c":color,"3a":0})
            foreground=replace_event(foreground,text=text,state=state)
        output.append(foreground)
    return sorted(output,key=lambda e:e.source_index),len(events)-len(output)


def static_text_paint_geometry(e: Event, paint: set[str]):
    """Resolve literal spans, coalescing boundaries that change only paint."""
    obj = static_object_key(e,e.styles,allow_unpositioned=True)
    geometry = []
    if obj is not None:
        for signature,drawing,payload in obj[-1]:
            state = dict(signature.formatting)
            if drawing or state.get("borderstyle",1) != 1:
                return None
            layout = state_key(dataclass_replace(e,state=state,continuation=signature.continuation),paint | {"clip","iclip"})
            if geometry and geometry[-1][0] == layout:
                geometry[-1] = (layout,geometry[-1][1]+payload)
            else:
                geometry.append((layout,payload))
    return (tuple(geometry),obj[-1]) if geometry else None


def static_text_paint_caption(e: Event, outlines: list[dict], paint: set[str], *,
                              source_events: list[Event] | None = None):
    """Use simplified caption paint selection without rewriting authored text geometry."""
    if inline_layout_key(e):
        sources=[e]+[p for p in (source_events or []) if p is not e]
        ranges=_literal_paint_ranges(sources)
        if ranges is None:return None
        paints=[_literal_source_paint(states[0],states if source_events is not None else outlines,
                                     own_contour=True,measurement=e.measurement) for _,states in ranges]
        if any(paint.get('pos')!=states[0].get('pos') for paint,(_,states) in zip(paints,ranges)):
            return None
        return _render_literal_paint(e,ranges,paints,paint,strip_clip=True)
    header = render_simplified_caption(e.state,"",outline_states=outlines,measurement=e.measurement,
                                       source_paint=_source_caption_paint(e.state,outlines))
    normalized = effective_state(header,e.defaults,e.styles)
    if normalized.get("pos") != e.state.get("pos"):
        return None
    tags = "".join("\\"+name+value for name,value in
                   tokenize_override(header[1:-1]) if name in paint)
    def retain_geometry(match):
        geometry = "".join("\\"+name+value for name,value in
                           tokenize_override(match[1])
                           if name not in paint | {"clip","iclip"})
        return "{"+geometry+tags+"}"
    text = OVERRIDE_RE.sub(retain_geometry,e.text)
    return text if text.startswith("{") else "{"+tags+"}"+text


def flatten_held_text_paint_copies(events: list[Event], visible_map: dict[int,str],
                                  paint: set[str], source_events: dict[int,Event],
                                  max_piece_duration: float) -> tuple[list[Event],int]:
    """Replace unpositioned paint copies beneath a full opaque hold.

    Match every literal span's geometry, retaining the foreground's layer,
    source order and interval. Only remove complete, isolated lower-layer
    components: an unrelated collision peer keeps the whole component.
    """
    families, layers = {}, {}
    for e in events:
        if e.kind != "Dialogue" or get_pos(e.text) is not None:
            continue
        layers.setdefault(e.layer,[]).append(e)
        if (not visible_map.get(e.source_index) or not e.layer.lstrip("-").isdigit()
                or e.effect or e.duration <= 0 or e.state.get("p",0)):
            continue
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
               visible_map[e.source_index])
        families.setdefault(key,[]).append(e)
    pending, copy_outlines = {}, {}
    for family in families.values():
        holds = [e for e in family if e.duration > max_piece_duration and
                 e.state.get("1a",0) == 0 and not inline_layout_key(e) and
                 not any(k in e.state for k in ("clip","iclip"))]
        if not holds:
            continue
        geometry = {}
        for hold in holds:
            profile = static_text_paint_geometry(hold,paint)
            if profile is not None:
                geometry[hold.source_index] = profile[0]
        for e in family:
            parents = [hold for hold in holds if int(hold.layer) > int(e.layer) and
                       hold.start_s <= e.start_s+1e-6 and hold.end_s >= e.end_s-1e-6 and
                       hold.source_index in geometry]
            if not parents:
                continue
            source = source_events.get(e.source_index,e)
            source_state = source.state or effective_state(source.text,source.defaults,source.styles)
            if source.effect or any(name in {"clip","iclip"} for block in
                                    OVERRIDE_RE.findall(source.text)
                                    for name,value in tokenize_override(block)):
                continue
            glow = any(abs(source_state.get(k,0)) > 0
                       for k in ("blur","be","shad","xshad","yshad"))
            # A short inline paint frame is also evidence after a prior run
            # removed its blur. Geometry still has to match the complete hold.
            frame = e.duration <= max_piece_duration and bool(inline_layout_key(e))
            coextensive = any(hold.start == e.start and hold.end == e.end for hold in parents)
            if not glow and not frame and not coextensive:
                continue
            profile = static_text_paint_geometry(e,paint)
            if profile is None or any("clip" in dict(s.formatting) or "iclip" in dict(s.formatting)
                                      for s,_,_ in profile[1]):
                continue
            parents = [hold for hold in parents if geometry[hold.source_index] == profile[0]]
            if len(parents) == 1 and (glow or frame or
                    parents[0].start == e.start and parents[0].end == e.end):
                pending[e.source_index] = (e,parents[0])
                # The outline selector only distinguishes one valid colour
                # from conflicting colours. Two samples preserve that evidence
                # without retaining every frame's complete inline state.
                samples = {}
                for signature,_,_ in profile[1]:
                    state = dict(signature.formatting)
                    colour = str(state.get("3c","000000")).upper()
                    if (state.get("3a",0) == 0 and
                            max(state.get("xbord",state.get("bord",0)),
                                state.get("ybord",state.get("bord",0))) > 0 and
                            re.fullmatch(r"[0-9A-F]{6}",colour)):
                        samples.setdefault(colour,state)
                        if len(samples) == 2:
                            break
                copy_outlines[e.source_index] = list(samples.values())
    removed, outlines = set(), {}
    for layer,peers in layers.items():
        copies = sorted((e for e in peers if e.source_index in pending),
                        key=lambda e:(e.start_s,e.end_s,e.source_index))
        foreign = [e for e in peers if e.source_index not in pending]
        components = []
        latest_end = -math.inf
        for e in copies:
            if not components or e.start_s > latest_end+1e-6:
                components.append([])
                latest_end = e.end_s
            components[-1].append(e)
            latest_end = max(latest_end,e.end_s)
        for component in components:
            start,end = component[0].start_s,max(e.end_s for e in component)
            if any(peer.start_s < end and peer.end_s > start for peer in foreign):
                continue
            for e in component:
                removed.add(e.source_index)
                parent = pending[e.source_index][1]
                outlines.setdefault(parent.source_index,[]).extend(copy_outlines[e.source_index])
    output = []
    for e in events:
        if e.source_index in removed:
            continue
        if e.source_index in outlines:
            text = static_text_paint_caption(e,[e.state]+outlines[e.source_index],paint)
            if text is not None:
                e = replace_event(e,text=text,effect="")
        output.append(e)
    return output,len(removed)


def _glow_source_geometry(e: Event) -> tuple | None:
    """Uniform stationary source layout; paint animation is evaluated separately."""
    if (e.kind != 'Dialogue' or e.duration <= 0 or get_pos(e.text) is None or
            e.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'} or
            not e.layer.lstrip('-').isdigit() or inline_layout_key(e) or
            not unrotated_text_state(e.state) or e.state.get('p',0) or
            any(k in e.state for k in ('clip','iclip','org')) or
            any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay')) or
            any(tag in {'move','r','k','kf','ko','kt','fade'}
                for tag,value in event_override_tokens(e))):
        return None
    fades = [value for tag,value in event_override_tokens(e) if tag == 'fad']
    if fades:
        if len(fades) != 1:
            return None
        try:
            values = [float(v) for v in fades[0].strip('()').split(',')]
        except ValueError:
            return None
        if (len(values) != 2 or not all(math.isfinite(v) and v >= 0 for v in values) or
                sum(values) > e.duration*1000):
            return None
    return text_layout_key(e)


def _returning_glow_highlight(e: Event) -> tuple[str,float,float] | None:
    """Prove one foreground pulse returns to its base without changing layout/opacity."""
    transforms = [value for tag,value in event_override_tokens(e) if tag == 't']
    if len(transforms) != 2 or e.state.get('1a',0) >= 128:
        return None
    parsed = [parse_effect_transform(value,e.duration,{'c','1c','blur','be','fscx','fscy'},
                                    allow_instant=True) for value in transforms]
    if any(p is None for p in parsed):
        return None
    first,last = parsed
    if first[1] > last[0] or last[1] > e.duration*1000+50:
        return None
    state = e.state.copy()
    continuation = e.continuation
    for tag,value in first[2]:
        continuation = apply_override(state,tag,value,e.styles,e.defaults,continuation)
    color = state.get('1c')
    if color == e.state.get('1c') or not re.fullmatch(r'[0-9A-F]{6}',str(color)):
        return None
    if any(not .5 <= state.get(k,100)/max(.01,e.state.get(k,100)) <= 1.5
           for k in ('fscx','fscy')):
        return None
    for tag,value in last[2]:
        continuation = apply_override(state,tag,value,e.styles,e.defaults,continuation)
    if (state.get('1c') != e.state.get('1c') or
            any(state.get(k,100) != e.state.get(k,100) for k in ('fscx','fscy'))):
        return None
    return color,e.start_s+first[0]/1000,e.start_s+last[1]/1000


def _matching_glow_pulse_geometry(glow: Event, foreground: Event) -> bool:
    """Keep a persistent glow's paint while admitting synchronized restored scale pulses."""
    if (tuple(value for tag,value in event_override_tokens(glow) if tag == 'fad') !=
            tuple(value for tag,value in event_override_tokens(foreground) if tag == 'fad')):
        return False
    values = [value for tag,value in event_override_tokens(glow) if tag == 't']
    if not values:
        return True
    targets = [value for tag,value in event_override_tokens(foreground) if tag == 't']
    if len(values) != 2 or len(targets) != 2:
        return False
    for value,target in zip(values,targets):
        a = parse_effect_transform(value,glow.duration,{'fscx','fscy','blur','be'},allow_instant=True)
        b = parse_effect_transform(target,foreground.duration,
            {'c','1c','fscx','fscy','blur','be'},allow_instant=True)
        if a is None or b is None or a[:2] != b[:2]:
            return False
        first,second = glow.state.copy(),foreground.state.copy()
        ca,cb = glow.continuation,foreground.continuation
        for tag,argument in a[2]:
            ca = apply_override(first,tag,argument,glow.styles,glow.defaults,ca)
        for tag,argument in b[2]:
            cb = apply_override(second,tag,argument,foreground.styles,foreground.defaults,cb)
        if any(first.get(k,100) != second.get(k,100) for k in ('fscx','fscy')):
            return False
    return True


def _index_glow_pulse_paint(context: StackedTextContext) -> dict[int,GlowPulsePaint]:
    """Prove ordered returning word highlights, their glow and exact-font letter copies.

    Original geometry and blur are essential: freezing has already erased blur
    and expanded dissolving letters. Proofs expire with this stack pass. Complete
    rows are accepted atomically; competing owners and missing letters keep the
    ordinary fallback. Colors, names and number of words do not select a source.
    """
    timing_slack = .051  # Existing ~50 ms source-pulse correspondence tolerance.
    metric = context.font_metrics
    if not context.source_events or metric is None or not metric.available:
        return {}
    sources = context.source_events
    current = {e.source_index:e for group in context.groups.values() for e in group}
    resolved = {}
    def source_event(index):
        original = sources.get(index)
        if original is not None and index not in resolved:
            evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
            resolved[index] = dataclass_replace(original,state=evaluated.formatting,
                                                continuation=evaluated.continuation)
        return resolved.get(index)
    letters = {}
    rows = {}
    expected = {}
    for key,group in context.groups.items():
        proof = _prove_stacked_text_paint(context,group)
        if proof is None or not proof.solid_stack or proof.shadow_text or proof.static_shadow_text:
            continue
        chosen = _select_stacked_text_foreground(group,proof)
        original = source_event(chosen.source_index)
        if original is None or get_pos(original.text) is None:
            continue
        row_key = (original.start,original.end,original.style,original.name,
                   placement_key(original),text_layout_key(original),get_pos(original.text)[1])
        expected.setdefault(row_key,set()).add(original.source_index)
        if _glow_source_geometry(original) is None:
            continue
        if metric.matching_face(str(original.state.get('fn','')),
                original.state.get('b',0),bool(original.state.get('i',0))) is None:
            continue
        pulse = _returning_glow_highlight(original)
        if pulse is None:
            continue
        glow = []
        for copy in group:
            source = source_event(copy.source_index)
            if (source is not None and _glow_source_geometry(source) == _glow_source_geometry(original) and
                    _matching_glow_pulse_geometry(source,original) and
                    int(source.layer) < int(original.layer) and source.state.get('1a',255) < 128 and
                    source.state.get('blur',0) > max(0,original.state.get('blur',0)) and
                    source.state.get('1c') not in {original.state.get('1c'),pulse[0]}):
                glow.append(source)
        if len(glow) != 1:
            continue
        word = OVERRIDE_RE.sub('',original.text)
        family = (original.style,original.name,original.layer)
        if family not in letters:
            letters[family] = [e.source_index for e in sources.values()
                if (e.style,e.name,e.layer) == family and
                   OVERRIDE_RE.sub('',e.text) and
                   not OVERRIDE_RE.sub('',e.text).isspace()]
        possible = [sources[index] for index in letters[family]]
        possible = [source_event(e.source_index) for e in possible
            if abs(e.start_s-pulse[1]) <= timing_slack and abs(e.end_s-pulse[2]) <= timing_slack]
        def same_fragment_layout(e):
            if any(not .5 <= e.state.get(k,100)/max(.01,original.state.get(k,100)) <= 1.5
                   for k in ('fscx','fscy')):
                return False
            normalized = dataclass_replace(e,state={**e.state,
                'fscx':original.state.get('fscx',100),'fscy':original.state.get('fscy',100)})
            return _glow_source_geometry(normalized) == _glow_source_geometry(original)
        children = [e for e in possible
            # Dissolving copies can straddle the held cue by one source frame.
            # Bound that overhang independently of the pulse correspondence;
            # two allowed offsets must not accumulate into a longer overhang.
            if e.start_s >= original.start_s-timing_slack and e.end_s <= original.end_s+timing_slack and
               abs(e.start_s-pulse[1]) <= timing_slack and abs(e.end_s-pulse[2]) <= timing_slack and
               same_fragment_layout(e) and
               abs(get_pos(e.text)[1]-get_pos(original.text)[1]) <= original.unit and
               e.state.get('1c') == pulse[0]]
        children.sort(key=lambda e:get_pos(e.text)[0])
        whole = [e for e in children if OVERRIDE_RE.sub('',e.text) == word and
                 math.dist(get_pos(e.text),get_pos(original.text)) <= original.unit]
        glyphs = [e for e in children if e not in whole]
        if (glyphs and (''.join(OVERRIDE_RE.sub('',e.text) for e in glyphs) != word or
                len(glyphs) != len(word) or not matches_authored_glyph_positions(
                    metric,original.state,[get_pos(e.text)[0] for e in glyphs],word,
                    get_pos(original.text)[0],max(original.unit,.04*text_height(original))))):
            continue
        if not children:
            continue
        if any(e.source_index in current and
               OVERRIDE_RE.sub('',current[e.source_index].text) != OVERRIDE_RE.sub('',e.text)
               for e in children):
            # Earlier reconstruction can reuse an original index for different
            # literal content. That successor must not inherit fragment ownership.
            continue
        # A dissolving glyph is redundant only when its original animation
        # changes opacity/blur/scale, never position, text or paint.
        valid = True
        for child in children:
            transforms = [value for tag,value in event_override_tokens(child) if tag == 't']
            if len(transforms) != 1:
                valid = False; break
            transform = parse_effect_transform(transforms[0],child.duration,
                {'alpha','1a','2a','3a','4a','blur','be','fscx','fscy'},allow_instant=True)
            if transform is None:
                valid = False; break
            state = child.state.copy()
            continuation = child.continuation
            for tag,value in transform[2]:
                continuation = apply_override(state,tag,value,child.styles,child.defaults,continuation)
            if state.get('1a',0) < 254:
                valid = False; break
        if not valid:
            continue
        paint_copies = [source_event(e.source_index) for e in group]
        samples = _settled_caption_paint_samples(original,paint_copies,metric)
        if samples is None:
            continue
        rows.setdefault(row_key,[]).append((original,pulse,glow[0],children,samples))
    result = {}
    claims = {}
    for key,row in rows.items():
        row.sort(key=lambda p:get_pos(p[0].text)[0])
        starts = [p[1][1] for p in row]
        ends = [p[1][2] for p in row]
        if (set(p[0].source_index for p in row) != expected[key] or
                len(row) < 2 or len(set(starts)) < 2 or
                len({(p[0].state.get('1c'),p[1][0],p[2].state.get('1c')) for p in row}) != 1 or
                not (all(a <= b for a,b in zip(starts,starts[1:])) and
                     all(a <= b for a,b in zip(ends,ends[1:])) or
                     all(a >= b for a,b in zip(starts,starts[1:])) and
                     all(a >= b for a,b in zip(ends,ends[1:])))):
            continue
        paint = _pool_source_caption_paint([p[4] for p in row])
        fill,outline,outline_alpha = paint.fill,paint.outline,paint.outline_alpha
        for original,pulse,glow,children,samples in row:
            ids = frozenset(e.source_index for e in children)
            result[original.source_index] = GlowPulsePaint(fill,outline,ids,
                (original.state.get('fscx',100),original.state.get('fscy',100)),outline_alpha)
            for index in ids:
                claims[index] = claims.get(index,0)+1
    return {index:proof for index,proof in result.items()
            if all(claims[i] == 1 for i in proof.fragments)}


def _prepare_stacked_text_copies(events: list[Event], visible_map: dict[int,str],
                                 animated_sources: set[int] | None, max_piece_duration: float,
                                 source_events: dict[int,Event] | None,
                                 font_metrics: FontMetrics | None = None
                                 ) -> tuple[StackedTextContext,int]:
    """Run existing echo/held-paint reductions, then group copies and collision peers."""
    events, echo_removed = collapse_frame_text_echoes(
        events,max_piece_duration,source_events=source_events)
    events = [without_inert_spacing_tail(e)
              if e.source_index in (animated_sources or set()) and
                 e.state.get('1a',0) >= 254 and e.state.get('3a',0) >= 254
              else e for e in events]
    groups = {}
    kept = []
    collision_peers = {}
    paint = {"alpha", "1a", "2a", "3a", "4a", "c", "1c", "2c", "3c", "4c",
             "bord", "xbord", "ybord", "shad", "xshad", "yshad", "blur", "be"}
    if source_events is not None:
        events,paint_removed = flatten_held_text_paint_copies(
            events,visible_map,paint,source_events,max_piece_duration)
        echo_removed += paint_removed
    for e in events:
        if e.kind == "Dialogue" and get_pos(e.text) is None:
            collision_peers.setdefault(e.layer, []).append(e)
        visible = visible_map.get(e.source_index, "")
        pos = get_pos(e.text)
        if (e.kind != "Dialogue" or not visible or e.state.get("p", 0) > 0):
            kept.append(e)
            continue
        key = (e.start, e.end, e.style, e.name, e.margin_l, e.margin_r,
               e.margin_v, pos, visible)
        groups.setdefault(key, []).append(e)
    context = StackedTextContext(groups,kept,collision_peers,paint,animated_sources,source_events,font_metrics)
    _group_contained_stacked_paint(context,events)
    context.matched_backing_fades.update(_index_matched_backing_fades(context,events))
    context.glow_paint.update(_index_glow_pulse_paint(context))
    return context,echo_removed


def _group_contained_stacked_paint(context: StackedTextContext, events: list[Event]) -> None:
    """Admit a foreground inside one held backing, without equating lifetimes.

    Frame-scale endpoint offsets alone grant no ownership. Require original
    corresponding opaque glyph planes and an unobstructed paint-order interval.
    Ambiguous families, independent foregrounds and incomplete support stay out.
    The stack producer owns both the proof and its containing display interval.
    """
    if context.source_events is None:
        return
    families={}
    for key in context.groups:
        if key[-2] is not None:
            families.setdefault(key[2:],[]).append(key)
    for keys in families.values():
        for long_key in keys:
            if long_key not in context.groups:
                continue
            held=context.groups[long_key];anchor=held[0]
            overlaps=[key for key in keys if key!=long_key and key in context.groups and
                      context.groups[key][0].start_s<anchor.end_s and
                      context.groups[key][0].end_s>anchor.start_s]
            if len(overlaps)!=1:
                continue
            short_key=overlaps[0];inside=context.groups[short_key][0]
            if not (anchor.start_s<=inside.start_s and inside.end_s<=anchor.end_s and
                    0<max(inside.start_s-anchor.start_s,anchor.end_s-inside.end_s)<=.0500001):
                continue
            group=held+context.groups[short_key]
            if any(not e.layer.lstrip('-').isdigit() for e in group):
                continue
            chosen=max(group,key=lambda e:(int(e.layer),e.source_index))
            if chosen not in context.groups[short_key]:
                continue
            contour=_stacked_source_contour_paint(context,chosen,group)
            if contour is None:
                continue
            ids={e.source_index for e in group}
            low=min((int(e.layer),e.source_index) for e in group)
            high=(int(chosen.layer),chosen.source_index)
            foreign=[e for e in events if e.source_index not in ids and e.kind=='Dialogue' and
                     e.start_s<anchor.end_s and e.end_s>anchor.start_s and
                     (not e.layer.lstrip('-').isdigit() or low<(int(e.layer),e.source_index)<high)]
            box=caption_bounds(chosen,context.font_metrics)
            obstructed=False
            for other in foreign:
                bounds=caption_bounds(other,context.font_metrics)
                if box is None or bounds is None or (box[0]<bounds[2] and bounds[0]<box[2] and
                                                     box[1]<bounds[3] and bounds[1]<box[3]):
                    obstructed=True;break
            if obstructed:
                continue
            context.groups[long_key]=group
            del context.groups[short_key]
            context.contained_paint[frozenset(ids)]=(chosen,anchor,contour)


def _matched_backing_fade_phase(context: StackedTextContext, peers: list[Event]) -> BackingFadePhase | None:
    """Prove coincident borderless fill over a same-glyph stroked backing.

    This is a paint-plane relationship, including projective/inline geometry,
    not an axis-aligned coverage estimate. Temporal fade ownership is separate.
    """
    if (len(peers)!=2 or any(get_pos(e.text) is None or e.effect or
            not e.layer.lstrip('-').isdigit() for e in peers)):
        return None
    backing,foreground=sorted(peers,key=lambda e:(int(e.layer),e.source_index))
    profiles=[static_text_paint_geometry(e,context.paint) for e in (foreground,backing)]
    if any(p is None for p in profiles) or profiles[0][0]!=profiles[1][0]:
        return None
    for e in peers:
        original=(context.source_events or {}).get(e.source_index,e)
        if any(re.search(r'\\i?clip\s*\(',block,re.I) for block in OVERRIDE_RE.findall(original.text)):
            return None
    ranges=_literal_paint_ranges([foreground,backing])
    if ranges is None:return None
    paints=[];alphas=set();surface=[]
    for fragment,states in ranges:
        front,back=states
        alpha=front.get('1a',0)
        if (not isinstance(alpha,(int,float)) or not math.isfinite(alpha) or
                not 0<=alpha<=255 or back.get('1a',0)!=alpha or back.get('3a',0)!=alpha or
                any(s.get('borderstyle',1)!=1 or any(k in s for k in ('clip','iclip')) or
                    s.get('4a',0)<255 and any(s.get(k,s.get('shad',0)) for k in ('xshad','yshad'))
                    for s in states) or
                any(front.get(k,front.get('bord',0))!=0 for k in ('xbord','ybord')) or
                max(back.get(k,back.get('bord',0)) for k in ('xbord','ybord'))<=0 or
                back.get('1c')!=back.get('3c')):
            return None
        # Establish a candidate resting contour; the family must still supply
        # an actual opaque hold before this can authorize any replacement.
        front={**front,'1a':0,'3a':0};back={**back,'1a':0,'3a':0}
        proof=_source_caption_paint(front,[front,back])
        if proof is None:return None
        paints.extend([proof]*len(fragment));alphas.add(alpha)
        surface.extend([tuple(s.get(k,0) for s in states for k in ('blur','be'))]*len(fragment))
    if len(alphas)!=1:return None  # Independent letter fades are not a caption fade.
    return BackingFadePhase(foreground,backing,next(iter(alphas)),tuple(paints),tuple(surface))


def _index_matched_backing_fades(context: StackedTextContext, events: list[Event]) -> dict[frozenset[int],MatchedBackingFade]:
    """Carry opaque stack paint through its continuous shared entrance/exit fades.

    Evidence is pass-local. No pose is selected, no time is extended and no
    scrolling budget changes. Ambiguous, overlapping or flashing families retain
    their ordinary stack rules, including the translucent-composite guard.
    """
    families={}
    for key,peers in context.groups.items():
        families.setdefault(key[2:7]+(key[-1],),[]).append((key,peers))
    order=sorted((e for e in events if e.kind=='Dialogue' and e.layer.lstrip('-').isdigit()),
                 key=lambda e:(int(e.layer),e.source_index))
    ranks={e.source_index:i for i,e in enumerate(order)}
    unranked=[e for e in events if e.kind=='Dialogue' and not e.layer.lstrip('-').isdigit()]
    proved={}
    for family in families.values():
        if not any(len(peers)==2 and any(e.state.get('1a',0)>0 for e in peers)
                   for key,peers in family):
            continue
        components=[];end=-math.inf
        for key,peers in sorted(family,key=lambda p:(p[1][0].start_s,p[1][0].end_s)):
            if not components or peers[0].start_s>end+.011:
                components.append([])
            components[-1].append(peers);end=max(end,peers[0].end_s)
        for groups in components:
            if (len(groups)<2 or any(b[0].start_s<a[0].end_s-1e-6 for a,b in zip(groups,groups[1:]))):
                continue
            phases=[_matched_backing_fade_phase(context,peers) for peers in groups]
            if any(p is None for p in phases):continue
            opaque=[i for i,p in enumerate(phases) if p.alpha==0]
            if not opaque or len(opaque)==len(phases):continue
            first,last=opaque[0],opaque[-1]
            if (sum(groups[i][0].duration for i in opaque)<.02-1e-6 or
                    any(phases[i].alpha for i in range(first,last+1)) or
                    any(a.alpha<b.alpha for a,b in zip(phases[:first],phases[1:first+1])) or
                    any(a.alpha>b.alpha for a,b in zip(phases[last:],phases[last+1:]))):
                continue
            # Different opacity/paint legs cannot borrow a neighbouring hold.
            base=phases[first]
            if any(p.surface!=base.surface or tuple(v.border for v in p.paint)!=tuple(v.border for v in base.paint)
                   for p in phases):continue
            selected=[]
            for offset in range(len(base.paint)):
                colors=[]
                for channel in ('fill','outline'):
                    votes={}
                    for peers,p in zip(groups,phases):
                        color=getattr(p.paint[offset],channel)
                        votes[color]=votes.get(color,0)+round(peers[0].duration,6)
                    colors.append(next(iter(votes)) if len(votes)==1 else _bounded_text_color(votes))
                if None in colors:break
                selected.append(SourceCaptionPaint(*colors,0,base.paint[offset].border))
            if len(selected)!=len(base.paint):continue
            # Removing the backing's fill changes interaction with a plane
            # painted between it and the foreground. Without an occlusion proof,
            # even a geometrically distant intervening object keeps the stack.
            if any(any(other.start_s<p.foreground.end_s and other.end_s>p.foreground.start_s
                       for other in unranked+order[ranks[p.backing.source_index]+1:ranks[p.foreground.source_index]])
                   for p in phases):continue
            for phase in phases:
                if phase.alpha==0:continue  # The existing opaque producer owns the hold.
                fg,bg=phase.foreground,phase.backing
                proved[frozenset((fg.source_index,bg.source_index))]=MatchedBackingFade(
                    fg,bg,OVERRIDE_RE.sub('',fg.text),tuple(selected),round(phase.alpha))
    return proved


def _render_matched_backing_fade(proof: MatchedBackingFade, paint_tags: set[str]) -> Event:
    """Emit one caption fading as a unit, retaining this source phase's layout."""
    fg=proof.foreground
    paints=[];palette={}
    for source in proof.paint:
        if source not in palette:
            body=render_simplified_caption(fg.state,'',source_paint=source,measurement=fg.measurement)
            state=effective_state(body,fg.defaults,fg.styles)
            state.update({'1a':proof.alpha,'3a':proof.alpha})
            palette[source]=state
        paints.append(palette[source])
    ranges=[(char,()) for char in proof.literal]
    text=_render_literal_paint(fg,ranges,paints,paint_tags)
    caption=replace_event(fg,text=text,effect='',source_index=min(fg.source_index,proof.backing.source_index))
    return _preserve_frame_pose_support(fg,caption)


def _partition_stacked_text_paint(context: StackedTextContext) -> list[tuple[tuple,list[Event]]]:
    """Partition only complete animated shadow families by their unchanged layout."""
    paint_groups = []
    for key, group in context.groups.items():
        # A differently scaled glow must not block an otherwise matching
        # shadow fill/contour stack. Partition only complete animated,
        # unclipped shadow families; keep every other geometry as its own
        # object for the existing later effect proofs.
        if (len(group) > 2 and all(e.source_index in (context.animated_sources or set()) and
                e.state.get('1a',0) >= 254 and e.state.get('3a',0) >= 254 and
                not inline_layout_key(e) and
                not any(k in e.state for k in ('clip','iclip')) for e in group)):
            layouts = {}
            for e in group:
                layouts.setdefault(text_layout_key(e),[]).append(e)
            paint_groups.extend((key,peers) for peers in layouts.values())
        else:
            paint_groups.append((key,group))
    return paint_groups


def _index_inline_stacked_text(context: StackedTextContext, group: list[Event]) -> tuple[dict,dict,list[Event]]:
    """Keep unsupported copies separate and index complete literal paint spans."""
    kept = []
    # Equal final states do not prove equal inline spacing/fonts.
    # Compare every literal span, coalescing paint-only boundaries.
    layouts = {}
    spans = {}
    for e in group:
        profile = static_text_paint_geometry(e,context.paint)
        if profile is None:
            kept.append(e)
        else:
            geometry,spans[e.source_index] = profile
            layouts.setdefault(geometry, []).append(e)
    return layouts,spans,kept


def _select_inline_stacked_text_foreground(context: StackedTextContext, key: tuple,
                                           peers: list[Event], spans: dict) -> tuple[Event,set[int]] | None:
    """Require matching spans and visible fill without automatic-row collisions."""
    ids = {e.source_index for e in peers}
    layers = {e.layer for e in peers}
    unpositioned = key[-2] is None
    # Same-layer unpositioned copies can occupy different rows.
    # Other captions can also displace either member of a stack.
    collision = unpositioned and (
        len(layers) != len(peers) or
        any(not layer.lstrip("-").isdigit() for layer in layers) or
        any(other.source_index not in ids and
            other.start_s < peers[0].end_s and other.end_s > peers[0].start_s
            for layer in layers for other in context.collision_peers[layer]))
    opaque = [e for e in peers if all(
        dict(signature.formatting).get("1a", 0) < 128 and
        "clip" not in dict(signature.formatting) and "iclip" not in dict(signature.formatting)
        for signature, _, _ in spans[e.source_index])]
    if len(peers) < 2 or collision or not opaque:
        return None
    chosen = max(opaque, key=lambda e: (
        int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
        e.source_index))
    if any(dict(signature.formatting).get('1a',0)>0 for signature,_,_ in spans[chosen.source_index]):
        ranges=_literal_paint_ranges([chosen]+[e for e in peers if e is not chosen])
        if ranges is None or any(0<states[0].get('1a',0)<255 and
                any(state.get('1a',0)<255 for state in states[1:]) for _,states in ranges):
            # A translucent foreground over another visible fill is composite
            # paint, not redundant lettering. Keep the layers until a backing
            # proof can reconstruct it; do not silently make it opaque.
            return None
    return chosen,ids


def _render_source_contour_paint(layout: Event, contour: tuple, paint_tags: set[str]) -> str:
    """Serialize the producer's complete palette without rediscovering ownership."""
    ranges,proofs=contour
    paints=[effective_state(render_simplified_caption(states[0],'',source_paint=proof,
                measurement=layout.measurement),layout.defaults,layout.styles)
            for (_,states),proof in zip(ranges,proofs)]
    return _render_literal_paint(layout,ranges,paints,paint_tags)


def _render_inline_stacked_text_caption(context: StackedTextContext, peers: list[Event],
                                        chosen: Event, ids: set[int], spans: dict
                                        ) -> tuple[list[Event],int]:
    """Preserve authored inline geometry while selecting paint and compacting its boundaries."""
    outlines = [dict(signature.formatting) for e in peers
                for signature, _, _ in spans[e.source_index]]
    # Reuse standard simplification paint choice while retaining all authored
    # geometry, including resets, wrapping and inline tracking.
    contour = _stacked_source_contour_paint(context,chosen,peers)
    if contour is None:
        text = static_text_paint_caption(chosen,outlines,context.paint,source_events=peers)
    else:
        text = _render_source_contour_paint(chosen,contour,context.paint)
    if text is None:
        return peers,0
    caption = replace_event(chosen, text=text, effect="",
                            source_index=min(ids))
    # Remove paint-only boundaries now so the existing frame
    # reducer can recognize the newly exposed complete caption.
    return compact_static_overrides([caption], 0),len(peers)-1


def _flatten_inline_stacked_text(context: StackedTextContext, key: tuple,
                                 group: list[Event]) -> tuple[list[Event],int]:
    """Reduce each compatible inline layout independently, retaining every refused group."""
    layouts,spans,kept = _index_inline_stacked_text(context,group)
    removed = 0
    for peers in layouts.values():
        selection = _select_inline_stacked_text_foreground(context,key,peers,spans)
        if selection is None:
            kept.extend(peers)
            continue
        chosen,ids = selection
        captions,count = _render_inline_stacked_text_caption(context,peers,chosen,ids,spans)
        kept.extend(captions)
        removed += count
    return kept,removed


def _prove_stacked_shadow_text(context: StackedTextContext, group: list[Event],
                               clipped: bool) -> tuple[bool,bool]:
    """Distinguish animated shadow paint from complete static shadow-offset proof."""
    # Some effects paint the letters entirely with the shadow channel.
    # A stack of animated, coincident shadow copies is still one text
    # object; normalize it before dedup discards the channel evidence.
    shadow_paint = (not clipped and len({text_layout_key(e) for e in group}) == 1 and
                   all(e.state.get("1a",0) >= 254 and e.state.get("3a",0) >= 254
                       for e in group) and
                   any(e.state.get("4a",0) < 254 and
                       any(abs(e.state.get(k,0)) > 0 for k in ("shad","xshad","yshad"))
                       for e in group))
    shadow_text = (shadow_paint and
                   all(e.source_index in (context.animated_sources or set()) and
                       e.state.get("1a",0) >= 254 and e.state.get("3a",0) >= 254
                       for e in group))
    # Static shadow-painted stacks are the same text object too. Prove
    # the original spans are static and their offsets coincide before
    # transferring the top visible shadow's paint and actual position.
    # Ordinary filled text, moving shadows and separate labels stay out.
    static_shadow_text = (shadow_paint and not shadow_text and
        all(static_object_key(dataclass_replace(
                (context.source_events or {}).get(e.source_index,e),effect=""),e.styles) is not None and
            unrotated_text_state(e.state) and
            e.state.get('borderstyle',1) == 1 and
            not any(k in e.state for k in ('org','clip','iclip')) and
            all(math.isfinite(e.state.get(k,0)) and e.state.get(k,0) > 0
                for k in ('fs','fscx','fscy')) for e in group) and
        len({(e.state.get('xshad',e.state.get('shad',0)),
              e.state.get('yshad',e.state.get('shad',0))) for e in group}) == 1 and
        all(math.isfinite(e.state.get(k,e.state.get('shad',0)))
            for e in group for k in ('xshad','yshad')))
    return shadow_text,static_shadow_text


def _prove_stacked_text_paint(context: StackedTextContext, group: list[Event]) -> StackedTextProof | None:
    """Admit a proved shadow stack, compatible visible fill, or opaque clipped copy."""
    clipped = any("clip" in e.state or "iclip" in e.state for e in group)
    shadow_text,static_shadow_text = _prove_stacked_shadow_text(context,group,clipped)
    solid_stack = (not clipped and len({text_layout_key(e) for e in group}) == 1 and
                   any(e.state.get("1a",255) < 128 for e in group))
    if (len(group) < 2 or not (shadow_text or static_shadow_text or solid_stack or
            clipped and any(e.state.get("1a", 255) == 0 for e in group))):
        return None
    return StackedTextProof(shadow_text,static_shadow_text,solid_stack)


def _select_stacked_text_foreground(group: list[Event], proof: StackedTextProof) -> Event:
    """Prefer a complete visible foreground using actual layer and source order."""
    # A complete, unclipped text copy is the best source for the font and
    # size. The output paint is uniform and opaque by design in standard simplification.
    # Dominantly visible foreground paint may be slightly translucent.
    # Prefer its actual compositing order over an opaque backing fill.
    candidates = ([e for e in group if e.state.get('4a',0) < 254] if proof.static_shadow_text or proof.shadow_text else
                  [e for e in group if e.state.get("1a",255) < 128] if proof.solid_stack else
                  [e for e in group if e.state.get("1a",255) == 0])
    chosen = max(candidates,key=lambda e:(
        "clip" not in e.state and "iclip" not in e.state,
        int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
        e.source_index))
    return chosen


def _settled_stacked_contour_source(source: Event) -> tuple[Event,tuple] | None:
    """Borrow static paint, or settle a shared opacity-only header animation.

    This is paint evidence, not a new timing decision. The existing freezer
    owns visibility. The caller must match the complete opacity progression
    between planes before using their opaque source colors.
    """
    tokens=event_override_tokens(source)
    transforms=[value for tag,value in tokens if tag=='t']
    if not transforms:
        return source,()
    prefix=re.match(r'(?:\{[^}]*\})*',source.text).end()
    if any(tag in {'t','r','alpha','1a','3a'} for tag,value in event_override_tokens(
            dataclass_replace(source,text=source.text[prefix:]))):
        # Resets or later opacity overrides can give separate spans different
        # progressions even when their initial alpha is identical.
        return None
    def without(tags):
        return OVERRIDE_RE.sub(lambda m:'{'+''.join('\\'+tag+value
            for tag,value in tokenize_override(m[1]) if tag not in tags)+'}',source.text)
    base=replace_event(source,text=without({'t'}))
    ranges=_literal_paint_ranges([base])
    if ranges is None:
        return None
    alphas={(state.get('1a',0),state.get('3a',0)) for _,states in ranges for state in states}
    if len(alphas)!=1 or next(iter(alphas))[0]!=next(iter(alphas))[1]:
        return None
    alpha=next(iter(alphas))[0];profile=[alpha];state={'1a':alpha,'3a':alpha}
    continuation=OverrideContinuation()
    for value in transforms:
        parsed=parse_effect_transform(value,source.duration,{'alpha','1a','3a'},allow_instant=True)
        if parsed is None:
            return None
        begin,end,changes=parsed
        for tag,argument in changes:
            continuation=apply_override(state,tag,argument,source.styles,source.defaults,continuation)
        if state.get('1a')!=state.get('3a'):
            return None
        args=[float(v.strip()) for v in value[1:-1].partition('\\')[0].rstrip(', ').split(',') if v.strip()]
        accel=args[-1] if len(args) in (1,3) else 1.
        profile.append((begin,end,accel,state['1a']))
    if min([alpha]+[item[-1] for item in profile[1:]])!=0:
        return None
    # Contour proof below rejects shadows altogether; no hidden shadow can
    # become evidence by stripping its global alpha here.
    settled=replace_event(source,text=without({'t','alpha','1a','3a'}))
    progression=tuple(profile) if any(item[-1]!=alpha for item in profile[1:]) else ()
    return settled,progression


def _source_palette_boundaries(source: Event) -> set[float] | None:
    """Borrow source timing for discrete paint; continuous color needs its own proof."""
    boundaries=set()
    for tag,value in event_override_tokens(source):
        if tag!='t':
            continue
        parsed=parse_effect_transform(value,source.duration,
            {'c','1c','2c','3c','4c','alpha','1a','2a','3a','4a'},allow_instant=True)
        if parsed is None:
            return None
        begin,end,changes=parsed
        if any(k in {'c','1c','2c','3c','4c'} for k,v in changes):
            if begin!=end:
                return None
            boundaries.add(source.start_s+begin/1000)
    return boundaries


def _representative_source_palette_time(sources: Iterable[Event], start: float, end: float) -> float:
    """Choose one held palette interval, never independent channel winners.

    One source-time sample supplies every corresponding fill and contour span.
    Geometry and karaoke-completion admission remain with the calling producer.
    Original events and their full timelines remain borrowed, unmodified evidence.
    """
    sources=list(sources)
    points={start,end}
    for source in sources:
        points.update(t for t in (_source_palette_boundaries(source) or ()) if start<t<end)
    points=sorted(points)
    if len(points)==2:
        return (start+end)/2
    votes={}
    for a,b in zip(points,points[1:]):
        at=(a+b)/2;palette=[]
        for source in sources:
            sampled=_source_palette_at(source,at)
            ranges=_literal_paint_ranges([sampled[0]]) if sampled else None
            spans=[]
            for fragment,states in ranges or []:
                color=tuple(states[0].get(k) for k in ('1c','3c','1a','3a'))
                if spans and spans[-1][0]==color:
                    spans[-1]=(color,spans[-1][1]+fragment)
                else:
                    spans.append((color,fragment))
            palette.append(tuple(spans))
        key=tuple(palette)
        duration,representative=votes.get(key,(0.,at))
        votes[key]=(duration+b-a,representative)
    # Repeated equal palettes and no-op tag boundaries add exposure rather
    # than competing as unrelated phases. The chosen time still occurred.
    return max(votes.values(),key=lambda item:(round(item[0],6),-item[1]))[1]


def _source_palette_at(source: Event, at: float) -> tuple[Event,tuple] | None:
    """Resolve source color steps at a common time, then prove coupled opacity.

    Replay each block in place so resets and intentional span gradients retain
    their meaning. Only color is sampled here; the existing opacity proof still
    owns fade admission. No sampled successor replaces the original source map.
    """
    if _faded_cue_is_scrolling(source) or _source_palette_boundaries(source) is None:
        return None
    source=dataclass_replace(source,effect='')
    def block(match):
        result=[]
        for tag,value in tokenize_override(match[1]):
            if tag!='t':
                result.append('\\'+tag+value);continue
            begin,end,changes=parse_effect_transform(value,source.duration,
                {'c','1c','2c','3c','4c','alpha','1a','2a','3a','4a'},allow_instant=True)
            colors=[(k,v) for k,v in changes if k in {'c','1c','2c','3c','4c'}]
            opacity=[(k,v) for k,v in changes if k not in {'c','1c','2c','3c','4c'}]
            if source.start_s+begin/1000<=at:
                result.extend('\\'+k+v for k,v in colors)
            if opacity:
                prefix=value[1:-1].partition('\\')[0]
                result.append('\\t('+prefix+''.join('\\'+k+v for k,v in opacity)+')')
        return '{'+''.join(result)+'}'
    sampled=replace_event(source,text=OVERRIDE_RE.sub(block,source.text))
    return _settled_stacked_contour_source(sampled)


def _stacked_source_contour_paint(context: StackedTextContext, chosen: Event,
                                  group: list[Event], *, at: float | None = None
                                  ) -> tuple[list[tuple],list[SourceCaptionPaint]] | None:
    """Prove the immediate opaque stroke beneath an opaque borderless foreground.

    Coincident lower copies can have several contour colors without being
    contradictory: the top sharp stroke owns the retained inner band. Wider
    contours below it are decoration. Use original spans before freezing erased
    blur/animation, and keep ordinary fallback when that ownership is uncertain.
    Layout admission and removal remain the stack producer's responsibility.
    """
    if any(not e.layer.lstrip('-').isdigit() for e in group):
        return None
    ordered = sorted(group,key=lambda e:(int(e.layer),e.source_index),reverse=True)
    if ordered[0] is not chosen:
        return None
    if at is None:
        sources=[(context.source_events or {}).get(e.source_index,e) for e in group]
        at=_representative_source_palette_time(sources,max(e.start_s for e in group),min(e.end_s for e in group))
    opacity=[]
    def original(event):
        source=event if context.source_events is None else context.source_events.get(event.source_index)
        if source is None:
            return None
        if ((source.start,source.end)!=(event.start,event.end) or
                _faded_cue_is_scrolling(source)):
            return None
        source=dataclass_replace(source,effect='')  # Other Effect annotations are inert.
        settled=_source_palette_at(source,at)
        if settled is None:
            return None
        source,progression=settled
        if opacity and progression!=opacity[0]:
            return None
        opacity.append(progression)
        profile=static_text_paint_geometry(source,context.paint)
        current=static_text_paint_geometry(event,context.paint)
        if profile is None or current is None or profile[0]!=current[0]:
            return None
        return source
    foreground=original(chosen)
    if foreground is None:
        return None
    # A borderless lower fill cannot reach beyond the selected glyph. Inspect
    # source paint even for skipped planes: freezing can erase their blur.
    for backing in ordered[1:]:
        source=original(backing)
        if source is None:
            return None
        spans=_literal_paint_ranges([source])
        if spans is None:
            return None
        if any(max(state.get(k,state.get('bord',0)) for k in ('xbord','ybord'))>0 and state.get('3a',0)<255 or
               state.get('blur',0) or state.get('be',0) or
               state.get('4a',0)<255 and any(state.get(k,state.get('shad',0)) for k in ('xshad','yshad'))
               for _,states in spans for state in states):
            break
    else:
        return None
    ranges=_literal_paint_ranges([chosen,backing,foreground,source])
    if ranges is None:
        return None
    proofs=[]
    for fragment,states in ranges:
        selected,_,front,back=states
        if (selected.get('1a',0)!=0 or front.get('1a',0)!=0 or
                any(front.get(k,front.get('bord',0))!=0 for k in ('xbord','ybord')) or
                back.get('3a',0)!=0 or
                max(back.get(k,back.get('bord',0)) for k in ('xbord','ybord'))<=0 or
                any(any(k in state for k in ('clip','iclip')) or
                    state.get('blur',0) or state.get('be',0) or
                    any(state.get(k,state.get('shad',0)) for k in ('xshad','yshad'))
                    for state in (front,back))):
            return None
        proof=_source_caption_paint({**selected,'1c':front.get('1c','FFFFFF')},[back])
        if proof is None:
            return None
        proofs.append(proof)
    return ranges,proofs


def _animated_stacked_shadow_paint(chosen: Event, group: list[Event], state: dict
                                   ) -> tuple[dict,list[dict]]:
    """Transfer shadow fill and the wider visible contour below it at the frozen anchor."""
    # Animated shadow-painted letters still have real foreground
    # paint. Keep the established frozen glyph anchor while removing
    # shadow jitter; use the top visible contour below the fill rather
    # than conflicting lower glow colours. Effects become opaque.
    state = {**state,'1c':state.get('4c','FFFFFF'),'1a':0}
    fill_order = (int(chosen.layer), chosen.source_index)
    fill_border = max(chosen.state.get(k,chosen.state.get('bord',0))
                      for k in ('xbord','ybord'))
    # The selected fill may itself have a thin same-colour stroke.
    # That stroke is not its surrounding contour: use a wider visible
    # shadow-painted layer below the fill, in actual paint order.
    contours = [e for e in group if e.state.get('4a',0) < 254 and
                (int(e.layer),e.source_index) < fill_order and
                max(e.state.get(k,e.state.get('bord',0))
                    for k in ('xbord','ybord')) > max(0,fill_border)]
    contour = max(contours,key=lambda e:(
        int(e.layer) if e.layer.lstrip('-').isdigit() else 0,e.source_index)) if contours else None
    outlines = ([{**contour.state,'3c':contour.state.get('4c','000000'),'3a':0}]
                if contour is not None else [])
    return state,outlines


def _static_stacked_shadow_paint(key: tuple, group: list[Event], state: dict
                                 ) -> tuple[dict,list[dict]]:
    """Transfer static shadow paint and its proved common position offset."""
    dx = state.get('xshad',state.get('shad',0))
    dy = state.get('yshad',state.get('shad',0))
    state = {**state,'pos':(key[-2][0]+dx,key[-2][1]+dy),
             '1c':state.get('4c','FFFFFF'),'1a':state.get('4a',0)}
    outlines = [{**e.state,'3c':e.state.get('4c','000000'),
                 '3a':e.state.get('4a',0)} for e in group]
    return state,outlines


def _static_outline_ink_bounds(caption: Event, metric: FontMetrics) -> tuple | None:
    """Bound simple exact-font ink, including tracking, without a RAQM-only proof.

    Horizontal clearance uses the existing conservative caption measurement.
    Vertical control-point bounds use raw contours and ASS Windows line metrics;
    unlike a whole line-box estimate, they do not count blank ascender space.
    Contextual shaping, multiline text and synthetic italic remain unknown.
    Synthetic bold receives the caption measurement's existing font clearance.
    """
    state = caption.state
    literal = OVERRIDE_RE.sub('',caption.text)
    if (any(tag in literal for tag in (r'\N',r'\n',r'\h')) or
            any(state.get(k,0) for k in ('frz','frx','fry','fax','fay','org'))):
        return None
    face = metric.matching_face(str(state.get('fn','')),state.get('b',0),bool(state.get('i',0)))
    if face is None:
        return None
    try:
        box = caption_bounds(caption,metric)
        outline = metric.cubic_outline(face,literal)
        if box is None or outline is None:
            return None
        with metric.open_face(face) as font:
            flags = font['head'].macStyle
            selection = font['OS/2'].fsSelection
            axes = dict(face.coordinates)
            if (bool(state.get('i',0)) and not
                    (flags & 2 or selection & 1 or axes.get('ital',0) or axes.get('slnt',0))):
                return None
            synthetic_bold = (bool(state.get('b',0)) and not
                              (flags & 1 or selection & 32 or axes.get('wght',0) >= 700))
            ascent = font['OS/2'].usWinAscent
            height = ascent+font['OS/2'].usWinDescent
        if height <= 0:
            return None
        coordinates = [v for v in outline[0] if not isinstance(v,str)]
        line_height = state.get('fs',20)*state.get('fscy',100)/100
        baseline = get_pos(caption.text)[1]-(1-(int(state.get('an',2))-1)//3/2)*line_height
        baseline += ascent/height*line_height
        top,bottom = (baseline+y/height*line_height
                      for y in (min(coordinates[1::2]),max(coordinates[1::2])))
        clearance = .08*line_height if synthetic_bold else 0
        return box[0],top-clearance,box[2],bottom+clearance
    except (OSError,ValueError,RuntimeError,KeyError):
        return None


def _collect_outline_strip_evidence(chosen: Event, group: list[Event],
                                    context: StackedTextContext) -> OutlineStripEvidence | None:
    """Prove common layout and complete base-stroke coverage for an outline family.

    This geometry proof is shared by static paint and ordered karaoke paint.
    Transform admission belongs to those consumers; original sources stay borrowed.
    """
    metric,sources = context.font_metrics,context.source_events
    if (metric is None or not metric.available or sources is None or
            chosen.state.get('1a',0) != 0 or chosen.state.get('borderstyle',1) != 1 or
            any(k in chosen.state for k in ('clip','iclip')) or
            max(chosen.state.get(k,chosen.state.get('bord',0)) for k in ('xbord','ybord')) > 0):
        return None
    strips = [e for e in group if 'clip' in e.state or 'iclip' in e.state]
    if len(strips) < 2:
        return None
    layout,literal = text_layout_key(chosen),OVERRIDE_RE.sub('',chosen.text)
    candidates = []
    animated = False
    source_tokens = {}
    for event in strips:
        source = sources.get(event.source_index)
        if (source is None or not event.layer.lstrip('-').isdigit() or
                not chosen.layer.lstrip('-').isdigit() or
                (int(event.layer),event.source_index) >= (int(chosen.layer),chosen.source_index)):
            return None
        tokens = tuple(event_override_tokens(source))
        source_tokens[id(source)] = source,tokens
        if any(name in {'move','fade','k','kf','ko','kt'} for name,value in tokens):
            return None
        animated = animated or any(name == 't' for name,value in tokens)
        state = source.state if source.state else evaluate_effective_state(
            source.text,source.defaults,source.styles,tokens=tokens).formatting
        original = dataclass_replace(source,state=state)
        rect = rectangle_clip(original)
        width = tuple(state.get(k,state.get('bord',0)) for k in ('xbord','ybord'))
        color = str(state.get('3c','')).upper()
        if (rect is None or not all(math.isfinite(v) for v in (*rect,*width)) or
                min(width) <= 0 or state.get('borderstyle',1) != 1 or
                not 0 <= state.get('3a',0) < 128 or state.get('1a',0) < 254 or
                text_layout_key(original) != layout or
                get_pos(source.text) != get_pos(chosen.text) or
                OVERRIDE_RE.sub('',source.text) != literal or
                not re.fullmatch(r'[0-9A-F]{6}',color)):
            return None
        candidates.append((source,rect,state))
    if len({(state.get('3a',0),tuple(state.get(k,state.get('bord',0))
                                  for k in ('xbord','ybord')))
            for source,rect,state in candidates}) != 1:
        return None
    candidates.sort(key=lambda item:item[1])
    union = merge_tiled_clips([rect for source,rect,state in candidates],chosen.unit)
    ink = _static_outline_ink_bounds(chosen,metric)
    if union is None or ink is None:
        return None
    state = candidates[0][2]
    bx,by = (state.get(k,state.get('bord',0)) for k in ('xbord','ybord'))
    bounds = (ink[0]-bx,ink[1]-by,ink[2]+bx,ink[3]+by)
    if not (union[0] <= bounds[0] and union[1] <= bounds[1] and
            union[2] >= bounds[2] and union[3] >= bounds[3]):
        return None
    weights = tuple(max(0,min(rect[2],bounds[2])-max(rect[0],bounds[0]))*max(
                    0,min(rect[3],bounds[3])-max(rect[1],bounds[1]))
                    for source,rect,state in candidates)
    if sum(weights) <= 0:
        return None
    return OutlineStripEvidence(tuple(candidates),weights,animated,source_tokens)


def _average_outline_strip_color(evidence: OutlineStripEvidence, states: list[dict]) -> str:
    """Average admitted strip paint in linear light using its already proved ink weights."""
    total,channels = sum(evidence.weights),[0.0,0.0,0.0]
    for area,state in zip(evidence.weights,states):
        color = str(state['3c']).upper()
        for i in range(3):
            value = int(color[2*i:2*i+2],16)/255
            channels[i] += area*(value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4)
    def encode(value):
        value /= total
        return round(255*(12.92*value if value <= .0031308 else 1.055*value**(1/2.4)-.055))
    return ''.join(f'{encode(value):02X}' for value in channels)


def _representative_static_strip_outline(chosen: Event,
                                        evidence: OutlineStripEvidence | None) -> dict | None:
    """Use the existing coverage proof; original transforms disqualify static paint."""
    if evidence is None or evidence.animated:
        return None
    color = _average_outline_strip_color(evidence,[state for source,rect,state in evidence.strips])
    return {**chosen.state,'3c':color,'3a':0,'bord':2,'xbord':2,'ybord':2}


def _profile_outline_strip_transition(source: Event, state: dict, *,
                                      tokens: tuple[tuple[str,str],...] | None = None) -> tuple | None:
    """Admit one outline-color transition and independent restored stroke/blur pulses.

    libass renders reversed/equal endpoints as a step after the stated start.
    Normalize only this paint evidence; general effect proofs remain strict.
    """
    if tokens is None:
        tokens = tuple(event_override_tokens(source))
    first = next((i for i,(name,value) in enumerate(tokens) if name == 't'),None)
    if (first is None or inline_layout_key(source) or
            source.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'} or
            any(name != 't' for name,value in tokens[first:])):
        return None
    final,continuation = state.copy(),source.continuation
    transition = None
    for name,value in tokens[first:]:
        prefix,sep,tail = value[1:-1].partition('\\')
        try:
            args = [float(v.strip()) for v in prefix.rstrip(', ').split(',') if v.strip()]
        except ValueError:
            return None
        # Normalize the renderer's step timing, then use the existing strict
        # transform validator. Geometry pulses may finish beyond the cue;
        # the color transition itself must still occur within its lifetime.
        if len(args) >= 2 and not (args[0] >= 0 and args[1] >= 0):
            return None
        normalized = value
        if len(args) in (2,3) and args[1] < args[0]:
            args[1] = args[0]
            normalized = '('+','.join(str(v) for v in args)+',\\'+tail+')'
        changes = tokenize_override('\\'+tail)
        has_color = any(tag == '3c' for tag,arg in changes)
        parsed = parse_effect_transform(normalized,source.duration,
            {'3c','bord','xbord','ybord','blur','be'},allow_instant=True,
            allow_after_end=not has_color,parsed_changes=changes)
        if parsed is None:
            return None
        begin,end,changes = parsed
        if begin >= source.duration*1000:
            return None
        colors = [(tag,arg) for tag,arg in changes if tag == '3c']
        if colors:
            if transition is not None or len(colors) != 1:
                return None
            transition = (source.start_s+begin/1000,source.start_s+end/1000)
        for tag,arg in changes:
            continuation = apply_override(final,tag,arg,source.styles,source.defaults,continuation)
        if any(not math.isfinite(final.get(k,final.get('bord',0))) or
               final.get(k,final.get('bord',0)) < 0 for k in ('xbord','ybord','blur','be')):
            return None
    if (transition is None or final.get('3c') == state.get('3c') or
            not re.fullmatch(r'[0-9A-Fa-f]{6}',str(final.get('3c',''))) or
            any(final.get(k,final.get('bord',0)) != state.get(k,state.get('bord',0))
                for k in ('xbord','ybord'))):
        return None
    return *transition,final


def _profile_outline_strip_sweep(chosen: Event, evidence: OutlineStripEvidence,
                                 context: StackedTextContext) -> KaraokeCompletionProfile | None:
    """Build one syllable's strip-palette transition for the existing row-sweep proof."""
    foreground = (context.source_events or {}).get(chosen.source_index)
    if (foreground is None or
            foreground.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'} or
            any(name in {'t','move','fade','k','kf','ko','kt'}
                                  for name,value in evidence.tokens_for(foreground))):
        return None
    transitions = []
    fades = set()
    for source,rect,state in evidence.strips:
        if abs(source.start_s-chosen.start_s) > .001 or abs(source.end_s-chosen.end_s) > .001:
            return None
        tokens = evidence.tokens_for(source)
        transition = _profile_outline_strip_transition(source,state,tokens=tokens)
        if transition is None:
            return None
        transitions.append(transition)
        fades.add(tuple(value for name,value in tokens if name == 'fad'))
    if len({(begin,end) for begin,end,final in transitions}) != 1 or len(fades) != 1:
        return None
    begin,end = transitions[0][:2]
    y = get_pos(chosen.text)[1]
    def palette(states):
        return (chosen.state.get('1c'),tuple((rect[0],rect[1]-y,rect[2],rect[3]-y,
                    str(state['3c']).upper(),state.get('3a',0),
                    state.get('xbord',state.get('bord',0)),state.get('ybord',state.get('bord',0)))
                    for (source,rect,initial),state in zip(evidence.strips,states)))
    initial = [state for source,rect,state in evidence.strips]
    final = [state for begin,end,state in transitions]
    color = _average_outline_strip_color(evidence,final)
    candidate = {**chosen.state,'3c':color,'3a':0,'bord':2,'xbord':2,'ybord':2}
    # Reuse the ordinary renderer's contrast policy rather than duplicating it.
    text = render_simplified_caption(chosen.state,OVERRIDE_RE.sub('',chosen.text),
                                     outline_states=[candidate],measurement=chosen.measurement,
                                     source_paint=SourceCaptionPaint(chosen.state.get("1c","FFFFFF"),color,0))
    color = effective_state(text,chosen.defaults,chosen.styles)['3c']
    visible_end = chosen.end_s
    for name,value in evidence.tokens_for(evidence.strips[0][0]):
        if name == 'fad':
            match = re.fullmatch(r'\(\s*('+NUMBER+r')\s*,\s*('+NUMBER+r')\s*\)',value)
            if match is None:
                return None
            visible_end -= max(0,float(match[2]))/1000
    return KaraokeCompletionProfile(palette(initial),palette(final),begin,end,
                                    {'3c':color},visible_end-end >= .02)


def _render_stacked_text_caption(key: tuple, group: list[Event], proof: StackedTextProof,
                                 context: StackedTextContext
                                 ) -> tuple[list[Event],int,KaraokeCompletionProfile | None]:
    """Build the caption and explicitly return any pass-local outline sweep evidence."""
    chosen = _select_stacked_text_foreground(group,proof)
    state = chosen.state
    outlines = [e.state for e in group]
    profile = None
    source_paint = None
    if proof.shadow_text:
        state,outlines = _animated_stacked_shadow_paint(chosen,group,state)
    elif proof.static_shadow_text:
        state,outlines = _static_stacked_shadow_paint(key,group,state)
    else:
        evidence = _collect_outline_strip_evidence(chosen,group,context)
        if evidence is not None and evidence.animated:
            profile = _profile_outline_strip_sweep(chosen,evidence,context)
        else:
            representative = _representative_static_strip_outline(chosen,evidence)
            if representative is not None:
                outlines.append(representative)
                source_paint = _source_caption_paint(state,[representative])
        if source_paint is None and evidence is None:
            # The selected foreground owns its own complete glyph stroke.
            # Decorative copies can have other contours; they do not make the
            # original foreground's authored stroke ambiguous. An earlier
            # fallback must not replace that stroke before row/phase joining.
            original = (context.source_events or {}).get(chosen.source_index)
            if original is not None and OVERRIDE_RE.sub('',original.text) == OVERRIDE_RE.sub('',chosen.text):
                authored = event_evaluation(original).formatting
                if (max(authored.get(k,authored.get('bord',0)) for k in ('xbord','ybord')) > 0 and
                        authored.get('3a',0) < 255):
                    source_paint = _source_caption_paint(state,[authored])
            if source_paint is None:
                contour = _stacked_source_contour_paint(context,chosen,group)
                if contour is not None:
                    source_paint = contour[1][0]
            if source_paint is None:
                source_paint = _source_caption_paint(state,outlines)
    glow = context.glow_paint.get(chosen.source_index)
    if glow is not None:
        state = {**state,'1c':glow.fill,'fscx':glow.scale[0],'fscy':glow.scale[1]}
        context.owned_glow_fragments.update(glow.fragments)
    text = render_simplified_caption(state,OVERRIDE_RE.sub('',chosen.text),
        outline_states=outlines,measurement=chosen.measurement,
        source_paint=SourceCaptionPaint(glow.fill,glow.outline,glow.outline_alpha) if glow is not None else source_paint)
    caption = replace_event(chosen, text=text, layer=chosen.layer if proof.shadow_text or glow is not None else "0", effect="",
                        source_index=min(e.source_index for e in group),
                        lyric=chosen.lyric or proof.static_shadow_text)
    caption = _preserve_frame_pose_support(chosen,caption)
    if glow is not None:
        context.glow_captions[chosen.source_index] = caption
        context.glow_collapsed[chosen.source_index] = [e.source_index for e in group
                                                     if e.source_index != chosen.source_index]
    return [caption],len(group)-1,profile


def _flatten_stacked_text_group(context: StackedTextContext, key: tuple,
                                group: list[Event]) -> tuple[list[Event],int,KaraokeCompletionProfile | None]:
    """Route literal-span layouts and proved uniform stacks through their existing rules."""
    if len(group) < 2:
        return group,0,None
    contained=context.contained_paint.get(frozenset(e.source_index for e in group))
    if contained is not None:
        chosen,held,contour=contained
        caption=replace_event(chosen,text=_render_source_contour_paint(chosen,contour,context.paint),
            start=held.start,end=held.end,start_s=held.start_s,end_s=held.end_s,
            source_index=min(e.source_index for e in group),effect='')
        return compact_static_overrides([caption],0),len(group)-1,None
    fade=context.matched_backing_fades.get(frozenset(e.source_index for e in group))
    if fade is not None:
        return compact_static_overrides([_render_matched_backing_fade(fade,context.paint)],0),1,None
    if key[-2] is None or any(inline_layout_key(e) for e in group):
        captions,count = _flatten_inline_stacked_text(context,key,group)
        return captions,count,None
    proof = _prove_stacked_text_paint(context,group)
    if proof is None:
        return group,0,None
    return _render_stacked_text_caption(key,group,proof,context)


def _glow_boundary_phase(source: Event, held: Event, entering: bool) -> bool:
    """Prove one stationary opacity leg joins the held source's primary paint."""
    if (_glow_source_geometry(source) != _glow_source_geometry(held) or
            _glow_source_geometry(source) is None or
            any(source.state.get(k) != held.state.get(k) for k in ('1c','3c','4c'))):
        return False
    values = [value for tag,value in event_override_tokens(source) if tag == 't']
    if len(values) != 1:
        return False
    transform = parse_effect_transform(values[0],source.duration,
        {'alpha','1a','2a','3a','4a','c','1c','blur','be'},allow_instant=True)
    if (transform is None or transform[0] > 50 or
            abs(transform[1]-source.duration*1000) > 50):
        return False
    final,continuation = source.state.copy(),source.continuation
    for tag,value in transform[2]:
        continuation = apply_override(final,tag,value,source.styles,source.defaults,continuation)
    if any(final.get(k) != source.state.get(k) for k in ('1c','3c','4c')):
        return False
    before,after = source.state.get('1a',0),final.get('1a',0)
    return ((before >= 254 and after == held.state.get('1a',0)) if entering else
            (before == held.state.get('1a',0) and after >= 254))


def _handoff_glow_boundaries(context: StackedTextContext, events: list[Event],
                              visible_map: dict[int,str]) -> tuple[list[Event],int,int,list[TextRow]]:
    """Give complete boundary families settled paint and explicit phase ownership.

    Source opacity animation proves the boundary; temporal proximity alone does
    not. Retained offset backing paint follows its own held formatting. The
    existing phase merger owns joining, while returned rows preserve the core
    for reconstruction/overlap trimming. Sources and visibility remain borrowed.
    """
    if not context.glow_captions or context.source_events is None:
        return events,0,0,[]
    sources = context.source_events
    current = {e.source_index:e for e in events}
    families = {(e.style,e.name) for e in context.glow_captions.values()}
    buckets = {}
    for source in sources.values():
        if source.kind != 'Dialogue' or (source.style,source.name) not in families:
            continue
        word = OVERRIDE_RE.sub('',source.text)
        buckets.setdefault((source.style,source.name,word),[]).append(source)
    resolved = {}
    def resolve(e):
        if e.source_index not in resolved:
            evaluation = evaluate_effective_state(e.text,e.defaults,e.styles)
            resolved[e.source_index] = dataclass_replace(e,state=evaluation.formatting,
                continuation=evaluation.continuation)
        return resolved[e.source_index]
    rows = {}
    for index,caption in context.glow_captions.items():
        held = resolve(sources[index])
        key = (held.style,held.name,held.start,held.end,_glow_source_geometry(held),get_pos(held.text)[1])
        rows.setdefault(key,[]).append((held,caption))
    replacements,phase_groups,proof_rows,removed = {},{},[],set()
    backing_ids = {}
    for row in rows.values():
        proposals = {}
        for entering in (True,False):
            matched = []
            for held,caption in row:
                word = OVERRIDE_RE.sub('',held.text)
                peers = buckets[held.style,held.name,word]
                candidates = [resolve(e) for e in peers if e.layer == held.layer and
                    get_pos(e.text) == get_pos(held.text) and
                    abs((e.end_s-held.start_s) if entering else (e.start_s-held.end_s)) <= .011 and
                    e.source_index in current and
                    OVERRIDE_RE.sub('',current[e.source_index].text) == word and
                    _glow_boundary_phase(resolve(e),held,entering)]
                if len(candidates) != 1:
                    matched = [];break
                matched.append((held,caption,candidates[0]))
            if not matched or len({(p.start,p.end) for held,caption,p in matched}) != 1:
                continue
            for held,caption,phase in matched:
                proposals.setdefault(held.source_index,[]).append(phase)
        if not proposals:
            continue
        for held,caption in row:
            phases = proposals[held.source_index]
            word = OVERRIDE_RE.sub('',held.text)
            # Each component is assigned its own family: a repeated word in a
            # different cue must never inherit this cue's lifetime or core.
            components = [(held,caption)]
            # The caption already replaces these exact coextensive paint
            # copies. Their matching boundary legs belong to that same stack,
            # rather than becoming a second outlined caption after freezing.
            for index in context.glow_collapsed.get(held.source_index,[]):
                component = resolve(sources[index])
                for boundary in phases:
                    peers = [resolve(e) for e in buckets[held.style,held.name,word]
                        if e.start == boundary.start and e.end == boundary.end and
                           e.layer == component.layer and get_pos(e.text) == get_pos(component.text) and
                           e.source_index in current and
                           OVERRIDE_RE.sub('',current[e.source_index].text) == word and
                           _glow_boundary_phase(resolve(e),component,boundary.end_s <= held.start_s+.011)]
                    if len(peers) == 1:
                        removed.add(peers[0].source_index)

            for e in buckets[held.style,held.name,word]:
                if (e.source_index == held.source_index or e.start != held.start or e.end != held.end or
                        e.source_index not in current or not e.layer.lstrip('-').isdigit() or
                        int(e.layer) >= int(held.layer) or get_pos(e.text) is None or
                        math.dist(get_pos(e.text),get_pos(held.text)) > .1*text_height(held)):
                    continue
                component = resolve(e)
                rendered = current[e.source_index]
                if (rendered.layer == e.layer and OVERRIDE_RE.sub('',rendered.text) == word and
                        _glow_source_geometry(component) == _glow_source_geometry(held)):
                    components.append((component,rendered))
            for component,rendered in components:
                members = []
                for boundary in phases:
                    peers = [resolve(e) for e in buckets[held.style,held.name,word]
                        if e.start == boundary.start and e.end == boundary.end and
                           e.layer == component.layer and get_pos(e.text) == get_pos(component.text) and
                           e.source_index in current and
                           OVERRIDE_RE.sub('',current[e.source_index].text) == word and
                           _glow_boundary_phase(resolve(e),component,boundary.end_s <= held.start_s+.011)]
                    if len(peers) == 1:
                        members.append(peers[0])
                if not members:
                    continue
                phase_groups[rendered.source_index] = component.source_index
                for phase in members:
                    phase_groups[phase.source_index] = component.source_index
                    replacements[phase.source_index] = replace_event(current[phase.source_index],text=rendered.text)
                first = min([rendered.source_index]+[p.source_index for p in members])
                if component is not held:
                    backing_ids.setdefault(held.source_index,[]).append(first)
                if component is held:
                    proof_rows.append((first,rendered,held.start_s,held.end_s,held.source_index))
    output = [replacements.get(e.source_index,e) for e in events if e.source_index not in removed]
    output,merged = coalesce_lyric_phases(output,visible_map,phase_groups=phase_groups)
    actual = {e.source_index:e for e in output}
    rows = [TextRow(actual[index],[(held,OVERRIDE_RE.sub('',held.text),get_pos(held.text))],
                    phase_core=(start,end),owned_backing=tuple(actual[i] for i in backing_ids.get(owner,[])
                                                           if i in actual))
            for index,held,start,end,owner in proof_rows if index in actual]
    return output,len(removed),merged,rows


def flatten_stacked_text_copies(events: list[Event],
                                   visible_map: dict[int,str],
                                   animated_sources: set[int] | None = None, *,
                                   max_piece_duration: float = .16,
                                   source_events: dict[int,Event] | None = None,
                                   font_metrics: FontMetrics | None = None,
                                   collect_rows: bool = False) -> tuple[list[Event], int] | StackedTextResult:
    """Replace stacked static copies of the same text with one.

    This is for standard simplification: color gradients, clipped stripes, shadows and
    alternate paint layers are intentionally replaced by a readable caption.
    Complete static outline strips may supply representative paint through exact
    font coverage. No font/style name, color, language or strip-count is hardcoded.
    Complete ordered strip-outline sweeps may retain their destination paint
    through the existing karaoke normalizer, using separately owned local proof.
    """
    context,removed = _prepare_stacked_text_copies(
        events,visible_map,animated_sources,max_piece_duration,source_events,font_metrics)
    outline_profiles = {}
    for key,group in _partition_stacked_text_paint(context):
        captions,count,profile = _flatten_stacked_text_group(context,key,group)
        context.kept.extend(captions)
        removed += count
        if profile is not None:
            outline_profiles[captions[0].source_index] = profile
    output = sorted(context.kept,key=lambda e:e.source_index)
    if context.owned_glow_fragments:
        retained = [e for e in output if e.source_index not in context.owned_glow_fragments]
        removed += len(output)-len(retained)
        output = retained
    if outline_profiles:
        output = normalize_karaoke_completion_paint(
            output,visible_map,source_events,outline_profiles=outline_profiles)
    output,boundaries_removed,phases,rows = _handoff_glow_boundaries(context,output,visible_map)
    removed += boundaries_removed
    return StackedTextResult(output,removed,phases,rows) if collect_rows else (output,removed+phases)


def remove_fragmented_font_decorations(events: list[Event], visible_map: dict[int,str],
                                       metric: FontMetrics | None,
                                       source_events: dict[int,Event]) -> tuple[list[Event],int]:
    """Drop dense scattered stamps whose exact glyphs consist of tiny islands.

    Font names and letter payloads are not evidence. Require a coextensive
    caption in another exact font, a two-dimensional stamp cluster, and highly
    fragmented outlines for every removed glyph. Simple symbols, ordinary
    letters, rows, ambiguous caption families and unsupported fonts survive.
    """
    if metric is None or not metric.available:
        return events,0
    groups, captions = {}, {}
    for e in events:
        word = visible_map.get(e.source_index,"")
        source = source_events.get(e.source_index,e)
        if (e.kind != "Dialogue" or not word or e.duration <= 0 or e.effect or
                not e.layer.lstrip('-').isdigit() or
                source.effect or get_pos(e.text) is None or inline_layout_key(e) or
                any(k in e.state for k in ("clip","iclip")) or
                re.search(r"\\(?:t\s*\(|move\s*\(|fad(?:e)?\s*\(|[kK](?:f|o|t)?\d|[i]?clip\s*\()",source.text)):
            continue
        identity = (e.start,e.end,e.style,e.name,e.margin_l,e.margin_r,e.margin_v)
        if len(word) >= 2 and e.state.get("1a",0) == 0:
            captions.setdefault(identity,[]).append(e)
        elif len(word) == 1 and not word.isspace():
            layout = (e.layer,) + tuple(e.state.get(k,DEFAULT_STATE.get(k))
                           for k in ("fn","fs","b","i","fscx","fscy","an","frz","frx","fry","fax","fay"))
            groups.setdefault((identity,layout),[]).append(e)
    removed = set()
    for (identity,layout),group in groups.items():
        if len(group) < 16:
            continue
        first = group[0]
        family = str(first.state.get("fn",""))
        parents = [p for p in captions.get(identity,())
                   if str(p.state.get("fn","")).casefold() != family.casefold()]
        if len(parents) != 1:
            continue
        parent = parents[0]
        all_positions = {get_pos(e.text) for e in group}
        if any(not math.isfinite(v) for pos in all_positions for v in pos):
            continue
        xs,ys = zip(*all_positions)
        height = text_height(first)
        if (len(all_positions) < 16 or height <= 0 or
                max(xs)-min(xs) < .5*height or max(ys)-min(ys) < .5*height):
            continue
        face = metric.matching_face(family,first.state.get("b",0),bool(first.state.get("i",0)))
        parent_face = metric.matching_face(str(parent.state.get("fn","")),
                                          parent.state.get("b",0),bool(parent.state.get("i",0)))
        if face is None or parent_face is None:
            continue
        # A second texture string must not stand in for a readable caption.
        parent_words = visible_map[parent.source_index]
        if any(ord(c) not in parent_face.cmap or
               metric.fragmented_glyph(parent_face,c) is not False
               for c in set(parent_words) if not c.isspace()):
            continue
        glyphs = {visible_map[e.source_index] for e in group}
        fragments = {c for c in glyphs if ord(c) in face.cmap and metric.fragmented_glyph(face,c) is True}
        stamps = [e for e in group if visible_map[e.source_index] in fragments]
        if len(fragments) < 4 or len(stamps) < 16 or len(stamps) < .9*len(group):
            continue
        positions = {get_pos(e.text) for e in stamps}
        xs,ys = zip(*positions)
        if (len(positions) < 16 or height <= 0 or
                max(xs)-min(xs) < .5*height or max(ys)-min(ys) < .5*height):
            continue
        # A slanted or rotated text row is still a row, not scattered artwork.
        mx,my = statistics.mean(xs),statistics.mean(ys)
        xx = sum((x-mx)**2 for x in xs)
        yy = sum((y-my)**2 for y in ys)
        xy = sum((x-mx)*(y-my) for x,y in positions)
        spread = (xx+yy-math.hypot(xx-yy,2*xy))/2
        if spread/len(positions) < (.1*height)**2:
            continue
        removed.update(e.source_index for e in stamps)
    return [e for e in events if e.source_index not in removed],len(removed)


def match_scale_trail(component: list[Event], visible: str,
                      animated_sources: set[int], positions: dict[int,tuple[float,float]],
                      heights: dict[int,float], layouts: dict[int,tuple]) -> list[Event] | None:
    """Return proven members of an unclipped, drifting scale-trail candidate.

    Validate shared layout, lifetime, scale and rendered-anchor trajectories
    using the caller's cached geometry. Return None for an unproven family;
    event grouping, caption selection and replacements remain with the caller.
    """
    if (len(component) < 3 or
            sum(e.source_index in animated_sources for e in component) < 3 or
            len({layouts[e.source_index] for e in component}) != 1 or
            len({e.name for e in component}) != 1):
        return None
    trail = False
    # Three distinct scales tracing the same affine position/scale
    # path establish an effect family. A nearby main fill may use
    # a slightly different authored scale; it must sit at the
    # largest trail sample, rather than at its displaced tail.
    samples=sorted(component,key=lambda e:e.state.get("fscx",100))
    lo,hi=samples[0],samples[-1]
    # Prefer the dense trail when an opaque main fill lies off its
    # scale trajectory. It is validated separately below.
    faded=[e for e in samples if e.state.get("1a",0)>0]
    if len(faded)>=3:
        samples=faded
        lo,hi=samples[0],samples[-1]
    sample_ids={e.source_index for e in samples}
    sample_start=max(e.start_s for e in samples)
    sample_end=min(e.end_s for e in samples)
    # A short lead-in/out phase outside the trail's shared visible
    # interval is not a trail member. Keep it independently rather
    # than letting it invalidate an otherwise proven family.
    members=[e for e in component if e.source_index in sample_ids or
             min(e.end_s,sample_end)>max(e.start_s,sample_start)]
    delta=hi.state.get("fscx",100)-lo.state.get("fscx",100)
    tolerance=max(.01*heights[hi.source_index],.05*hi.unit)
    if (sample_end>sample_start and delta>1e-6 and
            len({e.state.get("fscx",100) for e in samples})>=3 and
            all(e.source_index in animated_sources for e in samples)):
        lx,ly=positions[lo.source_index]; hx,hy=positions[hi.source_index]
        sy0,sy1=lo.state.get("fscy",100),hi.state.get("fscy",100)
        trail=all(
            abs(positions[e.source_index][0]-(lx+(hx-lx)*f))<=tolerance and
            abs(positions[e.source_index][1]-(ly+(hy-ly)*f))<=tolerance and
            abs(e.state.get("fscy",100)-(sy0+(sy1-sy0)*f))<=.05
            for e in samples
            for f in [(e.state.get("fscx",100)-lo.state.get("fscx",100))/delta])
        # Assess the rendered anchors, including displacement
        # around distant origins. Fit the whole family rather than
        # measuring every rotation against one endpoint sample.
        # Authored anchors/scales must still follow the path above.
        rendered=[]
        angle=hi.state.get("frz",0)
        for e in samples:
            px,py=positions[e.source_index]
            ox,oy=e.state.get("org",(px,py))
            turn=math.radians(math.remainder(e.state.get("frz",0),360))
            dx,dy=px-ox,py-oy
            rendered.append((e.state.get("fscx",100),
                             ox+dx*math.cos(turn)+dy*math.sin(turn),
                             oy-dx*math.sin(turn)+dy*math.cos(turn)))
        mean_scale=sum(v[0] for v in rendered)/len(rendered)
        mean_x=sum(v[1] for v in rendered)/len(rendered)
        mean_y=sum(v[2] for v in rendered)/len(rendered)
        variance=sum((v[0]-mean_scale)**2 for v in rendered)
        slope_x=sum((v[0]-mean_scale)*(v[1]-mean_x)
                    for v in rendered)/variance
        slope_y=sum((v[0]-mean_scale)*(v[2]-mean_y)
                    for v in rendered)/variance
        trail &= all(math.hypot(
            x-mean_x-slope_x*(scale-mean_scale),
            y-mean_y-slope_y*(scale-mean_scale))<=.06*heights[hi.source_index]
            for scale,x,y in rendered)
        # Rotation also changes glyph orientation around its
        # rendered anchor; large turns remain unsafe even when
        # anchors happen to trace a straight line.
        reference_anchor=rendered[-1][1:]
        for e in members:
            if e.source_index not in sample_ids:
                px,py=positions[e.source_index]
                ox,oy=e.state.get("org",(px,py))
                rotation=math.radians(math.remainder(e.state.get("frz",0),360))
                dx,dy=px-ox,py-oy
                anchor=(ox+dx*math.cos(rotation)+dy*math.sin(rotation),
                        oy-dx*math.sin(rotation)+dy*math.cos(rotation))
                trail &= math.dist(anchor,reference_anchor)<=.18*heights[e.source_index]
            radius=heights[e.source_index]*max(1,len(visible))
            turn=math.radians(math.remainder(e.state.get("frz",0)-angle,360))
            trail &= 2*radius*abs(math.sin(turn/2))<=.06*heights[hi.source_index]
        trail &= all(
            abs(positions[e.source_index][0]-hx)<=.18*heights[e.source_index] and
            abs(positions[e.source_index][1]-hy)<=.18*heights[e.source_index] and
            e.state.get("fscx",100)>=hi.state.get("fscx",100) and
            e.state.get("1a",0)<=hi.state.get("1a",0)
            for e in members if e.source_index not in sample_ids)
    return members if trail else None


def upright_text_holds(candidates: list[Event], source_events: dict[int,Event]) -> list[Event]:
    """Find candidate poses actually held by the original animated text.

    A midpoint sample that merely crosses zero is insufficient. Compare the
    complete settled geometry, so a hidden or flipped pose cannot win either.
    """
    holds = []
    geometry = ('pos','org','fn','fs','fscx','fscy','fsp','an','b','i','fax','fay',
                'clip','iclip','p','pbo','q')
    for e in candidates:
        original = source_events.get(e.source_index)
        if (not upright_text_state(e.state) or original is None or
                original.duration <= 0 or inline_layout_key(original)):
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',original.text).group()
        block = ''.join(OVERRIDE_RE.findall(prefix))
        frozen = freeze_block(block,original.duration,original.defaults,original.defaults,
                              original.styles,0,prior_settled_states=())
        if any(upright_text_state(state,include_shadow=True) and
               all(state.get(k,DEFAULT_STATE.get(k)) == e.state.get(k,DEFAULT_STATE.get(k))
                   for k in geometry) for state in frozen.selection.settled_states):
            holds.append(e)
    return holds


def without_inert_spacing_tail(e: Event) -> Event:
    """Ignore a tracking reset after the last literal glyph, with no ink.

    Generated punctuation can reset tracking after its sole character. The
    reset cannot move that character, but a final-state layout key mistakes
    it for the character's tracking. Keep all painted inline changes intact.
    """
    tail = re.search(r'(?:\{[^}]*\})+$',e.text)
    if tail is None or not simplify_text(e.text[:tail.start()],visible_only=True)[1]:
        return e
    tokens = [token for block in OVERRIDE_RE.findall(tail.group())
              for token in tokenize_override(block)]
    if not tokens or any(k != 'fsp' or not re.fullmatch(NUM,v) or
                         not math.isfinite(float(v)) for k,v in tokens):
        return e
    text = e.text[:tail.start()]
    tracking = effective_state(text,e.defaults,e.styles).get('fsp',0)
    return replace_event(e,text=text,state={**e.state,'fsp':tracking})






def _eligible_shrinking_row_families(events: dict[int,Event]) -> set:
    """Prefilter families with explicit moving scale fades and a positioned hold."""
    # Reject unrelated families before parsing transforms or freezing holds.
    # Every accepted shrinking fade must explicitly change both scale axes
    # and at least one visible alpha channel inside a moving source event.
    families = {(e.style,e.name) for e in events.values()
                if e.kind == 'Dialogue' and
                re.search(r'\\move\s*\(',e.text) and
                re.search(r'\\t\s*\(',e.text) and
                re.search(r'\\fscx(?=[^A-Za-z]|$)',e.text) and
                re.search(r'\\fscy(?=[^A-Za-z]|$)',e.text) and
                re.search(r'\\(?:alpha|[13]a)(?=[^A-Za-z]|$)',e.text)}
    families &= {(e.style,e.name) for e in events.values()
                 if (e.style,e.name) in families and e.kind == 'Dialogue' and
                 re.search(r'\\pos\s*\(',e.text) and
                 not re.search(r'\\move\s*\(',e.text) and
                 len(OVERRIDE_RE.sub('',e.text).strip()) >= 3}
    return families


def _shrinking_row_geometry(e: Event) -> tuple:
    """Use the existing placement/layout key, allowing the two shrinking scale axes."""
    return (e.style,e.name,placement_key(e),
            tuple((k,v) for k,v in text_layout_key(e)
                  if k not in {'fscx','fscy'}))


def _profile_shrinking_row_source(original: Event, families: set) -> ShrinkingRowSource | None:
    """Resolve one eligible source and reject unsupported geometry or timing effects."""
    if (original.kind != 'Dialogue' or original.duration <= 0 or
            (original.style,original.name) not in families or
            not re.search(r'\\(?:move|pos)\s*\(',original.text) or
            inline_layout_key(original)):
        return None
    tokens = event_override_tokens(original)
    moves = [v for k,v in tokens if k == 'move']
    transforms = [v for k,v in tokens if k == 't']
    text = simplify_text(original.text,visible_only=True)[1]
    if not text:
        return None
    evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
    state = evaluated.formatting
    e = dataclass_replace(original,state=state,continuation=evaluated.continuation)
    if (not unrotated_text_state(state) or state.get('p',0) or
            state.get('borderstyle',1) != 1 or
            any(k in state for k in ('clip','iclip','org')) or
            any(abs(state.get(k,0)) > .001 for k in ('fax','fay')) or
            any(k in {'fad','fade','k','K','kf','ko'} for k,v in tokens)):
        return None
    return ShrinkingRowSource(e,text,moves,transforms)


def _index_shrinking_row_hold(captions: dict, source: ShrinkingRowSource, max_blur: float) -> None:
    """Freeze an opaque geometry-stable hold and index both authored boundaries."""
    e,text,transforms = source.event,source.text,source.transforms
    # A held caption may fade, but its font and geometry must stay held.
    if any(any(k not in {'alpha','1a','2a','3a','4a'}
               for k,v in tokenize_override('\\'+value[1:-1].partition('\\')[2]))
           for value in transforms):
        return
    frozen,visible,drawings = simplify_visual_text(
        e.text,max_blur,e.duration,e.defaults,e.styles,1,
        upright_crossings=False)
    held = replace_event(e,text=frozen)
    if drawings or visible != text or held.state.get('1a',0) != 0:
        return
    for boundary in (e.start_s,e.end_s):
        captions.setdefault(_shrinking_row_geometry(held),{}).setdefault(boundary,[]).append(held)


def _prove_shrinking_row_glyph(source: ShrinkingRowSource) -> tuple | None:
    """Require one near-vertical move and one shrinking transform ending in transparent paint."""
    e,text,moves,transforms = source.event,source.text,source.moves,source.transforms
    state = e.state
    if (len(text) != 1 or text.isspace() or unicodedata.combining(text) or
            len(moves) != 1 or len(transforms) != 1 or get_pos(e.text) is not None):
        return None
    move = parse_effect_move(moves[0],e.duration,endpoint_slack=50)
    transform = parse_effect_transform(transforms[0],e.duration,
                                       {'fscx','fscy','alpha','1a','2a','3a','4a','blur','be'})
    if (move is None or transform is None or
            transform[0] >= 1000*e.duration or
            len(move) == 6 and move[4] >= 1000*e.duration or
            abs(move[0]-move[2]) > e.unit):
        return None
    final = state.copy()
    final_continuation = e.continuation
    for tag,value in transform[2]:
        final_continuation = apply_override(final,tag,value,e.styles,e.defaults,final_continuation)
    if (not all(0 < final.get(k,100) < state.get(k,100) for k in ('fscx','fscy')) or
            final.get('1a',0) != 255 or final.get('3a',0) != 255 or
            state.get('1a',0) == 255 and
            (state.get('3a',0) == 255 or state.get('bord',0) <= 0)):
        return None
    return e,text,move


def _index_shrinking_row_sources(events: dict[int,Event], families: set, max_blur: float) -> ShrinkingRowIndex:
    """Keep held-caption boundaries separate from complete source row groups."""
    groups, captions = {}, {}
    for original in events.values():
        source = _profile_shrinking_row_source(original,families)
        if source is None:
            continue
        e,text,moves = source.event,source.text,source.moves
        if not moves and len(text.strip()) >= 3 and get_pos(e.text) is not None:
            _index_shrinking_row_hold(captions,source,max_blur)
            continue
        glyph = _prove_shrinking_row_glyph(source)
        if glyph is not None:
            key = (_shrinking_row_geometry(e),e.start_s,e.end_s,e.layer)
            groups.setdefault(key,[]).append(glyph)
    caption_index = {key:(sorted(times),times) for key,times in captions.items()}
    return ShrinkingRowIndex(groups,caption_index)


def _shrinking_row_owners(
    caption_index: dict, metric: FontMetrics, key: tuple, start: float, end: float, peers: list,
) -> list[Event]:
    """Find boundary owners with complete literals, held geometry and exact-font anchors."""
    owners = []
    for time,helds in nearby_boundary_groups(caption_index,key,end):
        # Extend touching entrances; an existing hold can also cover the
        # whole burst. Never bridge a real gap or erase a partial overlap.
        if abs(time-end) > 1e-6:
            continue
        for held in helds:
            literal = simplify_text(held.text,visible_only=True)[1]
            if ''.join(c for e,c,m in peers) != ''.join(literal.split()):
                continue
            pos = get_pos(held.text)
            height = held.state.get('fs',20)*held.state.get('fscy',100)/100
            if (held.duration < end-start or
                    not (held.start_s == end or
                         held.start_s <= start and held.end_s >= end) or
                    any(abs(y-pos[1]) > .3*height for e,c,m in peers
                        for y in (m[1],m[3])) or
                    not matches_authored_glyph_positions(metric, 
                        held.state,[m[0] for e,c,m in peers],literal,pos[0],held.unit)):
                continue
            owners.append(held)
    return owners


def _adjust_shrinking_row_fade_handoffs(events: dict[int,Event], caption_index: dict, replacements: dict[int,Event]) -> None:
    """Trim proven transparent predecessors and delay entrances only to their fade boundary."""
    # Extending an entrance must not revive a preceding caption that was
    # already completely transparent. A single validated terminal alpha
    # transform proves a clean handoff; visible/ambiguous overlaps stay intact.
    for current in list(replacements.values()):
        original = events[current.source_index]
        if current.start_s >= original.start_s:
            continue
        preceding = [held for time,holds in nearby_boundary_groups(
                     caption_index,_shrinking_row_geometry(current),original.start_s)
                 for held in holds if held.source_index != current.source_index and
                 held.end_s == original.start_s and held.start_s < current.start_s and
                 held.layer == current.layer and get_pos(held.text) == get_pos(current.text)]
        if len(preceding) != 1:
            continue
        held = preceding[0]
        source = events[held.source_index]
        transforms = [v for k,v in event_override_tokens(source) if k == 't']
        if len(transforms) != 1:
            continue
        fade = parse_effect_transform(transforms[0],source.duration,
            {'alpha','1a','2a','3a','4a'},allow_instant=True)
        if fade is None or source.start_s+fade[1]/1000 > original.start_s+1e-6:
            continue
        evaluated = evaluate_effective_state(source.text,source.defaults,source.styles)
        final = evaluated.formatting
        final_continuation = evaluated.continuation
        for tag,value in fade[2]:
            final_continuation = apply_override(final,tag,value,source.styles,source.defaults,final_continuation)
        if not all(final.get(k,0) == 255 for k in ('1a','3a','4a')):
            continue
        finish = source.start_s+fade[1]/1000
        previous = replacements.get(held.source_index,held)
        replacements[held.source_index] = replace_event(
            previous,end=format_time(finish),end_s=finish)
        # If the preceding source stays visible for part of the entrance,
        # delay the replacement caption to its fade boundary. Keep real gaps.
        if finish > current.start_s:
            replacements[current.source_index] = replace_event(
                current,start=format_time(finish),start_s=finish)


def collapse_shrinking_glyph_rows(
    events: dict[int, Event], metric: FontMetrics | None, max_blur: float,
) -> tuple[dict[int, Event], int]:
    """Use a held caption for its complete moving, shrinking, fading row.

    Work before freezing/merging glyphs loses their source identity. Every
    layer must spell the whole caption and match its exact-font anchors at
    the held size. Paint copies may differ; the retained caption supplies
    formatting. Touching entrances and copies within the hold share that proof.
    Without a unique held owner, keep the existing simplification.
    """
    if metric is None or not metric.available:
        return events,0
    families = _eligible_shrinking_row_families(events)
    if not families:
        return events,0
    index = _index_shrinking_row_sources(events,families,max_blur)
    proposals = []
    for (key,start,end,layer),peers in index.groups.items():
        peers.sort(key=lambda item:item[2][0])
        if len(peers) < 3 or len({m[0] for e,c,m in peers}) != len(peers):
            continue
        owners = _shrinking_row_owners(index.caption_index,metric,key,start,end,peers)
        if len(owners) == 1:
            proposals.append(ShrinkingRowProposal(start,end,layer,peers,owners[0]))

    # Ambiguous repetitions at one boundary cannot share ownership. Different
    # paint layers of the same complete row deliberately share a caption.
    claims = {}
    for proposal in proposals:
        key = (proposal.held.source_index,proposal.layer,proposal.end_s)
        claims[key] = claims.get(key,0)+1
    removed, replacements = set(), {}
    for proposal in proposals:
        held = proposal.held
        if claims[(held.source_index,proposal.layer,proposal.end_s)] != 1:
            continue
        removed.update(e.source_index for e,c,m in proposal.peers)
        previous = replacements.get(held.source_index,held)
        if proposal.start_s < previous.start_s:
            replacements[held.source_index] = replace_event(
                held,start=format_time(proposal.start_s),start_s=proposal.start_s)
    if not removed:
        return events,0
    _adjust_shrinking_row_fade_handoffs(events,index.caption_index,replacements)
    return {idx:replacements.get(idx,e) for idx,e in events.items() if idx not in removed},len(removed)




































def _eligible_progressive_reveal_families(events: list[Event], visible_map: dict[int,str]) -> set:
    """Prefilter visible-text/style families containing an inline alpha reveal."""
    reveal_families = {(e.style,visible_map.get(e.source_index,'')) for e in events
                       if e.kind == 'Dialogue' and inline_layout_key(e) and
                       re.search(r'\\(?:alpha|[134]a)(?=[^A-Za-z]|$)',e.text,re.I)}
    return reveal_families


def _parse_progressive_reveal_prefix(e: Event, obj: tuple, paint: set, visible_map: dict[int,str]) -> ProgressiveRevealPrefix | None:
    """Prove consistent literal-span geometry and a visible prefix followed by hidden text."""
    literal, prefix, hidden, layout, foreground, valid = '', '', False, None, None, True
    for signature,drawing,payload in obj[-1]:
        state = dict(signature.formatting)
        if 'clip' in state:
            if state['clip'] != geometry_key(e.state.get('clip','')):
                valid = False; break
            state['clip'] = e.state['clip']
        sample = dataclass_replace(e,state=state,continuation=signature.continuation)
        geometry = state_key(sample,paint | {'pos','clip','iclip'})
        if (drawing or not unrotated_text_state(state) or
                any(k in state for k in ('iclip','org')) or
                layout is not None and geometry != layout or
                state.get('pos') != get_pos(e.text)):
            valid = False; break
        layout = geometry
        literal += payload
        invisible = all(state.get(k,0) == 255 for k in ('1a','3a','4a'))
        if invisible:
            hidden = True
        elif hidden or state.get('1a',0) >= 128:
            valid = False; break
        else:
            if foreground is not None and state_key(sample,{'clip'}) != state_key(
                    dataclass_replace(e,state=foreground,continuation=OverrideContinuation()),{'clip'}):
                valid = False; break
            foreground = state
            prefix += payload
    if not valid or not prefix or literal != visible_map[e.source_index]:
        return None
    return ProgressiveRevealPrefix(literal,prefix,layout,foreground)


def _profile_progressive_reveal_event(e: Event, visible_map: dict[int,str], reveal_families: set, paint: set) -> tuple | None:
    """Admit positioned single-line sources and validate their foreground clip and sizing."""
    if (e.kind != 'Dialogue' or not visible_map.get(e.source_index) or
            (e.style,visible_map[e.source_index]) not in reveal_families or
            get_pos(e.text) is None or any(t in e.text for t in (r'\N',r'\n',r'\h'))):
        return None
    obj = static_object_key(e,e.styles)
    if obj is None:
        return None
    parsed = _parse_progressive_reveal_prefix(e,obj,paint,visible_map)
    if parsed is None:
        return None
    literal,prefix,layout,foreground = (parsed.literal,parsed.prefix,parsed.layout,parsed.foreground)
    sample = dataclass_replace(e,state=foreground,continuation=OverrideContinuation())
    rect = rectangle_clip(sample) if 'clip' in foreground else None
    if ('clip' in foreground and rect is None or
            any(not math.isfinite(v) for v in get_pos(e.text)) or
            any(not math.isfinite(foreground.get(k,0)) or foreground.get(k,0) <= 0
                for k in ('fs','fscx','fscy'))):
        return None
    key = (e.style,e.layer,e.margin_l,e.margin_r,e.margin_v,literal,layout)
    return key,(e,prefix,foreground,rect)


def _index_progressive_reveal_families(events: list[Event], visible_map: dict[int,str], reveal_families: set) -> dict:
    """Group validated prefix/foreground fragments by the existing caption geometry key."""
    paint = {'alpha','1a','2a','3a','4a','c','1c','2c','3c','4c',
             'bord','xbord','ybord','shad','xshad','yshad','blur','be'}
    families = {}
    for e in events:
        profile = _profile_progressive_reveal_event(e,visible_map,reveal_families,paint)
        if profile is not None:
            key,item = profile
            families.setdefault(key,[]).append(item)
    return families


def _build_progressive_reveal_chains(family: list) -> list:
    """Separate distant/repeated captions and build locally increasing prefix chains."""
    # Separate distant signs and repeated captions. Candidate chains may
    # have small authored gaps, but replacements retain every such gap.
    chains = []
    for item in sorted(family,key=lambda p:(p[0].start_s,len(p[1]),p[0].source_index)):
        e,prefix,state,rect = item
        pos = get_pos(e.text)
        found = None
        for chain in reversed(chains):
            anchor = chain[0][0]
            height = min(text_height(anchor),text_height(e))
            start = chain[-1][0].start_s
            if (e.start_s <= max(p[0].end_s for p in chain)+.08+1e-6 and
                    abs(pos[0]-get_pos(anchor.text)[0]) <= .18*height and
                    abs(pos[1]-get_pos(anchor.text)[1]) <= .01*height and
                    (e.start_s == start or len(prefix) >= max(len(p[1]) for p in chain))):
                found = chain; break
        if found is None:
            chains.append([item])
        else:
            found.append(item)
    return chains


def _progressive_reveal_finishing_holds(chain: list, literal: str) -> list:
    """Require two incomplete prefixes and an unclipped complete copy finishing the reveal."""
    incomplete_prefixes = {prefix for e,prefix,state,rect in chain if prefix != literal}
    holds = [(e,state) for e,prefix,state,rect in chain if
             prefix == literal and rect is None and state.get('1a',0) < 128]
    if len(incomplete_prefixes) < 2 or not holds:
        return []
    # A complete copy must finish the reveal, rather than be an
    # unrelated simultaneous label behind a retracting prefix.
    last_prefix_start = max(e.start_s for e,prefix,state,rect in chain if prefix != literal)
    holds = [(e,state) for e,state in holds if e.start_s >= last_prefix_start]
    if not holds:
        return []
    return holds


def _progressive_reveal_strip_band(peers: list) -> ProgressiveRevealBand | None:
    """Prove a common horizontal extent and thin strips before checking temporal coverage."""
    rectangles = sorted(set(rect for e,rect in peers),key=lambda r:r[1])
    height = min(text_height(e) for e,rect in peers)
    # The union supplies the band's extent. A temporal hole in
    # any strip must not disappear merely because its neighbors
    # were coalesced across different start/end boundaries.
    if (len(rectangles) < 3 or
            len({(r[0],r[2]) for r in rectangles}) != 1 or
            any(r[3]-r[1] > .08*height for r in rectangles)):
        return None
    top,bottom = rectangles[0][1],max(r[3] for r in rectangles)
    return ProgressiveRevealBand(height,top,bottom)


def _progressive_reveal_strips_cover_band(peers: list) -> bool:
    """Aggregate simultaneous tile changes and prove each nonempty interval covers the whole band."""
    extent = _progressive_reveal_strip_band(peers)
    if extent is None:
        return False
    height,top,bottom = extent.height,extent.top,extent.bottom
    changes = {}
    for e,rect in peers:
        changes.setdefault(e.start_s,[]).append((rect,1))
        changes.setdefault(e.end_s,[]).append((rect,-1))
    active = {}
    for time,updates in sorted(changes.items()):
        # Aggregate simultaneous ends/starts before checking the
        # next half-open interval; a touching tile has no gap.
        for rect,delta in updates:
            active[rect] = active.get(rect,0)+delta
            if not active[rect]:
                del active[rect]
        if not active:
            continue
        band = sorted(active,key=lambda r:r[1])
        if (len(band) < 3 or bottom-top < .3*height or
                abs(band[0][1]-top) > .001 or
                abs(band[-1][3]-bottom) > .001 or
                any(abs(a[3]-b[1]) > .001 for a,b in zip(band,band[1:]))):
            return False
    return True


def _progressive_reveal_strip_coverage(chain: list) -> bool:
    """Group strips by prefix/paint and reject any group without complete coverage."""
    tiles = {}
    for e,prefix,state,rect in chain:
        if rect is not None:
            tiles.setdefault((prefix,state_key(
                dataclass_replace(e,state=state,continuation=OverrideContinuation()),{'pos','clip'})),[]).append((e,rect))
    for peers in tiles.values():
        if not _progressive_reveal_strips_cover_band(peers):
            return False
    return True


def _select_progressive_reveal_caption(holds: list, chain: list, literal: str) -> ProgressiveRevealCaption:
    """Select foreground paint by opacity/duration/source order and retain its fill transparency."""
    chosen,state = max(holds,key=lambda p:(-p[1].get('1a',0),
                                           p[0].duration,-p[0].source_index))
    source_paint = _source_caption_paint(state,[p[1] for p in holds])
    body = render_simplified_caption(state,literal,outline_states=[p[2] for p in chain],measurement=chosen.measurement,
                                     source_paint=source_paint)
    if state.get('1a',0):
        # The shared caption renderer normalizes opacity for effects.
        # This proof also accepts an already simplified translucent
        # foreground: keep its actual fill transparency.
        end_header = body.index('}')
        tags = render_tag('1a',state['1a'])
        if source_paint is not None and max(source_paint.border)>0 and state.get('3a',0)==state['1a']:
            # This route preserves fill transparency rather than freezing it.
            # Restore the coupled source contour opacity as well.
            tags += render_tag('3a',state['3a'])
        body = body[:end_header]+tags+body[end_header:]
    return ProgressiveRevealCaption(chosen,body)


def _progressive_reveal_intervals(chain: list) -> list[list[float]]:
    """Coalesce only overlapping/touching lifetimes so real authored gaps survive."""
    intervals = []
    for e,_,_,_ in sorted(chain,key=lambda p:(p[0].start_s,p[0].end_s)):
        if intervals and e.start_s <= intervals[-1][1]+1e-6:
            intervals[-1][1] = max(intervals[-1][1],e.end_s)
        else:
            intervals.append([e.start_s,e.end_s])
    return intervals


def _record_progressive_reveal_replacements(chain: list, literal: str, caption: ProgressiveRevealCaption, visibility_updates: dict[int,str], removed: set[int], replacements: dict[int,Event]) -> None:
    """Record captions and local visibility deltas for each covered interval."""
    chosen,body = caption.event,caption.body
    intervals = _progressive_reveal_intervals(chain)
    for start,end in intervals:
        members = [e for e,_,_,_ in chain if e.start_s < end and e.end_s > start]
        index = min(e.source_index for e in members)
        replacements[index] = replace_event(chosen,start=format_time(start),start_s=start,
            end=format_time(end),end_s=end,text=body,source_index=index,effect='')
        visibility_updates[index] = literal
        removed.update(e.source_index for e in members)


def collapse_progressive_text_reveals(events: list[Event],
                                      visible_map: dict[int,str]) -> TextVisibilityResult:
    """Freeze a proved prefix reveal at its complete foreground caption.

    Literal-span state distinguishes a visible prefix from its hidden suffix;
    the event's final state may describe only that suffix. Require increasing
    prefixes, a final unclipped visible copy, and matching text geometry. Thin
    clipped glitch strips must cover their complete band at every boundary.
    Preserve actual gaps and reject resets, changing layout and partial tiles.
    Borrow visibility during matching and return updates for accepted captions,
    including reveals whose preserved gaps leave the event count unchanged.
    """
    reveal_families = _eligible_progressive_reveal_families(events,visible_map)
    if not reveal_families:
        return TextVisibilityResult(events,0,{})
    families = _index_progressive_reveal_families(events,visible_map,reveal_families)
    removed,replacements = set(), {}
    visibility_updates: dict[int,str] = {}
    for key,family in families.items():
        literal = key[-2]
        for chain in _build_progressive_reveal_chains(family):
            holds = _progressive_reveal_finishing_holds(chain,literal)
            if not holds or not _progressive_reveal_strip_coverage(chain):
                continue
            caption = _select_progressive_reveal_caption(holds,chain,literal)
            _record_progressive_reveal_replacements(
                chain,literal,caption,visibility_updates,removed,replacements)
    output = [replacements.get(e.source_index,e) for e in events
              if e.source_index not in removed or e.source_index in replacements]
    return TextVisibilityResult(output,len(events)-len(output),visibility_updates)


def _prepare_text_effect_sequence_pass(events: list[Event], context: TextEffectSequenceContext
                                       ) -> tuple[list[Event],int]:
    """Complete exact-position reduction before attempting wider scale trails."""
    if not context.scale_trails:
        return events,0
    # Keep the established recursion contract: the exact-position pass does
    # not receive font metrics or repeat the wider animation pipeline.
    return flatten_text_effect_sequences(
        events,context.visible_map,context.styles,context.animated_sources,False,
        source_events=context.source_events, font_report=context.font_report,
        lyric_boundaries=context.lyric_boundaries)


def _group_text_effect_sequences(events: list[Event], context: TextEffectSequenceContext
                                 ) -> tuple[dict[tuple,list[Event]],list[Event]]:
    """Group eligible visible captions while separating original flying letters."""
    buckets, output = {}, []
    for e in events:
        visible=context.visible_map.get(e.source_index,"")
        if e.kind!="Dialogue" or not visible or get_pos(e.text) is None or e.state.get("p",0):
            output.append(e)
            continue
        key=(e.style,visible)
        if context.source_events is not None and len(visible) == 1:
            original = context.source_events.get(e.source_index)
            # A frozen flying letter can land near a different stationary
            # letter. It is not a styling phase of that neighbour's caption.
            key += (bool(original and re.search(r"\\move\s*\(",original.text,re.I)),)
        if context.scale_trails:
            key+=(e.name,tuple((k,v) for k,v in text_layout_key(e)
                              if k not in {"fscx","fscy","frz"}),placement_key(e))
        buckets.setdefault(key,[]).append(e)
    return buckets,output


def _index_text_effect_sequence_geometry(bucket: list[Event]) -> TextEffectSequenceGeometry:
    """Cache unchanged position, height and non-scale layout for one sequence bucket."""
    # Cache the geometry used while clustering. Scale trails change their
    # position and scale together, but not the font or paragraph layout.
    positions = {e.source_index: get_pos(e.text) for e in bucket}
    heights = {e.source_index: text_height(e) for e in bucket}
    layouts = {e.source_index: (tuple((k,v) for k,v in text_layout_key(e)
                                     if k not in {"fscx","fscy","frz"}), placement_key(e))
               for e in bucket}
    return TextEffectSequenceGeometry(positions,heights,layouts)


def _text_effect_sequence_neighbor(context: TextEffectSequenceContext,
                                   geometry: TextEffectSequenceGeometry, e: Event, pos: tuple,
                                   component: list[Event], reference: Event) -> bool:
    """Check connected timing, fade handoffs, scale allowance and authored margins."""
    previous=component[-1]
    if (context.lyric_boundaries is not None and
            any(_crosses_lyric_boundary(context.lyric_boundaries,member,e,complete_only=True) for member in component)):
        return False
    span_start = min(x.start_s for x in component)
    span_end = max(x.end_s for x in component)
    if e.start_s > span_end+1e-6:
        return False
    # Brief fade overlaps between consecutive captions must not
    # link their repeated letters into one long styling sequence.
    # Nested highlight phases remain eligible; genuinely touching
    # phases still share the exact centisecond boundary.
    overlap = min(e.end_s,span_end)-max(e.start_s,span_start)
    if (e.start_s > span_start and e.end_s > span_end and
            1e-6 < overlap < .8*min(e.duration,span_end-span_start)):
        return False
    anchor=geometry.positions[previous.source_index]
    allowance=.18*min(geometry.heights[e.source_index],geometry.heights[previous.source_index])
    # Only broaden candidates for animated, strongly overlapping
    # copies with the same non-scale layout. The affine trajectory
    # test below must still prove that these form one scale trail.
    if (context.scale_trails and not any(k in e.state or k in reference.state
                                    for k in ("clip","iclip")) and
            (e.source_index in context.animated_sources or
            pos==geometry.positions[reference.source_index]) and
            geometry.layouts[e.source_index]==geometry.layouts[reference.source_index] and
            e.name==reference.name and
            min(e.end_s,reference.end_s)-max(e.start_s,reference.start_s)
                >= .8*min(e.duration,reference.duration)):
        anchor=geometry.positions[reference.source_index]
        allowance=geometry.heights[reference.source_index]
    if (abs(pos[0]-anchor[0])<=allowance and
        abs(pos[1]-anchor[1])<=allowance and
        e.margin_l==previous.margin_l and
        e.margin_r==previous.margin_r and
        e.margin_v==previous.margin_v):
        return True
    return False


def _cluster_text_effect_sequences(context: TextEffectSequenceContext,
                                   geometry: TextEffectSequenceGeometry, bucket: list[Event]
                                   ) -> list[list[Event]]:
    """Build source-ordered components and retain the highest-sample reference."""
    components=[]
    anchors={}
    for e in sorted(bucket,key=lambda x:(x.start_s,x.end_s,x.source_index)):
        pos=get_pos(e.text)
        found=None
        for component in reversed(components):
            if _text_effect_sequence_neighbor(context,geometry,e,pos,component,anchors[id(component)]):
                found=component;break
        if found is None:
            component=[e]
            components.append(component)
            anchors[id(component)]=e
        else:
            found.append(e)
            if geometry.heights[e.source_index]>geometry.heights[anchors[id(found)].source_index]:
                anchors[id(found)]=e
    return components


def _prove_text_effect_sequence(context: TextEffectSequenceContext,
                                geometry: TextEffectSequenceGeometry, visible: str,
                                component: list[Event]
                                ) -> tuple[TextEffectSequenceProfile | None,list[Event]]:
    """Apply scale-trail proof and existing phase admission, preserving every excluded member."""
    retained=[]
    if len(component)<2:
        return None,retained+component
    clipped=any("clip" in e.state or "iclip" in e.state for e in component)
    drifting=len({geometry.positions[e.source_index] for e in component})>1
    members = (match_scale_trail(component,visible,context.animated_sources,geometry.positions,geometry.heights,geometry.layouts)
               if context.scale_trails and not clipped and drifting else None)
    trail = members is not None
    if context.scale_trails and not trail:
        return None,retained+component
    if trail:
        member_ids={e.source_index for e in members}
        retained.extend(e for e in component if e.source_index not in member_ids)
        component=members
    if not clipped and (len({e.name for e in component}) != 1 or
            drifting and not trail or
            (len({state_key(e) for e in component}) < 2 and
             not (all(e.source_index in (context.animated_sources or set()) for e in component) and
                  len({e.text for e in component}) == 1 and
                  len({e.layer for e in component}) == 1 and
                  all(a.end == b.start for a,b in zip(component,component[1:]))))):
        return None,retained+component
    visible_candidates=[e for e in component if e.state.get("1a",255)<255]
    if not visible_candidates:
        return None,retained+component
    start=min(e.start_s for e in component)
    end=max(e.end_s for e in component)
    return TextEffectSequenceProfile(component,visible_candidates,clipped,trail,start,end),retained


def _select_text_effect_sequence_geometry(context: TextEffectSequenceContext,
                                      geometry: TextEffectSequenceGeometry,
                                      profile: TextEffectSequenceProfile) -> Event:
    """Choose full-sized trail geometry, a temporal sample, or a proven upright hold."""
    if profile.clipped:
        chosen=max(profile.visible_candidates,key=lambda e:(
            e.state.get("1a",255)==0,
            "clip" not in e.state and "iclip" not in e.state,
            e.duration,int(e.layer) if e.layer.lstrip("-").isdigit() else 0))
        return chosen
    midpoint=(profile.start_s+profile.end_s)/2
    if profile.trail:
        # Keep the most visible full-sized sample, not a tiny tail
        # or an arbitrary frame nearer the temporal midpoint.
        chosen=max(profile.visible_candidates,key=lambda e:(
            -e.state.get("1a",255), geometry.heights[e.source_index],
            int(e.layer) if e.layer.lstrip("-").isdigit() else 0))
    else:
        rank = lambda e: (e.start_s <= midpoint < e.end_s,
                          -max(e.start_s-midpoint,midpoint-e.end_s,0),
                          -e.state.get("1a",255),
                          int(e.layer) if e.layer.lstrip("-").isdigit() else 0)
        def choose(candidates):
            ordered = sorted(candidates,key=lambda e:(e.start_s,e.end_s))
            if any(b.start_s<a.end_s-1e-6 for a,b in zip(ordered,ordered[1:])):
                # Simultaneous paint/effect alternatives are not a sampled
                # motion timeline. Their existing compositing representative
                # remains the owner; frame dwell cannot establish that role.
                return max(candidates,key=rank)
            pose,_ = _representative_frame_pose(candidates)
            key = _frame_pose_key(pose)
            # The ordinary sequence's existing literal/paint representative
            # remains independent of geometry, among records at that pose.
            return max((e for e in candidates if _frame_pose_key(e)==key),key=rank)
        chosen = choose(profile.visible_candidates)
        if (context.source_events is not None and
                any(e.source_index in context.animated_sources for e in profile.members) and
                not unrotated_text_state(chosen.state)):
            # Prefer a real readable hold over a longer rotated
            # entrance. Paint dwell and full cue timing stay shared.
            holds = upright_text_holds(profile.visible_candidates,context.source_events)
            if holds:
                chosen = choose(holds)
    return chosen


def _select_text_effect_sequence_paint(context: TextEffectSequenceContext,
                                   profile: TextEffectSequenceProfile, chosen: Event
                                   ) -> tuple[dict,str]:
    """Select sustained event paint without changing representative geometry."""
    selection = select_static_state(chosen.state,[],set(),context.styles,chosen.defaults,
        paint_events=profile.visible_candidates,continuation=chosen.continuation)
    state = selection.state
    # Preserve the chosen object's geometry and inline text. The
    # shared selector changes only colours when given event paint.
    color_tags = '' if profile.clipped else ''.join(render_tag(k,state[k]) for k in ('1c','3c','4c')
                         if state.get(k) != chosen.state.get(k) and k in state)
    return state,color_tags


def _construct_text_effect_sequence_caption(context: TextEffectSequenceContext,
                                          geometry: TextEffectSequenceGeometry,
                                          profile: TextEffectSequenceProfile) -> Event:
    """Construct the caption while preserving each route's text, timing and layer rules."""
    chosen = _select_text_effect_sequence_geometry(context,geometry,profile)
    state,color_tags = _select_text_effect_sequence_paint(context,profile,chosen)
    if profile.clipped or profile.trail:
        text = render_simplified_caption(state,OVERRIDE_RE.sub("",chosen.text),
                                        outline_states=[e.state for e in profile.members],measurement=chosen.measurement,
                                        source_paint=_source_caption_paint(state,[e.state for e in profile.members]))
    elif color_tags and chosen.text.startswith('{'):
        index = chosen.text.index('}')
        text = chosen.text[:index]+color_tags+chosen.text[index:]
    else:
        text = ('{'+color_tags+'}' if color_tags else '')+chosen.text
    timing = dict(start=format_time(profile.start_s),end=format_time(profile.end_s),
                  start_s=profile.start_s,end_s=profile.end_s,
                  source_index=min(e.source_index for e in profile.members))
    if profile.clipped:
        timing.update(layer="0",effect="")
    caption = replace_event(chosen,text=text,**timing)
    return _preserve_frame_pose_support(chosen,caption,profile.visible_candidates)


def _flatten_text_effect_sequence_bucket(context: TextEffectSequenceContext, key: tuple,
                                        bucket: list[Event]) -> tuple[list[Event],int]:
    """Cluster, prove and construct independent captions within one grouping key."""
    style,visible=key[:2]
    geometry = _index_text_effect_sequence_geometry(bucket)
    output=[]
    removed=0
    for component in _cluster_text_effect_sequences(context,geometry,bucket):
        profile,retained = _prove_text_effect_sequence(context,geometry,visible,component)
        output.extend(retained)
        if profile is None:
            continue
        output.append(_construct_text_effect_sequence_caption(context,geometry,profile))
        removed += len(profile.members)-1
    return output,removed


def _finish_text_effect_sequences(context: TextEffectSequenceContext, output: list[Event],
                                  removed: int) -> tuple[list[Event],int]:
    """Run the existing movement/paint handoff and final exact-position consolidation."""
    if context.scale_trails and context.source_events is not None:
        output,phase_removed = collapse_moving_glyph_sequences(
            output,context.visible_map,context.source_events,context.font_metrics)
        removed += phase_removed
        output = normalize_karaoke_completion_paint(output,context.visible_map,context.source_events)
    if context.scale_trails:
        # Unmasking/normalizing can expose an ordinary same-anchor phase.
        # Repeat only the existing exact-position phase rules, retaining
        # original move/hold evidence and avoiding another animation pass.
        output,phase_removed = flatten_text_effect_sequences(
            output,context.visible_map,context.styles,context.animated_sources,False,
            source_events=context.source_events, font_report=context.font_report,
            lyric_boundaries=context.lyric_boundaries)
        removed += phase_removed
    return sorted(output,key=lambda e:e.source_index),removed


def flatten_text_effect_sequences(
    events: list[Event], visible_map: dict[int, str], styles: dict,
    animated_sources: set[int] | None=None, _scale_trails: bool=True, *,
    source_events: dict[int, Event] | None=None, font_metrics: FontMetrics | None=None,
    font_report: FontProcessingReport | None=None,
    lyric_boundaries: LyricBoundaryIndex | None=None,
) -> tuple[list[Event], int]:
    """Freeze connected full-text styling phases as one static caption.

    For unmasked text keep representative geometry and sustained colours;
    for clipped effects retain a plain readable caption. Gaps split runs.
    """
    context = TextEffectSequenceContext(
        visible_map,styles,animated_sources or set(),_scale_trails,source_events,font_metrics,
        font_report=font_report,
        lyric_boundaries=lyric_boundaries or _index_lyric_boundaries(events,visible_map))
    events,removed = _prepare_text_effect_sequence_pass(events,context)
    buckets,output = _group_text_effect_sequences(events,context)
    for key,bucket in buckets.items():
        captions,count = _flatten_text_effect_sequence_bucket(context,key,bucket)
        output.extend(captions)
        removed += count
    return _finish_text_effect_sequences(context,output,removed)


def match_authored_lyric_rows(events: list[Event], visible_map: dict[int, str],
                              source_events: dict[int, Event]) -> AuthoredLyricRowsResult:
    """Prove complete captions from matching entrance and exit letter rows.

    Return removable source indices, row additions and resolved source updates
    for the existing covered-fragment pass. Original move endpoints prove
    placement; caption text and timing remain unchanged, and ambiguous or
    incomplete matches stay intact. Resolve private successors without caching
    into borrowed events, including when events and source-map entries alias.
    """
    removed: set[int] = set()
    row_evidence: list[TextRow] = []
    source_successors: dict[int,Event] = {}
    norm = lambda value: "".join(value.split()).casefold()
    moving: dict[tuple,list[tuple[Event,Event,list[float]]]] = {}
    captions: dict[tuple,list[tuple[Event,Event]]] = {}
    families = {(e.style,e.name) for e in events
                if visible_map.get(e.source_index,"") and
                (source := source_events.get(e.source_index)) is not None and
                re.search(r"\\move\s*\(",source.text,re.I)}
    for e in events:
        original = source_events.get(e.source_index)
        source = source_successors.get(id(original),original)
        words = visible_map.get(e.source_index, "")
        if ((e.style,e.name) not in families or source is None or
                e.kind != "Dialogue" or not words or
                source.duration <= 0 or inline_layout_key(e)):
            continue
        is_move = bool(re.search(r"\\move\s*\(",source.text,re.I))
        if not is_move and len(words) < 8:
            continue
        if not is_move and re.search(r"\\(?:t|fad(?:e)?)\s*\(",source.text,re.I):
            continue
        evaluated = event_evaluation(source)
        state = evaluated.formatting
        if not source.state:
            source = dataclass_replace(source,state=state,continuation=evaluated.continuation)
            source_successors[id(original)] = source
        # The input event list may contain the source object itself. Earlier
        # caching resolved that alias too; use its successor for the same proof.
        if e is original:
            e = source
        if (state.get("p",0) or state.get("1a",0) != 0 or
                any(k in state for k in ("clip","iclip","org")) or
                any(abs(state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        key = (e.style,e.name,placement_key(source)[0],
               tuple((k,v) for k,v in text_layout_key(source) if k != "an"))
        if is_move:
            tokens = [token for block in OVERRIDE_RE.findall(source.text)
                      for token in tokenize_override(block)]
            moves = [value for tag,value in tokens if tag == "move"]
            if (len(moves) != 1 or state.get("an") != 5 or
                    any(tag == "t" for tag,value in tokens)):
                continue
            try:
                values = [float(v) for v in moves[0].strip("()").split(",")]
            except ValueError:
                continue
            if len(values) not in (4,6) or not all(math.isfinite(v) for v in values):
                continue
            if len(values) == 6 and not 0 <= values[4] < values[5] <= 1000*source.duration+.001:
                continue
            moving.setdefault((key,source.start,source.end,source.layer),[]).append((e,source,values))
        elif get_pos(e.text) is None:
            captions.setdefault(key,[]).append((e,source))
    rows: dict[tuple,list[list[tuple[Event,Event,list[float]]]]] = {}
    for (key,start,end,layer),pieces in moving.items():
        if len(pieces) >= 8:
            rows.setdefault((key,"in",end),[]).append(pieces)
            rows.setdefault((key,"out",start),[]).append(pieces)
    for key,full_lines in captions.items():
        colliding = set()
        latest = None
        for full,source in sorted(full_lines,key=lambda pair:pair[0].start_s):
            if latest is not None and full.start_s < latest.end_s:
                colliding.update((full.source_index,latest.source_index))
            if latest is None or full.end_s > latest.end_s:
                latest = full
        for full,source in full_lines:
            # Style-based placement may move under ASS collision handling.
            # Overlapping unpositioned captions cannot prove this baseline.
            if full.source_index in colliding:
                continue
            height = text_height(source)
            alignment = int(source.state.get("an",2))
            if alignment not in range(1,10) or height <= 0:
                continue
            width,canvas_height = source.measurement.canvas or (0,0)
            left,right,vertical = placement_key(source)[0]
            expected_y = (canvas_height-vertical-height/2 if alignment <= 3 else
                          canvas_height/2 if alignment <= 6 else vertical+height/2)
            matched = {"in":[],"out":[]}
            adjacent = [(phase,pieces) for phase,boundary in
                        (("in",source.start),("out",source.end))
                        for pieces in rows.get((key,phase,boundary),[])]
            for phase,pieces in adjacent:
                first = pieces[0][1]
                if first.layer != source.layer:
                    continue
                offset = 2 if phase == "in" else 0
                ordered = sorted(pieces,key=lambda piece:piece[2][offset])
                positions = [tuple(values[offset:offset+2]) for e,original,values in ordered]
                xs,ys = [p[0] for p in positions],[p[1] for p in positions]
                if (norm("".join(visible_map[e.source_index] for e,original,values in ordered)) !=
                        norm(visible_map[full.source_index]) or
                        any(b-a <= full.unit for a,b in zip(xs,xs[1:])) or
                        max(ys)-min(ys) > .06*height or
                        abs(statistics.median(ys)-expected_y) > .06*height):
                    continue
                horizontal = (alignment-1)%3
                if (horizontal == 0 and not left <= xs[0] <= left+height or
                        horizontal == 2 and not width-right-height <= xs[-1] <= width-right or
                        horizontal == 1 and abs((xs[0]+xs[-1])/2-width/2) > height/2):
                    continue
                matched[phase].append((ordered,positions))
            if len(matched["in"]) != 1 or len(matched["out"]) != 1:
                continue
            entrance,positions = matched["in"][0]
            exit_row,exit_positions = matched["out"][0]
            if (any(visible_map[a[0].source_index] != visible_map[b[0].source_index]
                    for a,b in zip(entrance,exit_row)) or len(entrance) != len(exit_row) or
                    any(math.dist(a,b) > full.unit for a,b in zip(positions,exit_positions))):
                continue
            # Feed the established covered-fragment pass a real row model.
            # It owns nested syllable removal and its font/actor/layer guards.
            # The model's centered placement does not alter the caption.
            pieces = [(replace_event(original,text=render_simplified_caption(
                original.state,visible_map[e.source_index],an=5,pos=pos,measurement=original.measurement,
                source_paint=_source_caption_paint(original.state,[original.state]))),
                visible_map[e.source_index],pos)
                for (e,original,values),pos in zip(entrance,positions)]
            center = ((positions[0][0]+positions[-1][0])/2,statistics.median(p[1] for p in positions))
            base = replace_event(full,text=render_simplified_caption(full.state,visible_map[full.source_index],
                                                              an=5,pos=center,measurement=full.measurement,
                                                              source_paint=_source_caption_paint(full.state,[full.state])))
            row_evidence.append(TextRow(base,pieces))
            removed.update(e.source_index for row in (entrance,exit_row) for e,original,values in row)
    source_updates = {index:source_successors[id(event)] for index,event in source_events.items()
                      if id(event) in source_successors} if source_successors else {}
    return AuthoredLyricRowsResult(removed,row_evidence,source_updates)


def match_nested_glyph_copies(
    events: list[Event], visible_map: dict[int, str], metric: FontMetrics | None,
) -> set[int]:
    """Prove complete letter copies inside equally painted word fragments.

    Require near-coextensive nested timing and exact-font glyph spacing and
    anchors, rather than a shared word center alone. Every letter in a phase
    must have one owner; missing, extra or multiply owned letters keep that
    whole phase. Parent-only fragments are retained, including lone letters.
    """
    if metric is None or not metric.available:
        return set()
    groups = {}
    for e in events:
        word = visible_map.get(e.source_index,"")
        pos = get_pos(e.text)
        if (e.kind != "Dialogue" or not word or pos is None or e.effect or
                e.duration <= 0 or not e.layer.lstrip('-').isdigit() or
                e.state.get('1a',0) != 0 or e.state.get('p',0) or
                e.state.get('borderstyle',1) != 1 or inline_layout_key(e) or
                any(k in e.state for k in ('clip','iclip','org')) or
                any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay','fsp')) or
                any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word) or
                OVERRIDE_RE.sub('',e.text) != word or
                any(not math.isfinite(v) for v in (*pos,e.start_s,e.end_s)) or
                static_object_key(e,e.styles) is None):
            continue
        key = (e.style,e.name,e.row,placement_key(e),state_key(e,{'pos'}))
        groups.setdefault(key,{}).setdefault((e.start,e.end,e.layer),[]).append(e)

    proposals = []
    for phases in groups.values():
        by_start = {}
        for (start,end,layer),group in phases.items():
            by_start.setdefault((start,layer),[]).extend(group)
        parents = [group for group in by_start.values()
                   if sum(len(visible_map[e.source_index]) > 1 for e in group) >= 4]
        children = sorted((group for group in phases.values()
                           if len(group) >= 8 and all(len(visible_map[e.source_index]) == 1
                                                    for e in group)),key=lambda g:g[0].start_s)
        starts = [group[0].start_s for group in children]
        for parent_group in parents:
            # Earlier phase merging can extend one held fragment beyond its
            # neighbors. It remains valid backing throughout the shorter cue;
            # keep that lifetime and use the common end only for phase lookup.
            parent = min(parent_group,key=lambda e:e.end_s)
            if len({get_pos(e.text) for e in parent_group}) != len(parent_group):
                continue
            for child_group in children[bisect_left(starts,parent.start_s-1e-6):
                                        bisect_right(starts,parent.start_s+.25+1e-6)]:
                child = child_group[0]
                if (child.end_s > parent.end_s+1e-6 or
                        parent.end_s-child.end_s > .25+1e-6 or
                        child.duration < .8*parent.duration or
                        child.start == parent.start and child.end == parent.end):
                    continue
                ordered = sorted(child_group,key=lambda e:get_pos(e.text)[0])
                xs = [get_pos(e.text)[0] for e in ordered]
                if any(b-a <= child.unit for a,b in zip(xs,xs[1:])):
                    continue
                letters = [visible_map[e.source_index] for e in ordered]
                owners = [0]*len(ordered)
                matched = 0
                for p in parent_group:
                    word = visible_map[p.source_index]
                    px,py = get_pos(p.text)
                    options = []
                    for index in range(len(ordered)-len(word)+1):
                        stop = index+len(word)
                        if (''.join(letters[index:stop]) != word or
                                any(abs(get_pos(e.text)[1]-py) > .25*p.unit
                                    for e in ordered[index:stop])):
                            continue
                        anchor = fit_fragment_anchor(metric, p.state,xs[index:stop],letters[index:stop],
                                                        word,p.unit,separate_glyphs=True,exact_size=True)
                        if anchor is not None and abs(anchor-px) <= .25*p.unit:
                            options.append((index,stop))
                    if len(options) > 1:
                        matched = -1; break
                    if options:
                        index,stop = options[0]
                        for i in range(index,stop):
                            owners[i] += 1
                        matched += len(word) > 1
                if matched >= 4 and all(owner == 1 for owner in owners):
                    proposals.append({e.source_index for e in child_group})
    ownership = {}
    for members in proposals:
        for index in members:
            ownership[index] = ownership.get(index,0)+1
    return {index for members in proposals if all(ownership[i] == 1 for i in members)
            for index in members}


def match_staggered_full_line_copies(
    events: list[Event], visible_map: dict[int, str], metric: FontMetrics | None,
) -> set[int]:
    """Match complete, near-coextensive glyph rows to retained full captions.

    Exact font advances and the authored spaces prove the whole row, including
    style-based caption placement. Actor labels may differ, but each letter
    row keeps its own label/layer and needs exactly one owner. Keep the full
    caption's formatting and timing; staggered copy lead-ins/tails are effects.
    """
    if metric is None or not metric.available:
        return set()
    captions, groups, unpositioned = [], {}, {}

    def geometry(e: Event) -> tuple:
        return (e.style,placement_key(e)[0],
                tuple((k,str(v).casefold() if k == 'fn' else v)
                      for k,v in text_layout_key(e) if k != 'an'),
                (int(e.state.get('an',2))-1)%3)

    for e in events:
        word = visible_map.get(e.source_index,'')
        if e.kind != 'Dialogue' or not word or e.duration <= 0:
            continue
        pos = get_pos(e.text)
        if pos is None and not e.state.get('p',0):
            collision_layer = int(e.layer) if e.layer.lstrip('+-').isdigit() else 0
            unpositioned.setdefault((collision_layer,(int(e.state.get('an',2))-1)//3),[]).append(e)
        if (not e.layer.lstrip('-').isdigit() or e.state.get('1a',0) != 0 or
                e.state.get('p',0) or e.state.get('borderstyle',1) != 1 or
                inline_layout_key(e) or not unrotated_text_state(e.state) or
                any(k in e.state for k in ('clip','iclip','org')) or
                any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay'))):
            continue
        if len(word) == 1 and not word.isspace() and pos is not None:
            key = (geometry(e),e.name,e.layer,e.row)
            groups.setdefault(key,[]).append(e)
        elif len(''.join(word.split())) >= 3:
            captions.append(e)
    if not captions or not groups:
        return set()

    # Default ASS placement can shift under collision handling. Only isolated
    # unpositioned captions prove a baseline, even across different styles.
    colliding = set()
    for peers in unpositioned.values():
        previous = None
        for e in sorted(peers,key=lambda item:item.start_s):
            if previous is not None and e.start_s < previous.end_s:
                colliding.update((previous.source_index,e.source_index))
            if previous is None or e.end_s > previous.end_s:
                previous = e
    indexes = {}
    for (key,name,layer,row),peers in groups.items():
        ordered = sorted(peers,key=lambda e:e.start_s)
        indexes.setdefault(key,[]).append((int(layer),[e.start_s for e in ordered],ordered))

    proposals = []
    for full in captions:
        key = geometry(full)
        families = indexes.get(key,[])
        if not families or full.source_index in colliding:
            continue
        pos = get_pos(full.text)
        canvas = full.measurement.canvas
        alignment = int(full.state.get('an',2))
        if alignment not in range(1,10) or static_object_key(
                full,full.styles,allow_unpositioned=True) is None:
            continue
        left,right,vertical = placement_key(full)[0]
        height = text_height(full)
        if pos is None:
            if canvas is None:
                continue
            width,canvas_height = canvas
            horizontal = (alignment-1)%3
            pos = (left if horizontal == 0 else width-right if horizontal == 2 else
                   (left+width-right)/2,
                   canvas_height-vertical if alignment <= 3 else
                   canvas_height/2 if alignment <= 6 else vertical)
        center_y = pos[1]+((alignment-1)//3-1)*height/2
        text = visible_map[full.source_index]
        # Stagger may grow with a long cue. Bound both endpoints and shared
        # visibility relative to that cue instead of assuming a fixed delay.
        allowance = .2*full.duration
        for layer,starts,peers in families:
            if layer > int(full.layer):
                continue
            candidates = peers[bisect_left(starts,full.start_s-allowance-1e-6):
                               bisect_right(starts,full.start_s+allowance+1e-6)]
            candidates = [e for e in candidates
                if abs(e.end_s-full.end_s) <= allowance+1e-6 and
                   min(e.end_s,full.end_s)-max(e.start_s,full.start_s) >=
                        .8*max(e.duration,full.duration)-1e-6 and
                   e.state.get('1c') == full.state.get('1c') and
                   abs(get_pos(e.text)[1]+((int(e.state.get('an',5))-1)//3-1)*
                       text_height(e)/2-center_y) <= full.unit]
            candidates.sort(key=lambda e:get_pos(e.text)[0])
            if (len(candidates) != len(''.join(text.split())) or
                    ''.join(visible_map[e.source_index] for e in candidates) != ''.join(text.split()) or
                    len({get_pos(e.text)[0] for e in candidates}) != len(candidates) or
                    not matches_authored_glyph_positions(metric, 
                        full.state,[get_pos(e.text)[0] for e in candidates],text,pos[0],full.unit)):
                continue
            # A caption that wraps is not the single row the letters prove.
            # Explicit no-wrap formatting can intentionally span the canvas.
            if full.state.get('q') != 2:
                if canvas is None:
                    continue
                face = metric.matching_face(str(full.state.get('fn','')),
                    full.state.get('b',0),bool(full.state.get('i',0)))
                try:
                    span = (metric.measure(face,text,bool(full.state.get('kerning',False)))*
                            metric.ass_em_scale(face)*full.state.get('fs',20)*
                            full.state.get('fscx',100)/100/1024+
                            full.state.get('fsp',0)*full.state.get('fscx',100)/100*(len(text)-1))
                except (OSError,ValueError,RuntimeError,TypeError):
                    continue
                if span > canvas[0]-left-right+full.unit:
                    continue
            if any(static_object_key(e,e.styles) is None for e in candidates):
                continue
            proposals.append({e.source_index for e in candidates})
    owners = {}
    for members in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    return {index for members in proposals if all(owners[i] == 1 for i in members)
            for index in members}


def _prove_full_line_fragment_copies(full: Event, group: list[Event],
                                     visible_map: dict[int,str], removed: set[int]) -> FullLineCopyProof | None:
    """Prove a complete spatial row and select its foreground columns without changing ownership."""
    norm = lambda value: "".join(value.split()).casefold()
    shadow_only = (full.state.get('1a',0) >= 254 and
                   full.state.get('3a',0) >= 254 and
                   full.state.get('4a',0) < 254 and
                   full.state.get('borderstyle',1) == 1 and
                   not full.state.get('p',0) and
                   not inline_layout_key(full) and
                   not any(k in full.state for k in ('clip','iclip','org')) and
                   unrotated_text_state(full.state) and
                   any(abs(full.state.get(k,full.state.get('shad',0))) > 0
                       for k in ('xshad','yshad')))
    full_length = len(norm(visible_map[full.source_index]))
    fx = [e for e in group if e is not full and e.source_index not in removed
          and 0 < len(norm(visible_map[e.source_index])) < full_length
          # Longer word/syllable copies need matching font geometry
          # and placement as well as the complete-row text proof below.
          and (len(visible_map[e.source_index]) <= 4 or
               (text_layout_key(e) == text_layout_key(full) and
                placement_key(e) == placement_key(full) and
                not e.state.get('p',0) and not inline_layout_key(e) and
                not any(k in e.state for k in ('clip','iclip','org')) and
                unrotated_text_state(e.state)))
          and abs(get_pos(e.text)[1]-get_pos(full.text)[1]) <= .1*text_height(full)]
    if shadow_only:
        # A complete shadow backing supplies authored text and its
        # exact caption anchor. Four opaque, equally timed fragments
        # with identical font/layout can prove its foreground without
        # requiring duplicate effect layers for every syllable.
        fx = [e for e in fx if e.state.get('1a',0) == 0 and
              text_layout_key(e) == text_layout_key(full) and
              placement_key(e) == placement_key(full)]
    if len(fx) < (4 if shadow_only else 8):
        return None
    columns: list[list[Event]] = []
    for e in sorted(fx,key=lambda e:get_pos(e.text)[0]):
        if columns and abs(get_pos(e.text)[0]-get_pos(columns[-1][0].text)[0]) <= .06*text_height(full):
            columns[-1].append(e)
        else:
            columns.append([e])
    if len(columns) < 4 or any(len({visible_map[e.source_index] for e in col}) != 1
                               for col in columns):
        return None
    assembled = "".join(visible_map[col[0].source_index] for col in columns)
    matches = (''.join(assembled.split()) == ''.join(visible_map[full.source_index].split())
               if shadow_only else norm(assembled) == norm(visible_map[full.source_index]))
    if not matches:
        return None
    xs = [get_pos(col[0].text)[0] for col in columns]
    if not min(xs) <= get_pos(full.text)[0] <= max(xs):
        return None
    # The author's complete, spaced text is the canonical caption.
    # Standard simplification gives it one opaque fill and contour instead of
    # translucent backing paint plus dozens of animated letters.
    ordered = [max(col,key=lambda e:(int(e.layer) if e.layer.lstrip('-').isdigit() else 0,
                                     e.source_index)) for col in columns]
    return FullLineCopyProof(ordered,fx,assembled,shadow_only)


def _render_proven_full_line_caption(full: Event, proof: FullLineCopyProof,
                                   visible_map: dict[int,str]) -> str | None:
    """Recover proved foreground paint while preserving authored text, placement and tracking spans."""
    ordered,assembled,shadow_only = proof.ordered,proof.assembled,proof.shadow_only
    prefix_end = re.match(r'(?:\{[^}]*\})*',full.text).end()
    tracking_tokens = [token for block in OVERRIDE_RE.findall(full.text[prefix_end:])
                       for token in tokenize_override(block)]
    tracking_only = (bool(tracking_tokens) and
        all(k == 'fsp' and re.fullmatch(NUM,v) and math.isfinite(float(v))
            for k,v in tracking_tokens) and
        len({tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
            ('1c','3c','b','i','u','s')) for e in ordered}) == 1)
    def paint_layout(e):
        return tuple((k,v) for k,v in text_layout_key(e)
                     if not tracking_only or k != 'fsp')
    # A nearly invisible full-line scaffold can carry the literal text
    # while its already-matched opaque letters carry the actual paint.
    # Reuse those colours only after the existing ownership proof, with
    # identical literal characters and font/layout/placement evidence.
    fragment_paint = shadow_only or (
        full.state.get('1a',0) >= 254 and full.state.get('3a',0) >= 254 and
        (not inline_layout_key(full) or tracking_only) and
        not any(k in full.state for k in ('clip','iclip','org')) and
        unrotated_text_state(full.state) and
        ''.join(assembled.split()) == ''.join(visible_map[full.source_index].split()) and
        all(e.state.get('1a',0) == 0 and
            paint_layout(e) == paint_layout(full) and
            (placement_key(e)[:3] == placement_key(full)[:3] if tracking_only else
             placement_key(e) == placement_key(full)) and
            not inline_layout_key(e) and
            not any(k in e.state for k in ('clip','iclip','org')) for e in ordered))
    if fragment_paint:
        body = render_merged_caption(ordered,
            [visible_map[e.source_index] for e in ordered],visible_map[full.source_index],
            animated=True,an=int(full.state.get('an',5)),pos=get_pos(full.text),
            fscx=full.state.get('fscx',100),fscy=full.state.get('fscy',100))
        if body is None:
            return None
        if tracking_only:
            # Authored spacing remains authoritative. Uniform proved
            # foreground paint can replace the scaffold header while
            # retaining its literal text and tracking spans exactly.
            body = body[:body.index('}')+1]+full.text[prefix_end:]
        if 'q' in full.state:
            body = '{'+render_tag('q',full.state['q'])+'}'+body
    else:
        body = render_simplified_caption(full.state,visible_map[full.source_index],measurement=full.measurement,
                                         source_paint=_source_caption_paint(full.state,[full.state]))
    return body


def remove_letters_over_full_lines(
    events: list[Event], visible_map: dict[int, str], source_events: dict[int, Event] | None=None,
    *, collect_rows: bool=False, font_metrics: FontMetrics | None=None,
) -> FullLineCopyResult:
    """Use retained full lines or word fragments over proven letter copies.

    Match complete text and placement, using either equal timing or paired
    entrance/exit rows. Near-coextensive full-line and word-fragment copies
    additionally require exact-font glyph positions. Nearby letters alone never prove
    caption ownership. Complete shadow backings can supply authored text and
    its anchor, while matching opaque fragments supply foreground paint.
    Opt into row collection to return additions for reconstruction and run
    authored-source matching. Source caches are returned as explicit updates.
    """
    removed = match_nested_glyph_copies(events,visible_map,font_metrics)
    removed.update(match_staggered_full_line_copies(events,visible_map,font_metrics))
    replacements: dict[int,Event] = {}
    row_additions: list[TextRow] = []
    source_updates: dict[int,Event] = {}
    if source_events is not None and collect_rows:
        authored = match_authored_lyric_rows(events,visible_map,source_events)
        removed.update(authored.removed_sources)
        row_additions.extend(authored.row_additions)
        source_updates = authored.source_updates
        if source_updates:
            successors = {id(source_events[index]):event for index,event in source_updates.items()}
            events = [successors.get(id(e),e) for e in events]
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.kind == "Dialogue" and get_pos(e.text) is not None and visible_map.get(e.source_index):
            groups.setdefault((e.style,e.name,e.start,e.end,e.row,
                               e.margin_l,e.margin_r,e.margin_v),[]).append(e)
    for group in groups.values():
        full_lines = [e for e in group if len(visible_map[e.source_index]) >= 8
                      and len(visible_map[e.source_index].split()) >= 2]
        for full in full_lines:
            if full.source_index in removed:
                continue
            proof = _prove_full_line_fragment_copies(full,group,visible_map,removed)
            if proof is None:
                continue
            body = _render_proven_full_line_caption(full,proof,visible_map)
            if body is None:
                continue
            replacements[full.source_index] = replace_event(
                full, text=body,
                layer="0", effect="")
            if collect_rows:
                row_additions.append(TextRow(replacements[full.source_index],
                    [(e,visible_map[e.source_index],get_pos(e.text)) for e in proof.ordered]))
            removed.update(e.source_index for e in proof.fragments)
    return FullLineCopyResult([replacements.get(e.source_index,e) for e in events
            if e.source_index not in removed],len(removed),row_additions,source_updates)


# Exact-font row recovery and anchor fitting.
# These algorithms borrow events/formatting and return geometry only. The
# caller decides rendering, timing and ownership. Metrics owns reusable font
# caches; the optional report belongs to the caller, including failed proofs.

@dataclass
class FontProcessingReport:
    """Caller-owned diagnostics accumulated during font-backed processing.

    rows_joined counts accepted measured joins at their commit sites, not
    removed events or attempted fits. missing_families is deliberately
    selective: spacing/fullwidth recovery and vector-outline fitting record
    unavailable exact faces; ordinary measurement/anchor checks stay silent.
    Share one report across a batch to accumulate completed work, including
    work before a later conversion failure. A fresh report isolates a run.
    """
    rows_joined: int = 0
    missing_families: set[str] = field(default_factory=set)


def recover_font_row(
    metrics: FontMetrics, ordered, fragments, *, max_size_error: float | None=None,
    allow_internal_spaces: bool=False, font_report: FontProcessingReport | None=None,
    fit_scale: bool=False,
):
    if not metrics.available or len(ordered) < 4:
        return None
    import unicodedata
    if any(not t or t != t.strip() or any((c.isspace() and not
           (allow_internal_spaces and c == ' ')) or
           unicodedata.bidirectional(c) in {'R','AL','AN'} or
           unicodedata.combining(c) for c in t) for t in fragments):
        return None
    first = ordered[0].state
    identity = ('fn','fs','b','i','fsp','an')
    if any(any(e.state.get(k) != first.get(k) for k in identity) or
           any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay'))
           for e in ordered):
        return None
    family = str(first.get('fn','')).strip()
    key = (family.casefold(), first.get('b',0), bool(first.get('i',0)))
    face = metrics.matching_face(family, key[1], key[2])
    if face is None:
        if font_report is not None:
            font_report.missing_families.add(family)
        return None
    cmap = face.cmap
    if any(ord(c) not in cmap for c in ''.join(fragments)+' '):
        return None
    try:
        kerning = bool(first.get("kerning",False))
        sx = statistics.median(e.state.get('fscx',100) for e in ordered)
        sy = statistics.median(e.state.get('fscy',100) for e in ordered)
        if sx <= 0 or sy <= 0:
            return None
        scale = first.get('fs',20)*sx/100/1024
        spacing = first.get('fsp',0)*sx/100
        # Nonzero authored tracking has differing renderer conventions.
        if abs(spacing) > .001:
            return None
        widths = [metrics.measure(face,t,kerning)*scale for t in fragments]
        space = metrics.measure(face,' ',kerning)*scale
    except (OSError, ValueError, RuntimeError):
        return None
    if space <= 0:
        return None
    alignment = int(first.get('an',5))
    if alignment not in range(1,10):
        return None
    anchor = ((alignment-1)%3)/2
    xs = [get_pos(e.text)[0] for e in ordered]
    deltas = [b-a for a,b in zip(xs,xs[1:])]
    base = [(1-anchor)*a+anchor*b for a,b in zip(widths,widths[1:])]
    # ASS font size conventions differ from Pillow's em size. Calibrate
    # one common multiplier for the row, checking every boundary against
    # an integral number of measured spaces. Ambiguous fits stay positioned.
    fits, unbroken_fits = {}, {}
    for distance, advance in zip(deltas,base):
        for bit in (0,1):
            factor = distance/(advance+bit*space)
            if not .5 <= factor <= 1.5:
                continue
            for _ in range(3):
                bits = tuple(max(0,math.floor((distance-factor*advance)/(factor*space)+.5))
                             for distance,advance in zip(deltas,base))
                predicted = [advance+bit*space for advance,bit in zip(base,bits)]
                factor = sum(a*b for a,b in zip(predicted,deltas))/sum(a*a for a in predicted)
            if (not .5 <= factor <= 1.5 or
                    sum(bits) > sum(map(len,fragments))
                    or (any(bits) and 0 in bits and bits.count(0)<2 and len(bits)<4)):
                continue
            errors = [abs(actual-factor*expected)/(factor*space)
                      for actual,expected in zip(deltas,predicted)]
            # Up to one script pixel of coordinate rounding is tolerated.
            if max(errors) > .22 + min(.12,1/(factor*space)):
                continue
            score = sum(e*e for e in errors)/len(errors)
            destination = fits if any(bits) and 0 in bits else unbroken_fits
            if bits not in destination or score < destination[bits][0]:
                destination[bits] = (score,factor)
    # Preserve established mixed-space recovery. When it has no fit,
    # try an unbroken run, retaining entirely spaced alternatives as
    # ambiguity evidence (especially for equal-width fonts).
    candidates = fits or unbroken_fits
    if not candidates:
        return None
    ranked = sorted(candidates.items(),key=lambda pair:pair[1][0])
    if len(ranked)>1 and ranked[1][1][0]-ranked[0][1][0] < .02:
        return None
    bits, (_,factor) = ranked[0]
    if max_size_error is not None:
        nominal = metrics.ass_em_scale(face)
        if nominal is None or abs(factor-nominal) > max_size_error*nominal:
            return None
    # Entirely spaced rows cannot calibrate a no-space reference. Keep
    # them as ambiguity evidence, but only emit mixed or unbroken fits.
    if 0 not in bits:
        return None
    text = fragments[0]+''.join(' '*bit+t for bit,t in zip(bits,fragments[1:]))
    # A merged font may kern across the old fragment seams. Reject a large
    # difference between the assembled advance and the measured row span.
    span = factor*(sum(widths)+sum(bits)*space)
    try:
        if abs(metrics.measure(face,text,kerning)*scale*factor-span) > max(1,.2*factor*space):
            return None
    except (OSError,ValueError,RuntimeError):
        return None
    center = (xs[0]-anchor*widths[0]*factor +
              xs[-1]+(1-anchor)*widths[-1]*factor)/2
    if fit_scale:
        nominal = metrics.ass_em_scale(face)
        if nominal is None:
            return None
        sx *= factor/nominal
    return text, center, sx, sy, ((alignment-1)//3)*3+2


def recover_tracked_font_row(
    metrics: FontMetrics, ordered, fragments, *, font_report: FontProcessingReport | None=None,
):
    """Recover a tracked single-glyph row without rescaling its glyphs.

    Reuse spacing recovery for the literal text, then fit only one tracking
    value against exact ASS font metrics. Every original anchor must fit
    within a bounded tolerance relative to glyph advance. Shaping across
    former glyph seams must preserve the separate advances.
    """
    # Brief bursts can belong to entrance/exit effects, rather than a held
    # line. Leave them to the existing effect-removal passes.
    if (not ordered or any(e.duration <= .25 for e in ordered) or
            any(len(t) != 1 for t in fragments)):
        return None
    state = ordered[0].state
    spacing = state.get('fsp',0)
    if not math.isfinite(spacing) or abs(spacing) <= .001:
        return None
    fit = recover_font_row(metrics,[dataclass_replace(e,state={**e.state,'fsp':0})
                        for e in ordered],fragments,font_report=font_report)
    if fit is None:
        return None
    text,_,sx,sy,alignment = fit
    if any(any(e.state.get(k) != state.get(k)
               for k in ('fn','fs','b','i','fsp','an','fscx','fscy'))
           for e in ordered):
        return None
    face = metrics.matching_face(str(state.get('fn','')),state.get('b',0),
                              bool(state.get('i',0)))
    factor = metrics.ass_em_scale(face) if face is not None else None
    if factor is None:
        return None
    scale = state.get('fs',20)*sx/100/1024*factor
    kerning = bool(state.get('kerning',False))
    try:
        widths = [metrics.measure(face,c,kerning,ligatures=False)*scale for c in text]
        full = metrics.measure(face,text,kerning,ligatures=False)*scale
    except (OSError,ValueError,RuntimeError):
        return None
    if abs(full-sum(widths)) > 1:
        return None
    anchor = ((int(state.get('an',5))-1)%3)/2
    indices = [i for i,c in enumerate(text) if not c.isspace()]
    xs = [get_pos(e.text)[0] for e in ordered]
    prefix = [0.0]
    for width in widths:
        prefix.append(prefix[-1]+width)
    residuals = [x-prefix[i]-anchor*widths[i] for x,i in zip(xs,indices)]
    mean_i,mean_r = statistics.mean(indices),statistics.mean(residuals)
    denominator = sum((i-mean_i)**2 for i in indices)
    tracking = sum((i-mean_i)*(r-mean_r) for i,r in zip(indices,residuals))/denominator
    origin = mean_r-tracking*(mean_i+anchor)
    # Allow modest irregular spacing, measured in script pixels at the
    # rendered glyph size. Exclude word spaces from the typical advance.
    tolerance = min(5,max(1,.1*statistics.median(widths[i] for i in indices)))
    # Check every anchor against the completed row, so boundary errors
    # cannot accumulate. Keep the existing bound on fitted tracking.
    if (abs(tracking) > .1*state.get('fs',20)*sx/100 or
            abs(tracking) <= .001 or any(w+tracking <= 0 for w in widths) or
            max(abs(x-(origin+prefix[i]+anchor*widths[i]+
                       tracking*(i+anchor))) for x,i in zip(xs,indices)) > tolerance):
        return None
    center = origin+(full+len(text)*tracking)/2
    return text,center,sx,sy,alignment,tracking*100/sx


def fit_fullwidth_run(
    metrics: FontMetrics, ordered: list[Event], glyphs: list[str], *,
    font_report: FontProcessingReport | None=None,
):
    """Fit one unbroken row against its exact font's glyph advances."""
    if not metrics.available or len(ordered) < 2 or sum(map(len,glyphs)) < 3:
        return None
    state = ordered[0].state
    family = str(state.get("fn", "")).strip()
    key = (family.casefold(), state.get("b",0), bool(state.get("i",0)))
    face = metrics.matching_face(family, key[1], key[2])
    if face is None:
        if font_report is not None:
            font_report.missing_families.add(family)
        return None
    cmap = face.cmap
    if any(ord(g) not in cmap for fragment in glyphs for g in fragment):
        return None
    if any(any(e.state.get(k) != state.get(k)
               for k in ("fn","fs","fscx","fscy","an","b","i","fsp"))
           for e in ordered):
        return None
    fs, sx = state.get("fs",0), state.get("fscx",100)
    if fs <= 0 or sx <= 0:
        return None
    try:
        kerning = bool(state.get("kerning",False))
        text = "".join(glyphs)
        scale = fs*sx/100/1024
        widths = [metrics.measure(face,g,kerning)*scale for g in glyphs]
        offsets = [0]
        for fragment in glyphs:
            offsets.append(offsets[-1]+len(fragment))
        advances = [metrics.measure(face,text[:i],kerning)*scale for i in offsets]
    except (OSError,ValueError,RuntimeError):
        return None
    # Adjacent glyph positions are their own alignment anchors, not
    # necessarily their centres. Preserve the original glyph width.
    alignment = int(state.get("an",5))
    if alignment not in range(1,10):
        return None
    anchor = ((alignment-1)%3)/2
    model = [advance+anchor*width for advance,width in zip(advances,widths)]
    xs = [get_pos(e.text)[0] for e in ordered]
    model_delta = [b-a for a,b in zip(model,model[1:])]
    actual_delta = [b-a for a,b in zip(xs,xs[1:])]
    denominator = sum(v*v for v in model_delta)
    if denominator == 0:
        return None
    factor = sum(a*b for a,b in zip(model_delta,actual_delta))/denominator
    if not .85 <= factor <= 1.15:
        return None
    origin = statistics.mean(x-factor*advance for x,advance in zip(xs,model))
    if max(abs(x-(origin+factor*advance))
           for x,advance in zip(xs,model)) > max(1.25,.06*statistics.median(actual_delta)):
        return None
    return (origin+anchor*factor*advances[-1], sx*factor)


CAPTION_PAINT_TAGS = ('1c','2c','3c','4c','1a','2a','3a','4a',
                      'bord','xbord','ybord','shad','xshad','yshad','blur','be')


def render_caption_spans(header: str, fragments: list[str], text: str,
                         paints: list[dict], span_tags: tuple[str,...],
                         chosen: Event, *, exact: bool = False) -> str | None:
    """Attach selected span formatting to literal recovered characters.

    Callers choose the paint policy; this helper only maps fragments and emits
    state changes. Spaces belong to the recovered text, never to a word guess.
    Replay emitted tags so base border/shadow changes reset their axes exactly
    as the renderer does before comparing the next tag or fragment.
    Exact correspondence retains literal whitespace at its authored offsets;
    recovered glyph rows keep their existing whitespace-insensitive mapping.
    """
    norm = lambda value: ''.join(value.split())
    if len(fragments) != len(paints) or (text != ''.join(fragments) if exact else
                                       norm(text) != norm(''.join(fragments))):
        return None
    def value(state,tag):
        return state.get(tag,state.get(tag[1:],0) if tag in
                         {'xbord','ybord','xshad','yshad'} else DEFAULT_STATE.get(tag,0))
    evaluation = evaluate_effective_state(header,chosen.defaults,chosen.styles)
    live,continuation = evaluation.formatting,evaluation.continuation
    cursor,segments = 0,[]
    for fragment,paint in zip(fragments,paints):
        begin,remaining = cursor,len(norm(fragment))
        if exact:
            cursor+=len(fragment)
        else:
            while remaining and cursor < len(text):
                remaining -= not text[cursor].isspace()
                cursor += 1
        tags = ''
        for tag in span_tags:
            target = value(paint,tag)
            if value(live,tag) != target:
                rendered = render_tag(tag,target)
                tags += rendered
                continuation = apply_override(live,tag,rendered[len(tag)+1:],
                                              chosen.styles,chosen.defaults,continuation)
        segments.append(('{' + tags + '}' if tags else '')+text[begin:cursor])
    return header+''.join(segments)+text[cursor:]


def render_merged_caption(ordered: list[Event], fragments: list[str], text: str,
                          *, animated: bool, an: int, pos: tuple[float,float],
                          fscx: float, fscy: float, fsp: float | None = None,
                          preserve_paint: bool = False) -> str | None:
    """Render a validated row using its recovered text and placement.

    Animated rows use simplified fragment paint and decorations. Static rows
    use shared formatting, or exact per-fragment paint with preserve_paint.
    Return None if span formatting cannot map to the text.
    Spacing recovery, row eligibility and event updates belong to the caller.
    """
    alignment = an
    x,y = pos
    sx,sy = fscx,fscy
    chosen = ordered[0]
    paints = None
    span_tags = ()
    if animated:
        # Normalize geometry/effects, retaining each fragment's formatting.
        # Visibility changes also mark stable gradient glyphs as animated;
        # merging them must not spread the first glyph's fill over the row.
        body = render_simplified_caption(chosen.state,text,
                                  outline_states=[e.state for e in ordered],
                                  source_paint=_source_caption_paint(chosen.state,[e.state for e in ordered]),
                                  an=alignment,pos=(x,y),fscx=sx,fscy=sy,measurement=chosen.measurement)
        header = body[:body.index('}')+1]
        paints = [effective_state(render_simplified_caption(e.state,fragment,measurement=e.measurement,
                                          source_paint=_source_caption_paint(e.state,[e.state])),e.defaults,e.styles)
                  for e,fragment in zip(ordered,fragments)]
        span_tags = ('b','i','u','s','1c','3c','3a','bord','xbord','ybord')
        formatting = [tuple(paint.get(k,paint.get('bord',0) if k in {'xbord','ybord'} else DEFAULT_STATE.get(k))
                            for k in span_tags) for paint in paints]
        if len(set(formatting)) == 1:
            paints = None
    else:
        # Static callers prove a shared layout. Reuse the first fragment's
        # overrides for the header, and retain paint spans when requested.
        tags = "".join(OVERRIDE_RE.findall(chosen.text))
        tags = "".join("\\"+name+value for name,value in tokenize_override(tags)
                       if name not in {"pos","an","a","fscx","fscy"})
        header = "{"+tags+f"\\an{alignment}\\pos({x:g},{y:g})\\fscx{sx:g}\\fscy{sy:g}"+"}"
        if preserve_paint:
            paints = [e.state for e in ordered]
            span_tags = CAPTION_PAINT_TAGS
    if fsp is not None:
        # This is one proven positioned row, including when it is wider than
        # the canvas. Disable automatic wrapping and replace prior tracking.
        tags = ''.join('\\'+tag+value for tag,value in tokenize_override(header[1:-1])
                       if tag not in {'fsp','q'})
        header = '{'+tags+render_tag('fsp',fsp)+r'\q2}'
    if paints is not None:
        return render_caption_spans(header,fragments,text,paints,span_tags,chosen)
    return header+text


def merge_shared_interval_rows(
    events: list[Event], visible: Mapping[int, str], metric: FontMetrics | None,
    animated_sources: set[int], *, font_report: FontProcessingReport | None=None,
) -> SharedIntervalRowsResult:
    """Compact common visibility, then compact retained phase tails.

    Four rounds bound subdivision. Each round consumes a fragment at most
    once; no round can expand a glyph's original lifetime or alter its paint.
    Borrow visibility and expose pending rows/tails only through a local
    overlay. Return one sparse delta for the pipeline to apply after all rounds.
    """
    rows = tails = 0
    visibility_updates = {}
    pending_visibility = collections.ChainMap(visibility_updates,visible)
    eligible_sources = set(animated_sources)
    for _ in range(4):
        previous_ids = {e.source_index for e in events}
        events,count,retained = _merge_shared_interval_rows_once(
            events,pending_visibility,metric,eligible_sources, font_report=font_report)
        eligible_sources.update(e.source_index for e in events if e.source_index not in previous_ids)
        rows += count
        tails += retained
        if not count:
            break
    return SharedIntervalRowsResult(events,rows,tails,visibility_updates)


def _shared_interval_bounds(context: SharedIntervalContext, e: Event) -> tuple | None:
    """Cache original caption bounds, including every inline paint extent."""
    if e.source_index not in context.boxes:
        probe = e
        if inline_layout_key(e):
            prefix = re.match(r'(?:\{[^}]*\})*',e.text).end()
            suffix = e.text[prefix:]
            tokens = [token for block in OVERRIDE_RE.findall(suffix)
                      for token in tokenize_override(block)]
            if any(tag not in context.paint_tags for tag,value in tokens):
                context.boxes[e.source_index] = None
                return None
            evaluation = evaluate_effective_state(e.text[:prefix],e.defaults,e.styles)
            state,continuation = evaluation.formatting,evaluation.continuation
            states = [state.copy()]
            for tag,value in tokens:
                continuation = apply_override(state,tag,value,e.styles,e.defaults,continuation)
                states.append(state.copy())
            state = dict(e.state)
            for k in ('xbord','ybord','xshad','yshad'):
                state[k] = max(abs(p.get(k,p.get(k[1:],0))) for p in states)
            for k in ('blur','be'):
                state[k] = max(abs(p.get(k,0)) for p in states)
            # Replacing text reparses its formatting. Install the accumulated
            # source extents afterwards, or a narrow final span can erase the
            # larger border/shadow/blur footprint needed for compositing proof.
            probe = replace_event(e,text=e.text[:prefix]+OVERRIDE_RE.sub('',suffix))
            probe = replace_event(probe,state=state)
        box = caption_bounds(probe,context.metric)
        if box is not None:
            pad = 2*abs(probe.state.get('blur',0))+abs(probe.state.get('be',0))
            box = (box[0]-pad,box[1]-pad,box[2]+pad,box[3]+pad)
        context.boxes[e.source_index] = box
    return context.boxes[e.source_index]


def _prepare_shared_interval_context(
    events: list[Event], visible: MutableMapping[int, str], metric: FontMetrics, *,
    font_report: FontProcessingReport | None=None,
) -> SharedIntervalContext:
    """Index original file order and numeric layers once for this pass."""
    paint_tags = CAPTION_PAINT_TAGS
    boxes = {}
    order_index = {e.source_index:i for i,e in enumerate(events)}
    by_layer = {}
    for e in events:
        if e.kind == 'Dialogue' and e.layer.lstrip('-').isdigit():
            by_layer.setdefault(int(e.layer),[]).append(e)
    layer_indices = {}
    for layer,peers in by_layer.items():
        peers.sort(key=lambda e:order_index[e.source_index])
        layer_indices[layer] = [order_index[e.source_index] for e in peers]
    return SharedIntervalContext(visible,metric,paint_tags,boxes,order_index,by_layer,layer_indices, font_report=font_report)


def _group_shared_interval_candidates(context: SharedIntervalContext, events: list[Event], animated_sources: set[int]) -> dict[tuple,list[Event]]:
    """Group eligible frozen fragments by original layout and geometry."""
    buckets = {}
    for e in events:
        word = context.visible.get(e.source_index,'')
        if (e.kind != 'Dialogue' or not word or e.duration <= 0 or e.effect or
                not (e.lyric or e.source_index in animated_sources) or
                get_pos(e.text) is None or not e.layer.lstrip('-').isdigit() or e.state.get('p',0) or
                e.state.get('1a',0) != 0 or e.state.get('borderstyle',1) != 1 or
                any(k in e.state for k in ('clip','iclip','org')) or
                any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay')) or
                any(tag in e.text for tag in (r'\N',r'\n')) or
                OVERRIDE_RE.search(e.text,re.match(r'(?:\{[^}]*\})*',e.text).end()) or
                any(tag in {'t','move','fad','fade','k','kf','ko','kt'}
                    for tag,value in event_override_tokens(e))):
            continue
        key = (e.style,e.name,e.row,e.margin_l,e.margin_r,e.margin_v,
               tuple((k,v) for k,v in text_layout_key(e) if k != 'q'),
               state_key(e,{'pos','q',*context.paint_tags}))
        buckets.setdefault(key,[]).append(e)
    return buckets


def _shared_interval_row_bands(buckets: dict[tuple,list[Event]]) -> list[list[Event]]:
    """Separate candidate buckets into their original vertical bands."""
    bands = []
    for bucket in buckets.values():
        current = []
        for e in sorted(bucket,key=lambda p:get_pos(p.text)[1]):
            if current and get_pos(e.text)[1]-get_pos(current[0].text)[1] > .15*min(
                    text_height(e),min(text_height(p) for p in current)):
                bands.append(current)
                current = []
            current.append(e)
        bands.append(current)
    return bands


def _shared_interval_sweep_candidates(bucket: list[Event]) -> list[list[Event]]:
    """Collect shared-boundary and directional sweeps with complete common visibility."""
    boundaries = {}
    for e in bucket:
        boundaries.setdefault(('start',e.start),[]).append(e)
        boundaries.setdefault(('end',e.end),[]).append(e)
    candidates = list(boundaries.values())
    # Staggered glyph entrances/exits need not share an exact boundary.
    # Grow directional sweeps only while the entire run retains a common
    # interval; never chain pairwise overlaps into a lifetime union.
    for boundary in ('start_s','end_s'):
        for direction in (1,-1):
            run = []
            for e in sorted(bucket,key=lambda p:(getattr(p,boundary),direction*get_pos(p.text)[0])):
                if run and (direction*(get_pos(e.text)[0]-get_pos(run[-1].text)[0]) <= e.unit or
                            e.end_s < run[-1].end_s-.011 or
                            min(e.end_s,min(p.end_s for p in run))-
                            max(e.start_s,max(p.start_s for p in run)) < .04-1e-6):
                    candidates.append(run)
                    run = []
                run.append(e)
            candidates.append(run)
    return candidates


def _shared_interval_candidate_windows(peers: list[Event]) -> list[list[Event]]:
    """Include complete rows and bounded prefix/suffix windows around independently timed edges."""
    runs = split_positioned_row_runs(peers)
    # A missing or independently timed edge glyph must not prevent
    # a proven prefix/suffix from sharing its own common interval.
    windows = []
    for run in runs:
        windows.append(run)
        if len(run) <= 32:
            windows.extend(run[left:right] for left in range(len(run)-3)
                           for right in range(left+4,len(run)+1)
                           if left or right != len(run))
        elif len(run) <= 64:
            for size in range(4,len(run)):
                windows.extend((run[:size],run[-size:]))
    return windows


def _shared_interval_slot_constraints(context: SharedIntervalContext, ordered: list[Event], members: frozenset[int], start: float, end: float, member_boxes: list[tuple]) -> list[Event] | None:
    """Preserve each original overlap relation when selecting available row slots."""
    # Preserve every overlapping glyph's relation to outside
    # objects. Disjoint glyphs may safely move to another slot.
    # Retain all fragment tails on their own layers.
    interleaved = False
    low_order = min((int(e.layer),context.order_index[e.source_index]) for e in ordered)
    high_order = max((int(e.layer),context.order_index[e.source_index]) for e in ordered)
    floor,ceiling = None,None
    for layer,peers_on_layer in context.by_layer.items():
        if not low_order[0] <= layer <= high_order[0]:
            continue
        first = bisect_right(context.layer_indices[layer],low_order[1]) if layer == low_order[0] else 0
        last = bisect_left(context.layer_indices[layer],high_order[1]) if layer == high_order[0] else len(peers_on_layer)
        for peer in peers_on_layer[first:last]:
            if (peer.source_index in members or
                    min(peer.end_s,end) <= max(peer.start_s,start)):
                continue
            box = _shared_interval_bounds(context,peer)
            peer_order = (layer,context.order_index[peer.source_index])
            relations = {(int(piece.layer),context.order_index[piece.source_index]) < peer_order
                         for piece,member_box in zip(ordered,member_boxes)
                         if box is None or member_box[0] < box[2] and box[0] < member_box[2] and
                         member_box[1] < box[3] and box[1] < member_box[3]}
            if len(relations) > 1:
                interleaved = True
                break
            if relations == {True}:
                ceiling = min(ceiling,peer_order) if ceiling is not None else peer_order
            elif relations == {False}:
                floor = max(floor,peer_order) if floor is not None else peer_order
        if interleaved:
            break
    if interleaved:
        return None
    slots_in_order = sorted(ordered,key=lambda e:(int(e.layer),context.order_index[e.source_index]))
    valid_slots = [e for e in slots_in_order if
        (floor is None or (int(e.layer),context.order_index[e.source_index]) > floor) and
        (ceiling is None or (int(e.layer),context.order_index[e.source_index]) < ceiling)]
    if not valid_slots:
        return None
    return valid_slots


def _fit_shared_interval_caption(context: SharedIntervalContext, ordered: list[Event], ys: list[float]) -> tuple[str,str] | None:
    """Prove exact-font spacing and render the retained per-fragment paint."""
    fragments = [context.visible[e.source_index] for e in ordered]
    fit = (recover_tracked_font_row(context.metric, ordered,fragments, font_report=context.font_report)
           if abs(ordered[0].state.get('fsp',0)) > .001 else
           recover_font_row(context.metric, ordered,fragments,allow_internal_spaces=True,
                          max_size_error=.1, font_report=context.font_report))
    if fit is None:
        return None
    text,x,sx,sy,an = fit[:5]
    tracking = fit[5] if len(fit) > 5 else ordered[0].state.get('fsp',0)
    body = render_merged_caption(ordered,fragments,text,animated=False,
        an=an,pos=(x,statistics.median(ys)),fscx=sx,fscy=sy,fsp=tracking,
        preserve_paint=True)
    if body is None:
        return None
    return body,text


def _prove_shared_interval_candidate(context: SharedIntervalContext, ordered: list[Event], tested: set[frozenset[int]]) -> SharedIntervalProposal | None:
    """Prove common timing, geometry, compositing order and a readable caption once per member set."""
    if len(ordered) < 4:
        return None
    first_start = max(ordered,key=lambda e:e.start_s)
    first_end = min(ordered,key=lambda e:e.end_s)
    start,end = first_start.start_s,first_end.end_s
    if end-start < .04-1e-6:
        return None
    geometry = positioned_row_geometry(ordered)
    if geometry is None:
        return None
    xs,ys = geometry
    members = frozenset(e.source_index for e in ordered)
    if members in tested:
        return None
    tested.add(members)
    member_boxes = [_shared_interval_bounds(context,e) for e in ordered]
    if any(box is None for box in member_boxes):
        return None
    clearance = 2*max(e.unit for e in ordered)
    member_boxes = [(box[0]-clearance,box[1]-clearance,
                     box[2]+clearance,box[3]+clearance) for box in member_boxes]
    valid_slots = _shared_interval_slot_constraints(context,ordered,members,start,end,member_boxes)
    if valid_slots is None:
        return None
    fitted = _fit_shared_interval_caption(context,ordered,ys)
    if fitted is None:
        return None
    body,text = fitted
    return SharedIntervalProposal(members,ordered,first_start,first_end,body,text,valid_slots,member_boxes)


def _collect_shared_interval_proposals(context: SharedIntervalContext, bands: list[list[Event]]) -> dict[frozenset[int],SharedIntervalProposal]:
    """Collect proven candidates before resolving competing row placements."""
    proposals = {}
    tested = set()
    for bucket in bands:
        candidates = _shared_interval_sweep_candidates(bucket)
        for peers in candidates:
            windows = _shared_interval_candidate_windows(peers)
            for ordered in windows:
                proposal = _prove_shared_interval_candidate(context,ordered,tested)
                if proposal is not None:
                    proposals[proposal.members] = proposal
    return proposals


def _compatible_shared_interval_slots(context: SharedIntervalContext, proposal: SharedIntervalProposal, accepted: list[tuple]) -> list[Event]:
    """Recheck a proposed placement against every already accepted overlapping row."""
    ordered,member_boxes = proposal.ordered,proposal.member_boxes
    start,end = proposal.first_start.start_s,proposal.first_end.end_s
    valid_slots = proposal.valid_slots
    # Independently safe placements can cross after two rows both move.
    # Recheck each overlapping accepted row against the original glyph
    # orders, then select a slot satisfying both sets of constraints.
    for peers,peer_boxes,peer_start,peer_end,peer_order in accepted:
        if min(end,peer_end) <= max(start,peer_start):
            continue
        relations = {(int(piece.layer),context.order_index[piece.source_index]) <
                     (int(peer.layer),context.order_index[peer.source_index])
                     for piece,box in zip(ordered,member_boxes)
                     for peer,peer_box in zip(peers,peer_boxes)
                     if box[0] < peer_box[2] and peer_box[0] < box[2] and
                     box[1] < peer_box[3] and peer_box[1] < box[3]}
        if len(relations) > 1:
            valid_slots = []
            break
        if relations:
            before = next(iter(relations))
            valid_slots = [e for e in valid_slots if
                ((int(e.layer),context.order_index[e.source_index]) < peer_order) == before]
            if not valid_slots:
                break
    return valid_slots


def _preserve_shared_interval_fragment_tails(context: SharedIntervalContext, proposal: SharedIntervalProposal, edits: SharedIntervalEdits) -> None:
    """Keep both original fragment tails in their original slots with unique generated IDs."""
    ordered = proposal.ordered
    first_start,first_end = proposal.first_start,proposal.first_end
    start,end = first_start.start_s,first_end.end_s
    for piece in ordered:
        pieces = edits.slots.setdefault(piece.source_index,[])
        for before in (True,False):
            if before and piece.start_s < start or not before and piece.end_s > end:
                tail = replace_event(piece,source_index=edits.next_index,
                    **({'end':first_start.start,'end_s':start} if before else
                       {'start':first_end.end,'start_s':end}))
                edits.next_index += 1
                context.visible[tail.source_index] = context.visible[piece.source_index]
                pieces.append(tail)
                edits.tails += 1


def _apply_shared_interval_proposal(context: SharedIntervalContext, proposal: SharedIntervalProposal, valid_slots: list[Event], edits: SharedIntervalEdits) -> None:
    """Place one readable row, retain its tails and record the accepted original ordering."""
    ordered,members = proposal.ordered,proposal.members
    member_boxes = proposal.member_boxes
    first_start,first_end = proposal.first_start,proposal.first_end
    start,end = first_start.start_s,first_end.end_s
    body,text = proposal.body,proposal.text
    slot_piece = valid_slots[0]
    row = replace_event(ordered[0],source_index=edits.next_index,text=body,effect='',
        layer=slot_piece.layer,
        start=first_start.start,start_s=start,end=first_end.end,end_s=end)
    edits.next_index += 1
    context.visible[row.source_index] = text
    slot = slot_piece.source_index
    edits.slots[slot] = [row]
    _preserve_shared_interval_fragment_tails(context,proposal,edits)
    edits.claimed.update(members)
    edits.accepted.append((ordered,member_boxes,start,end,
                     (int(slot_piece.layer),context.order_index[slot_piece.source_index])))
    edits.rows += 1


def _apply_shared_interval_proposals(context: SharedIntervalContext, events: list[Event], proposals: dict[frozenset[int],SharedIntervalProposal]) -> tuple[list[Event],int,int]:
    """Rank proposals by saved overlap, claim members once and apply compatible rows in original slots."""
    edits = SharedIntervalEdits(max((e.source_index for e in events),default=-1)+1)
    for members,proposal in sorted(proposals.items(),key=lambda item:
            (-(len(item[0])-1)*(item[1].first_end.end_s-item[1].first_start.start_s),min(item[0]))):
        if edits.claimed & members:
            continue
        valid_slots = _compatible_shared_interval_slots(context,proposal,edits.accepted)
        if not valid_slots:
            continue
        _apply_shared_interval_proposal(context,proposal,valid_slots,edits)
    if not edits.rows:
        return events,0,0
    # Place rows/tails at their original event slots to preserve layer order.
    output = [piece for e in events for piece in edits.slots.get(e.source_index,[e])]
    return output,edits.rows,edits.tails


def _merge_shared_interval_rows_once(
    events: list[Event], visible: MutableMapping[int, str], metric: FontMetrics | None,
    animated_sources: set[int], *, font_report: FontProcessingReport | None=None,
) -> tuple[list[Event], int, int]:
    """Compact frozen rows inside common visibility, retaining all glyph tails.

    Shared boundaries or directional sweeps supply phase boundaries; exact-font measurements
    must prove the row. Never expand visibility, select new paint or geometry,
    or run source-dependent effect removal on the resulting time slices.
    Each original event is consumed at most once. Four fragments and 40 ms
    of shared visibility bound subdivision of short, low-benefit candidates.
    The outer pass supplies its owned writable overlay for generated text.
    """
    if metric is None or not metric.available:
        return events,0,0
    context = _prepare_shared_interval_context(events,visible,metric, font_report=font_report)
    buckets = _group_shared_interval_candidates(context,events,animated_sources)
    bands = _shared_interval_row_bands(buckets)
    proposals = _collect_shared_interval_proposals(context,bands)
    return _apply_shared_interval_proposals(context,events,proposals)


def _translated_layout_key(e: Event) -> tuple:
    """Match paragraph geometry while allowing scale and shear animation."""
    return (e.style,placement_key(e),tuple((k,v) for k,v in text_layout_key(e)
            if k not in {'fscx','fscy','fax','fay'}))


def _match_touching_phase_fragments(
    peers: list[Event], target: Event, poses: dict[int, tuple[float, float]],
    words: dict[int, str], metric: FontMetrics,
) -> list[tuple[list[Event], float]]:
    """Measure complete touching fragments at the target baseline in the exact font."""
    peers = sorted(peers,key=lambda e:poses[e.source_index][0])
    spans = index_fragment_spans(words[e.source_index] for e in peers)
    output = []
    for a,b in matching_fragment_spans(spans,words[target.source_index]):
        row = peers[a:b+1]
        if (len({state_key(p,{'pos'}) for p in row}) != 1 or
                any(abs(poses[p.source_index][1]-poses[target.source_index][1]) > .001 for p in row)):
            continue
        anchor = fit_fragment_anchor(metric, row[0].state,[poses[p.source_index][0] for p in row],
            [words[p.source_index] for p in row],words[target.source_index],target.unit,
            separate_glyphs=all(len(words[p.source_index]) == 1 for p in row),max_size_error=.1)
        if anchor is not None:
            output.append((row,anchor))
    return output


def _collect_translated_motion_profiles(
    events: list[Event], visible: Mapping[int, str], metric: FontMetrics, cue_styles: set[str],
) -> list[tuple]:
    """Find uniquely owned before/movement/after phases proving horizontal translation."""
    keys, poses, words, begins, ends, eligible = {}, {}, {}, {}, {}, []
    for e in events:
        word, pos = visible.get(e.source_index,''), get_pos(e.text)
        if (e.kind != 'Dialogue' or e.style not in cue_styles or not word or pos is None or e.duration <= 0 or
                any(c.isspace() for c in word) or inline_layout_key(e) or
                not opaque_text_effect_state(e.state) or not unrotated_text_state(e.state) or
                static_object_key(e,e.styles) is None):
            continue
        key = _translated_layout_key(e)
        keys[e.source_index], poses[e.source_index], words[e.source_index] = key,pos,word
        eligible.append(e)
        if not any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay')):
            begins.setdefault((key,round(e.start_s,2)),[]).append(e)
            ends.setdefault((key,round(e.end_s,2)),[]).append(e)
    proposals = []
    for e in eligible:
        key, pos = keys[e.source_index],poses[e.source_index]
        left = _match_touching_phase_fragments(ends.get((key,round(e.start_s,2)),[]),e,poses,words,metric)
        right = _match_touching_phase_fragments(begins.get((key,round(e.end_s,2)),[]),e,poses,words,metric)
        options = []
        for before,bx in left:
            for after,ax in right:
                delta = ax-bx
                if (state_key(before[0],{'pos'}) != state_key(after[0],{'pos'}) or
                        abs(delta) <= e.unit or not min(ax,bx)-e.unit <= pos[0] <= max(ax,bx)+e.unit):
                    continue
                if (len(before) == len(after) and any(
                        abs(poses[b.source_index][0]-poses[a.source_index][0]-delta) > 1.5*e.unit
                        for a,b in zip(before,after))):
                    continue
                options.append((before,after,delta))
        if len(options) == 1:
            before,after,delta = options[0]
            ids = {e.source_index}|{p.source_index for p in before+after}
            proposals.append((ids,after,e,before,delta))
    claims = {}
    for ids,after,e,before,delta in proposals:
        for index in ids:
            claims[index] = claims.get(index,0)+1
    return [p for p in proposals if all(claims[index] == 1 for index in p[0])]


def _prepare_translated_phases(
    events: list[Event], visible: Mapping[int, str], metric: FontMetrics, cues: list[Event], *,
    font_report: FontProcessingReport | None=None,
) -> TranslatedPhaseContext:
    """Collect original movement profiles and the eligible static phase pool once."""
    cue_styles = {e.style for e in cues}
    allids = {e.source_index:e for e in events}
    profiles = _collect_translated_motion_profiles(events,visible,metric,cue_styles)
    pool = {}
    for e in events:
        w = visible.get(e.source_index, '')
        p = get_pos(e.text)
        if (e.kind == 'Dialogue' and e.style in cue_styles and w and p and (e.duration > 0)
            and (not inline_layout_key(e)) and (static_object_key(e, e.styles) is not None)
            and unrotated_text_state(e.state) and (not any((k in e.state for k in ['clip', 'iclip', 'org'])))):
            pool.setdefault(e.style, []).append(e)
    return TranslatedPhaseContext(visible,metric,profiles,pool,allids, font_report=font_report)


def _select_translated_cue_layout(
    context: TranslatedPhaseContext, cue: Event,
) -> TranslatedCueLayout | None:
    """Select the authored row and its measured translation or held-text baseline."""
    text = simplify_text(cue.text, visible_only=True)[1]
    if len(''.join(text.split())) < 4 or cue.duration <= 0:
        return None
    # Scale lead-in/tail allowances with the cue, not a fixed time limit.
    window = 0.25 * cue.duration
    seeds = [p for p in context.profiles if p[2].style == cue.style and cue.start_s - 0.011 <= p[2].start_s
        and (p[2].end_s <= cue.end_s + 0.011)]
    if seeds:
        k = _translated_layout_key(seeds[0][3][0])
        delta = statistics.median((p[4] for p in seeds))
        if any((_translated_layout_key(p[3][0]) != k or abs(p[4] - delta) > p[2].unit + 0.1 * text_height(p[2]) for p in seeds)):
            return None
        sample = seeds[0][3][0]
        y = get_pos(sample.text)[1]
    else:
        options = [e for e in context.pool.get(cue.style, []) if opaque_text_effect_state(e.state)
            and e.start_s <= cue.start_s + window and (e.end_s >= cue.end_s - window)
            and (e.duration >= 0.5 * cue.duration) and (not any((abs(e.state.get(k, 0)) > 0.001 for k in ['fax',
            'fay'])))]
        if not options:
            return None
        sample = max(options, key=lambda e: e.duration)
        k = _translated_layout_key(sample)
        delta = 0
        y = get_pos(sample.text)[1]
    positions = authored_glyph_positions(context.metric, sample.state, text, 0, sample.unit)
    if not positions:
        return None
    return TranslatedCueLayout(cue,text,window,seeds,sample,k,delta,y,positions)


def _fit_translated_cue_model(
    context: TranslatedPhaseContext, layout: TranslatedCueLayout,
) -> TranslatedCueModel | None:
    """Require one complete authored glyph model, then create its cue-local span cache."""
    candidates = [e for e in context.pool.get(layout.cue.style, []) if _translated_layout_key(e) == layout.key
        and layout.cue.start_s - layout.window - 0.001 <= e.start_s <= layout.cue.start_s + layout.window + 0.001
        and (e.end_s <= layout.cue.end_s + layout.window + 0.001)
        and (abs(get_pos(e.text)[1] - layout.y) <= 0.25 * text_height(layout.sample)) and (not any((abs(e.state.get(k,
        0)) > 0.001 for k in ['fax', 'fay']))) and (e.state.get('fscx') == layout.sample.state.get('fscx'))
        and (e.state.get('fscy') == layout.sample.state.get('fscy')) and (e.state.get('1c') == layout.sample.state.get('1c'))]
    # Full font geometry must account for every authored nonspace glyph.
    first = [e for e in candidates if context.visible[e.source_index] == layout.positions[0][0]]
    models = {}
    glyph_spans = index_fragment_spans(c for c,x in layout.positions)
    for e in first:
        center = get_pos(e.text)[0] - layout.positions[0][1]
        matches = [[p for p in candidates if context.visible[p.source_index] == char
            and abs(get_pos(p.text)[0] - (center + offset)) <= 1.5 * layout.sample.unit] for char, offset in layout.positions]
        for ids, new, phase, before, d in layout.seeds:
            for b in before:
                word = context.visible[b.source_index]
                if len(word) <= 1:
                    continue
                for a, z in matching_fragment_spans(glyph_spans, word):
                    gp = authored_glyph_positions(context.metric, layout.sample.state, word, 0, layout.sample.unit)
                    if (gp
                        and abs(get_pos(b.text)[0] - (center + layout.positions[a][1] - gp[0][1])) <= layout.sample.unit + 0.1 * text_height(layout.sample)):
                        for i in range(a, z + 1):
                            matches[i].append(b)
        if any((not m for m in matches)):
            continue
        if (layout.seeds and any((not all((any((p.source_index == b.source_index for m in matches for p in m))
            for b in before)) for ids, new, p, before, d in layout.seeds))):
            continue
        models[round(center, 1)] = (center, matches)
    if len(models) != 1:
        return None
    center, matches = next(iter(models.values()))
    xs = [center + x for c, x in layout.positions]
    initial_start = (min([b.start_s for ids, new, phase, before, d in layout.seeds for b in before] + [p.start_s
        for group in matches for p in group if (p.end_s > layout.cue.start_s + 0.011 or abs(p.end_s-layout.cue.start_s) < .001)
        and abs(get_pos(p.text)[1] - layout.y) <= layout.sample.unit and (state_key(p, {'pos'}) == state_key(layout.sample, {'pos'}))],
        default=layout.cue.start_s))
    spans = glyph_spans
    return TranslatedCueModel(layout,center,xs,initial_start,spans)


def _translated_span_options(
    context: TranslatedPhaseContext, model: TranslatedCueModel,
    e: Event, dx: float = 0, travel: bool = False,
) -> list[tuple[int,int]]:
    """Cache exact occurrence/anchor matches within one authored cue only."""
    layout = model.layout
    key = (e.source_index,dx,travel)
    if key in model.span_cache:
        return model.span_cache[key]
    word = context.visible[e.source_index]
    poss = []
    for a, b in matching_fragment_spans(model.spans, ''.join(word.split())):
        anchor = (fit_fragment_anchor(context.metric, layout.sample.state, model.xs[a:b + 1], [c for c, x in layout.positions[a:b + 1]], word,
            layout.sample.unit) if not any((c.isspace() for c in word)) else None)
        if anchor is None:
            if any((c.isspace() for c in word)):
                g = authored_glyph_positions(context.metric, layout.sample.state, word, 0, layout.sample.unit)
                if g and len(g) == b - a + 1:
                    anchor = model.xs[a] - g[0][1]
                if (anchor is not None and (not matches_authored_glyph_positions(context.metric, layout.sample.state,
                    model.xs[a:b + 1], word, anchor, layout.sample.unit))):
                    anchor = None
        if anchor is not None:
            px, py = get_pos(e.text)
            if (min(anchor, anchor + dx) - layout.sample.unit <= px <= max(anchor, anchor + dx) + layout.sample.unit
                if travel else abs(px - anchor - dx) <= layout.sample.unit + 0.1 * text_height(layout.sample)):
                poss.append((a, b))
    model.span_cache[key] = poss
    return poss


def _translated_held_spans(
    context: TranslatedPhaseContext, model: TranslatedCueModel, e: Event,
    before_ids: set[int], after_ids: set[int], effect_ends: dict[float,list[Event]],
) -> set[tuple[int,int]] | None:
    """Match held text; None rejects the entire event before other phase fallbacks."""
    layout = model.layout
    oldopts = _translated_span_options(context,model,e)
    newopts = _translated_span_options(context,model,e, layout.delta)
    if e.source_index in after_ids:
        opts = set(newopts)
    elif e.source_index in before_ids:
        opts = set(oldopts)
    elif e.end_s < layout.cue.end_s - layout.window:
        if layout.seeds and e.start_s < model.initial_start - 0.011:
            return None
        opts = set(oldopts)
    elif e.start_s >= layout.cue.start_s + layout.window:
        opts = set(newopts)
    else:
        opts = set(oldopts + newopts)
    if len(opts) == 1 and e.start_s >= layout.cue.end_s and e.source_index not in after_ids:
        # A late held tail needs its own touching effect phase.
        # The next cue's entrance cannot be backing for this row.
        opts = {span for span in opts if any(
            abs(p.end_s-e.start_s) <= .001 and any(
                max(span[0],ab[0]) <= min(span[1],ab[1])
                for ab in _translated_span_options(context,model,p,layout.delta,True))
            for p in effect_ends.get(round(e.start_s,2),[]))}
    return opts


def _translated_entrance_spans(
    context: TranslatedPhaseContext, model: TranslatedCueModel, e: Event, px: float,
) -> list[tuple[int,int]]:
    """Match entrance text, recovering recorded glyph anchors for a misread prefix."""
    layout = model.layout
    opts = _translated_span_options(context,model,e)
    if not opts:
        # A prior simplification may have mistaken a narrow
        # letter for a space in an entrance prefix. Match every
        # rendered glyph to the complete row instead of trusting
        # that partial transcript. Missing held glyphs still
        # reject the whole cue below.
        recorded = authored_glyph_positions(context.metric, 
            e.state,context.visible[e.source_index],px,e.unit)
        owners = [[i for i,(c,x) in enumerate(zip(
            [c for c,x in layout.positions],model.xs)) if c == char and
            abs(x-gx) <= layout.sample.unit+.2*text_height(layout.sample)]
            for char,gx in (recorded or [])]
        if (len(owners) >= 4 and all(len(indices) == 1 for indices in owners) and
                all(a[0] < b[0] for a,b in zip(owners,owners[1:]))):
            opts = [(owners[0][0],owners[-1][0])]
    return opts


def _covered_translated_pulses(
    context: TranslatedPhaseContext, model: TranslatedCueModel,
    stable: list[tuple[Event,tuple[int,int]]],
    pulses: list[tuple[Event,list[tuple[int,int]]]],
) -> list[tuple[Event,tuple[int,int]]]:
    """Prove moving pulses against touching or already-held translated backing."""
    layout = model.layout
    # An earlier merge may already hold a whole phrase over a later
    # syllable pulse. Its measured translated span proves that pulse too;
    # do not require the held event to begin again at every word boundary.
    covered_pulses = []
    for e,options in pulses:
        covered = [span for span in options if all(
            any(a <= i <= b and p.start_s <= e.end_s+.001 and p.end_s > e.end_s+.011 and
                (a,b) in _translated_span_options(context,model,p,layout.delta) for p,(a,b) in stable)
            for i in range(span[0],span[1]+1))]
        # Repeated words can have overlapping travel segments. Their
        # exact occurrence is immaterial when the complete held caption
        # already contains every candidate; ownership is still cue-wide.
        if covered:
            covered_pulses.append((e,covered[0]))
    return covered_pulses


def _classify_translated_cue_phases(
    context: TranslatedPhaseContext, model: TranslatedCueModel,
) -> TranslatedCuePhases:
    """Match held text, then entrances, then movement effects in their original order."""
    layout = model.layout
    before_ids = {p.source_index for ids,after,phase,before,d in layout.seeds for p in before}
    after_ids = {p.source_index for ids,after,phase,before,d in layout.seeds for p in after}
    effect_ends = {}
    for p in context.pool.get(layout.cue.style,[]):
        changing = (any(abs(p.state.get(q,0)) > .001 for q in ('fax','fay')) or
                    any(p.state.get(q) != layout.sample.state.get(q) for q in ('fscx','fscy')))
        if (_translated_layout_key(p) == layout.key and changing and opaque_text_effect_state(p.state) and
                layout.cue.start_s-.011 <= p.start_s < layout.cue.end_s and
                abs(get_pos(p.text)[1]-layout.y) <= layout.sample.unit):
            effect_ends.setdefault(round(p.end_s,2),[]).append(p)
    stable = []
    entrances = []
    pulses = []
    for e in context.pool.get(layout.cue.style, []):
        if (_translated_layout_key(e) != layout.key or e.start_s < layout.cue.start_s - layout.window - 0.001 or e.end_s > layout.cue.end_s + layout.window + 0.001
            or (e.start_s >= layout.cue.end_s + layout.window) or (e.end_s <= layout.cue.start_s - layout.window)):
            continue
        w = context.visible[e.source_index]
        px, py = get_pos(e.text)
        flat = (not any((abs(e.state.get(q, 0)) > 0.001 for q in ['fax', 'fay']))
            and all((e.state.get(q) == layout.sample.state.get(q) for q in ['fscx', 'fscy'])))
        if flat and state_key(e, {'pos'}) == state_key(layout.sample, {'pos'}) and (abs(py - layout.y) <= layout.sample.unit):
            opts = _translated_held_spans(context,model,e,before_ids,after_ids,effect_ends)
            if opts is None:
                continue
            if len(opts) == 1:
                stable.append((e, next(iter(opts))))
                continue
        if (flat and e.duration <= layout.window + 0.001 and (e.start_s <= layout.cue.start_s + layout.window)
            and (e.end_s <= layout.cue.start_s + layout.window) and (abs(py - layout.y) <= 0.25 * text_height(layout.sample))
            and (e.state.get('1c') == layout.sample.state.get('1c'))):
            opts = _translated_entrance_spans(context,model,e,px)
            if len(opts) == 1:
                entrances.append((e, opts[0]))
                continue
        if (layout.delta and not flat and opaque_text_effect_state(e.state) and abs(py - layout.y) <= layout.sample.unit
            and (layout.cue.start_s - 0.011 <= e.start_s) and e.start_s < layout.cue.end_s
            and (e.end_s <= layout.cue.end_s + layout.window + 0.001)):
            pulses.append((e,_translated_span_options(context,model,e,layout.delta,True)))
    pulses = _covered_translated_pulses(context,model,stable,pulses)
    return TranslatedCuePhases(stable,entrances,pulses)


def _prove_translated_cue_coverage(
    context: TranslatedPhaseContext, model: TranslatedCueModel, phases: TranslatedCuePhases,
) -> tuple[set[int],list[Event]] | None:
    """Require complete animation and held backing with no competing persistent text."""
    layout = model.layout
    if any((not any((a <= i <= b for e, (a, b) in phases.stable)) for i in range(len(layout.positions)))):
        return None
    # Static matching fragments alone do not prove an animation.
    changed = {ab for e, ab in phases.entrances if abs(get_pos(e.text)[1] - layout.y) > e.unit or e.state.get('1a', 0) > 0}
    if not layout.seeds and len(changed) < 4:
        return None
    if layout.seeds and len(layout.seeds) < 2 and (len(phases.pulses) < 3 or
            sum(len(context.visible[e.source_index]) > 1 for e,span in phases.pulses) < 2):
        return None
    # Every glyph needs completed held backing, not only an early fragment.
    if any(not any(a <= i <= b and p.end_s >= layout.cue.end_s-layout.window and
                   (a,b) in _translated_span_options(context,model,p,layout.delta) for p,(a,b) in phases.stable)
           for i in range(len(layout.positions))):
        return None
    members = [e for e, span in phases.stable + phases.entrances + phases.pulses]
    ids = {e.source_index for e in members}
    if layout.seeds:
        ids.update((i for pi, new, e, before, d in layout.seeds for i in pi))
        members = [context.allids[i] for i in ids]
    blockers = [e for e in context.pool.get(layout.cue.style, []) if _translated_layout_key(e) == layout.key and e.source_index not in ids
        and (layout.cue.start_s - 0.011 <= e.start_s < layout.cue.end_s) and (min(e.end_s, layout.cue.end_s) - max(e.start_s,
        layout.cue.start_s) >= 0.5 * min(e.duration, layout.cue.duration)) and (e.duration >= layout.window)
        and (abs(get_pos(e.text)[1] - layout.y) <= 0.25 * text_height(layout.sample))
        and (model.xs[0] - text_height(layout.sample) <= get_pos(e.text)[0] <= model.xs[-1] + text_height(layout.sample))]
    if blockers:
        return None
    return ids,members


def _render_translated_cue_proposal(
    model: TranslatedCueModel, ids: set[int], members: list[Event],
) -> tuple[set[int],TextRow,str] | None:
    """Use the shared renderer and retain complete glyph anchors for overlap proofs."""
    layout = model.layout
    body = render_merged_caption([layout.sample],[layout.text],layout.text,animated=False,
        an=int(layout.sample.state.get('an',5)),pos=(model.center+layout.delta,layout.y),
        fscx=layout.sample.state.get('fscx',100),fscy=layout.sample.state.get('fscy',100),
        fsp=layout.sample.state.get('fsp',0))
    if body is None:
        return None
    start = min((e.start_s for e in members))
    end = max((e.end_s for e in members))
    base = min(members, key=lambda e: e.source_index)
    caption = (replace_event(base, layer=layout.sample.layer, text=body, start=format_time(start), start_s=start,
        end=format_time(end), end_s=end))
    core = (layout.cue.start_s,layout.cue.end_s) if start < layout.cue.start_s < layout.cue.end_s < end else None
    # Supply the verified glyph anchors even when an earlier pass already
    # combined the held backing into one event. Its center alone is not
    # the row's horizontal extent for the shared overlap pass.
    pieces = [(replace_event(layout.sample,text=render_simplified_caption(
        {**layout.sample.state,'pos':(x+layout.delta,layout.y)},char,measurement=layout.sample.measurement,
        source_paint=_source_caption_paint(layout.sample.state,[layout.sample.state]))),char,(x+layout.delta,layout.y))
        for (char,offset),x in zip(layout.positions,model.xs)]
    row = TextRow(caption,pieces,phase_core=core)
    return ids,row,layout.text


def _apply_translated_cue_proposals(
    events: list[Event], context: TranslatedPhaseContext,
    proposals: list[tuple[set[int],TextRow,str]],
) -> TextPhaseRowsResult:
    """Resolve ownership across complete cues before consuming any source events."""
    # Resolve ownership across complete cues, never greedily by event order.
    claims = collections.Counter((i for ids, e, t in proposals for i in ids))
    accepted = [p for p in proposals if all((claims[i] == 1 for i in p[0]))]
    ids = set().union(*(p[0] for p in accepted)) if accepted else set()
    out = [e for e in events if e.source_index not in ids]+[row.base for ids,row,t in accepted]
    visibility_updates = {}
    for ids,row,t in accepted:
        visibility_updates[row.base.source_index] = t
        if context.font_report is not None:
            context.font_report.rows_joined += 1
    return TextPhaseRowsResult(sorted(out,key=lambda e:e.source_index),
        len(events)-len(out),[row for ids,row,t in accepted],visibility_updates)


def collapse_translated_phase_rows(
    events: list[Event], visible: Mapping[int, str], metric: FontMetrics | None, *,
    font_report: FontProcessingReport | None=None,
) -> TextPhaseRowsResult:
    """Flatten complete authored rows with measured entrance/translation phases.

    Touching before/after fragments prove a shared horizontal translation.
    The exact font and authored spaces must account for every glyph in the
    initial row and its held backing. Short bounce/fade phases may then vary
    in paint and grouping; moving syllables need a touching held successor.
    Without translation, at least four changing entrance fragments are needed.
    Missing text, competing persistent neighbors or shared ownership reject
    the cue. Neither actor names nor fixed effect timings/coordinates matter.
    Return protected rows and sparse visibility updates without modifying
    the input map; the pipeline applies them before subsequent consumers.
    """
    if metric is None or not getattr(metric,'available',False):
        return TextPhaseRowsResult(events,0,[],{})
    cues = [e for e in events if e.kind == 'Comment' and e.duration > 0]
    if not cues:
        return TextPhaseRowsResult(events,0,[],{})
    context = _prepare_translated_phases(events,visible,metric,cues, font_report=font_report)
    proposals = []
    for cue in cues:
        layout = _select_translated_cue_layout(context,cue)
        if layout is None:
            continue
        model = _fit_translated_cue_model(context,layout)
        if model is None:
            continue
        phases = _classify_translated_cue_phases(context,model)
        coverage = _prove_translated_cue_coverage(context,model,phases)
        if coverage is None:
            continue
        ids,members = coverage
        proposal = _render_translated_cue_proposal(model,ids,members)
        if proposal is not None:
            proposals.append(proposal)
    return _apply_translated_cue_proposals(events,context,proposals)


def _index_fragment_phase_rows(
    events: list[Event], visible_map: Mapping[int, str], metric: FontMetrics, *,
    font_report: FontProcessingReport | None=None,
) -> FragmentPhaseContext:
    """Index eligible stationary fragments and exact touching phase boundaries."""
    eligible, words, geometry, positions = [], {}, {}, {}
    for e in events:
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or not word or pos is None or e.duration <= 0 or
                any(c.isspace() or unicodedata.combining(c) or
                    unicodedata.bidirectional(c) in {'R','AL','AN'} for c in word) or
                inline_layout_key(e) or not opaque_text_effect_state(e.state) or
                not unrotated_text_state(e.state) or
                static_object_key(e,e.styles) is None):
            continue
        # Vertical exit compression does not change horizontal glyph anchors.
        # A matched earlier completed phase supplies its readable height.
        key = (e.style,placement_key(e),tuple((k,v) for k,v in text_layout_key(e)
                                             if k != 'fscy'),round(pos[1],4))
        eligible.append(e)
        words[e.source_index],geometry[e.source_index],positions[e.source_index] = word,key,pos
    endings, anchored_starts, anchored_ends = {}, {}, {}
    for e in eligible:
        key = geometry[e.source_index]
        endings.setdefault((key,round(e.end_s,2)),[]).append(e)
        anchor = (key,positions[e.source_index],words[e.source_index])
        anchored_starts.setdefault((*anchor,round(e.start_s,2)),[]).append(e)
        anchored_ends.setdefault((*anchor,round(e.end_s,2)),[]).append(e)
    for group in endings.values():
        group.sort(key=lambda e:positions[e.source_index][0])
    # Lookup is local to a centisecond phase boundary, rather than comparing
    # every event with every other event in a font/row family.
    return FragmentPhaseContext(eligible,words,geometry,positions,
                                endings,anchored_starts,anchored_ends,metric, font_report=font_report)


def _previous_fragment_phases(context: FragmentPhaseContext, e: Event) -> list[Event]:
    """Find same-word and same-anchor predecessors at an exact phase boundary."""
    key = (context.geometry[e.source_index],context.positions[e.source_index],context.words[e.source_index],round(e.start_s,2))
    return [p for p in context.anchored_ends.get(key,[])
            if abs(p.end_s-e.start_s) <= .001]


def _match_fragment_phase_join(context: FragmentPhaseContext, tail: Event,
                                current: Event) -> list[list[Event]]:
    """Prove fragment joins using literal order, compatible paint and exact-font anchors."""
    word = context.words[tail.source_index]
    peers = (context.endings.get((context.geometry[tail.source_index],round(current.start_s,2)),[])
             if len(word) > 1 else [])
    matches = []
    for offset,p in enumerate(peers):
        if not word.startswith(context.words[p.source_index]):
            continue
        pieces, text = [],''
        for index in range(offset,len(peers)):
            p = peers[index]
            if abs(p.end_s-current.start_s) > .001:
                break
            pieces.append(p)
            text += context.words[p.source_index]
            if not word.startswith(text):
                break
            if text == word:
                xs = [context.positions[p.source_index][0] for p in pieces]
                if len(pieces) > 1 and (any(b <= a for a,b in zip(xs,xs[1:])) or
                        len({state_key(p,{'pos'}) for p in pieces}) != 1):
                    break
                anchor = fit_fragment_anchor(context.metric, tail.state,xs,
                    [context.words[p.source_index] for p in pieces],word,tail.unit,exact_size=True)
                if anchor is not None and abs(anchor-context.positions[tail.source_index][0]) <= .25*tail.unit:
                    matches.append(pieces)
                break
    return matches


def _prove_fragment_phase_chain(context: FragmentPhaseContext, tail: Event) -> FragmentPhaseProfile | None:
    """Require an unambiguous touching chain and restore its earlier readable height."""
    chain, current = [tail],tail
    while True:
        peers = _previous_fragment_phases(context,current)
        if not peers:
            break
        if len(peers) != 1:
            return None
        current = peers[0]
        chain.append(current)
    word = context.words[tail.source_index]
    matches = _match_fragment_phase_join(context,tail,current)
    if len(matches) != 1:
        # Single-letter phases have already been traversed by _previous_fragment_phases().
        # They participate only alongside proven multi-fragment joins.
        if matches or len(word) != 1 or len(chain) < 2:
            return None
        pieces = [chain.pop()]
        current = chain[-1]
    else:
        pieces = matches[0]
    members = pieces+chain
    if (min(p.end_s for p in members)-max(p.start_s for p in pieces) <= .011 or
            any(p.source_index == q.source_index for i,p in enumerate(members) for q in members[:i])):
        return None
    tail = replace_event(tail,text=render_simplified_caption(
        {**tail.state,'fscy':current.state.get('fscy',100)},word,measurement=tail.measurement,
        source_paint=_source_caption_paint(tail.state,[tail.state])))
    return FragmentPhaseProfile(tail,members,min(p.start_s for p in pieces),current.start_s,
            tail.start_s,len(pieces) > 1)


def _collect_fragment_phase_families(context: FragmentPhaseContext) -> dict:
    """Group terminal phases by layout and paint, retaining failed proofs as blockers."""
    families = {}
    for e in context.eligible:
        paint = tuple(e.state.get(k,e.defaults.get(k,0)) for k in
                      ('1c','3c','4c','1a','3a','4a','bord','xbord','ybord',
                       'shad','xshad','yshad','blur','be'))
        key = (context.geometry[e.source_index],e.layer,paint)
        anchor = (context.geometry[e.source_index],context.positions[e.source_index],context.words[e.source_index],round(e.end_s,2))
        successors = [p for p in context.anchored_starts.get(anchor,[])
                      if abs(e.end_s-p.start_s) <= .001]
        if not successors:
            families.setdefault(key,[]).append((e,_prove_fragment_phase_chain(context,e)))
    return families


def _group_fragment_phase_cues(context: FragmentPhaseContext, family: list,
                                direction: int) -> list:
    """Split ordered activations by horizontal direction and shared lifetime."""
    sequence, cues = [],[]
    for e,p in sorted(family,key=lambda pair:((pair[1].activation_s if pair[1] else pair[0].start_s),
                                            direction*context.positions[pair[0].source_index][0])):
        start = p.start_s if p else e.start_s
        if sequence and (direction*(context.positions[e.source_index][0]-context.positions[sequence[-1][0].source_index][0]) <= e.unit or
                         start >= min(q.end_s for q,_ in sequence)-.011):
            cues.append(sequence);sequence=[]
        sequence.append((e,p))
    cues.append(sequence)
    return cues


def _fit_fragment_phase_cue(context: FragmentPhaseContext, cue: list) -> tuple | None:
    """Fit only complete ordered rows and preserve their protected activation core."""
    if len(cue) < 4 or any(p is None for e,p in cue) or sum(p.joined_fragments for e,p in cue) < 2:
        return None
    if (any(b[1].activation_s <= a[1].activation_s+.011 or b[1].terminal_start_s < a[1].terminal_start_s-.011
            for a,b in zip(cue,cue[1:])) or
            any(b[0].end_s < a[0].end_s-.011 for a,b in zip(cue,cue[1:]))):
        return None
    held = sorted((p.caption_sample for e,p in cue),key=lambda e:context.positions[e.source_index][0])
    if len({state_key(e,{'pos'}) for e in held}) != 1:
        return None
    fragments = [context.words[e.source_index] for e in held]
    fit = recover_font_row(context.metric, held,fragments, font_report=context.font_report)
    if fit is None:
        return None
    text,x,sx,sy,an = fit
    body = render_merged_caption(held,fragments,text,animated=False,an=an,
        pos=(x,statistics.median(context.positions[e.source_index][1] for e in held)),fscx=sx,fscy=sy)
    if body is None:
        return None
    ids = frozenset(m.source_index for e,p in cue for m in p.members)
    if len(ids) != sum(len(p.members) for e,p in cue):
        return None
    start,end = min(p.start_s for e,p in cue),max(e.end_s for e,p in cue)
    core = (min(p.activation_s for e,p in cue),max(p.activation_s for e,p in cue))
    if not start < core[0] < core[1] < end:
        return None
    first = min(held,key=lambda e:e.source_index)
    caption = replace_event(first,text=body,start=format_time(start),start_s=start,
        end=format_time(end),end_s=end,source_index=min(ids))
    row = TextRow(caption,[(e,context.words[e.source_index],context.positions[e.source_index]) for e in held],
                  phase_core=core)
    return ids,row,text


def _propose_fragment_phase_rows(context: FragmentPhaseContext, families: dict) -> list:
    """Build all row proposals before missing-fragment and ownership checks."""
    proposals = []
    for family in families.values():
        if sum(p is not None and p.joined_fragments for e,p in family) < 2:
            continue
        for direction in (1,-1):
            for cue in _group_fragment_phase_cues(context,family,direction):
                proposal = _fit_fragment_phase_cue(context,cue)
                if proposal is not None:
                    proposals.append(proposal)
    return proposals


def _filter_incomplete_fragment_rows(context: FragmentPhaseContext, proposals: list) -> list:
    """Reject rows with unmatched nearby fragments before resolving source ownership."""
    # An unmatched nearby fragment may be a missing part of this cue. Do not
    # turn a failed boundary or font match into a partial reconstructed line.
    # Other complete proposals are known neighbouring cues, not missing text.
    proposed_ids = set().union(*(ids for ids,row,text in proposals)) if proposals else set()
    blockers = {}
    for e in context.eligible:
        if e.source_index not in proposed_ids:
            key = (e.style,placement_key(e),round(context.positions[e.source_index][1],4))
            blockers.setdefault(key,[]).append(e)
    complete = []
    for ids,row,text in proposals:
        e = row.pieces[0][0]
        key = (e.style,placement_key(e),round(row.pieces[0][2][1],4))
        xs = [pos[0] for piece,word,pos in row.pieces]
        start,end = row.phase_core
        reach = 2*min(text_height(piece) for piece,word,pos in row.pieces)
        if not any(min(xs)-reach <= context.positions[p.source_index][0] <= max(xs)+reach and
                   min(end,p.end_s)-max(start,p.start_s) >= .5*min(end-start,p.duration)
                   for p in blockers.get(key,[])):
            complete.append((ids,row,text))
    return complete


def _resolve_fragment_phase_ownership(complete: list) -> list:
    """Deduplicate equivalent claims and reject every competing source owner."""
    # A phase belongs to exactly one complete caption; no greedy ownership.
    unique = {ids:(row,text) for ids,row,text in complete}
    claims = {}
    for ids in unique:
        for index in ids:
            claims[index] = claims.get(index,0)+1
    accepted = [(ids,row,text) for ids,(row,text) in unique.items()
                if all(claims[index] == 1 for index in ids)]
    return accepted


def _apply_fragment_phase_rows(context: FragmentPhaseContext, events: list[Event],
                               accepted: list) -> TextPhaseRowsResult:
    """Return accepted rows and visibility; commit the explicit font counter."""
    consumed = set().union(*(ids for ids,row,text in accepted)) if accepted else set()
    rows = [row for ids,row,text in accepted]
    visibility_updates = {}
    for ids,row,text in accepted:
        visibility_updates[row.base.source_index] = text
        if context.font_report is not None:
            context.font_report.rows_joined += 1
    output = [e for e in events if e.source_index not in consumed]+[row.base for row in rows]
    return TextPhaseRowsResult(sorted(output,key=lambda e:e.source_index),
        len(events)-len(output),rows,visibility_updates)


def collapse_fragment_phase_rows(
    events: list[Event], visible_map: Mapping[int, str], metric: FontMetrics | None, *,
    font_report: FontProcessingReport | None=None,
) -> TextPhaseRowsResult:
    """Assemble rows whose touching phases change fragment granularity.

    Exact-font anchors connect smaller fragments to the same completed word
    or syllable. Any number of same-anchor phases may follow. Ordered word
    activation and a shared terminal paint prove a complete readable row;
    event names, animation tags and particular colours are not evidence.
    Missing, competing or multiply claimed phases reject the whole cue.
    Borrow visibility and return accepted text updates with protected row
    evidence. The pipeline applies the updates before timing/reconstruction.
    """
    if metric is None or not getattr(metric,'available',False):
        return TextPhaseRowsResult(events,0,[],{})
    context = _index_fragment_phase_rows(events,visible_map,metric, font_report=font_report)
    families = _collect_fragment_phase_families(context)
    proposals = _propose_fragment_phase_rows(context,families)
    complete = _filter_incomplete_fragment_rows(context,proposals)
    accepted = _resolve_fragment_phase_ownership(complete)
    return _apply_fragment_phase_rows(context,events,accepted)


_ROW_TIME_QUANTUM = .011  # ASS row timings have centisecond precision.


@dataclass(frozen=True)
class CaptionPhaseSource:
    """A borrowed source plus its static paint view and actual non-fading core."""
    source: Event
    settled: Event
    core: tuple[float,float]
    fade: tuple[float,float]


def _caption_phase_source(source: Event) -> CaptionPhaseSource | None:
    """Borrow readable static paint without stripping fades from working events.

    A simple global fade has one fixed resting appearance. Fade-only fragments
    remain candidates; the complete paint phase must supply a real readable
    hold before gaining authority. Independent opacity, karaoke and motion do not.
    The original record continues to own source pose and visibility evidence.
    """
    if _faded_cue_is_scrolling(source):return None
    tokens=event_override_tokens(source)
    fading=any(k in {'fad','fade'} for k,v in tokens)
    fade=_parse_simple_source_fade(tokens) if fading else (0.,0.)
    if fade is None:return None
    core=source.start_s+fade[0]/1000,source.end_s-fade[1]/1000
    if core[1]<core[0]-1e-6:return None
    text=OVERRIDE_RE.sub(lambda m:'{'+''.join('\\'+k+v for k,v in tokenize_override(m[1]) if k!='fad')+'}',source.text)
    settled=replace_event(source,text=text,effect='') if fading else dataclass_replace(source,effect='')
    if static_text_paint_geometry(settled,set(CAPTION_PAINT_TAGS)|{'alpha','c'}) is None:return None
    settled=dataclass_replace(settled,state=event_evaluation(settled).formatting)
    return CaptionPhaseSource(source,settled,core,tuple(fade))


def _caption_phase_runs(groups: list[list[CaptionPhaseSource]]) -> list[tuple]:
    """Keep authored adjacency/gaps; resolve only overlaps between readable cores."""
    runs=[];run=[];handoffs=[]
    for peers in sorted(groups,key=lambda ps:(ps[0].source.start_s,ps[0].source.end_s)):
        events=[p.settled for p in peers]
        if run:
            previous,previous_sources=run[-1]
            order=lambda p:(int(p.source.layer) if p.source.layer.lstrip('-').isdigit() else 0,p.source.source_index)
            left=max(previous_sources,key=order);right=max(peers,key=order)
            delta=events[0].start_s-previous[0].end_s
            cutoff=None
            if delta < -1e-6 and events[0].end_s>previous[0].end_s+1e-6:
                cutoff=_select_readable_core_handoff((previous[0].start_s,previous[0].end_s),
                    (events[0].start_s,events[0].end_s),left.core,right.core)
            if abs(delta)>.001 and cutoff is None:
                runs.append((run,tuple(handoffs)));run=[];handoffs=[]
            elif cutoff is not None:
                run[-1]=([replace_event(e,end=format_time(cutoff),end_s=cutoff) for e in previous],previous_sources)
                events=[replace_event(e,start=format_time(cutoff),start_s=cutoff) for e in events]
                handoffs.append(cutoff)
        run.append((events,peers))
    if run:runs.append((run,tuple(handoffs)))
    return runs


def _matching_caption_phase_opacity(left: CaptionPhaseSource, right: CaptionPhaseSource,
                                     start: float, end: float) -> bool:
    """Compare shared fade factors on each linear segment, not intrinsic alpha."""
    def factor(source,at):
        first,last=source.fade
        return max(0.,min(1.,(at-source.source.start_s)*1000/first if first else 1.,
                          (source.source.end_s-at)*1000/last if last else 1.))
    points={start,end,*[t for s in (left,right) for t in s.core if start<t<end]}
    return all(abs(factor(left,t)-factor(right,t))<1e-6 for t in points)


def _caption_phase_family_is_clear(planes: list[Event], interval: tuple[float,float],
                                    parsed: dict[int,Event], metric: FontMetrics | None) -> bool:
    """Reuse whole-line exact-font clearance after uniform glyph layout proof."""
    if metric is None or not metric.available or any(not e.layer.lstrip('-').isdigit() for e in planes):return False
    probe=min(planes,key=lambda e:int(e.layer))
    probe,available=_caption_implicit_anchor(probe)
    if probe is None:return False
    footprints=[dataclass_replace(e,state=states[0]) for e in planes
                for literal,states in _literal_paint_ranges([e])]
    state=probe.state.copy()
    for k in ('bord','xbord','ybord','blur','be'):
        state[k]=max(e.state.get(k,e.state.get('bord',0) if k.endswith('bord') else 0) for e in footprints)
    probe=dataclass_replace(probe,state=state,
        text='{'+render_tag('pos',get_pos(probe.text))+'}'+OVERRIDE_RE.sub('',probe.text))
    box=caption_bounds(probe,metric)
    if box is None or available is not None and box[2]-box[0]>available:return False
    return _glyph_replacement_row_is_clear(probe,interval,{e.source_index for e in planes},
        max(int(e.layer) for e in planes),parsed,metric,footprints)


@dataclass(frozen=True)
class CaptionPaintCompanion:
    """A source-proved outer contour whose color follows foreground fill.

    The fill beneath the opaque foreground can disappear in earlier sequence
    merging. Borrow its source exposure so one actual appearance supplies all
    paint. Contour width/opacity, blur and geometry stay with the retained plane.
    """
    owner: Event
    members: frozenset[int]
    fill_phases: tuple[tuple[float,float,tuple[tuple[str,float],...]],...]


@dataclass(frozen=True)
class CaptionPaintTimeline:
    """Producer-proved source paint, independent of later layout reconstruction.

    Phases contain one SourceCaptionPaint per non-space literal character.
    Sources retain original timing/paint; no rendered tag is used as authority.
    """
    owner: Event
    members: frozenset[int]
    literal: str
    phases: tuple[tuple[float,float,tuple[SourceCaptionPaint,...]],...]
    companions: tuple[CaptionPaintCompanion,...] = ()
    overlap_handoffs: tuple[float,...] = ()


def _near_caption_palette(a: tuple, b: tuple) -> bool:
    """Use the existing two-level, non-chaining RGB bound on corresponding paint."""
    return len(a)==len(b) and all(x.border==y.border and x.outline_alpha==y.outline_alpha and
        all(abs(int(c[i:i+2],16)-int(d[i:i+2],16))<=2
            for c,d in ((x.fill,y.fill),(x.outline,y.outline)) for i in (0,2,4)) for x,y in zip(a,b))


def _source_row_palette(row: TextRow, at: float) -> tuple | None:
    # Settling opacity proves a readable representative contour, but temporal
    # intent also needs source exposure at this phase. Decorative blurred planes
    # do not own the retained glyph/stroke; their opacity cannot veto that ink.
    sources={e.source_index:e for peers in row.paint_rows for e in peers}
    sources.update((e.source_index,e) for e in row.foreground)
    for source in sources.values():
        sampled=_source_palette_at(source,at)
        if sampled is None or not sampled[1] or source.state.get('blur',0) or source.state.get('be',0):continue
        evaluated,transforms,_,_=_freeze_inputs(''.join(OVERRIDE_RE.findall(source.text)),
            source.duration,source.defaults,source.defaults,source.styles)
        live=sample_transform_state(evaluated.formatting,transforms,(at-source.start_s)*1000,
            source.styles,source.defaults,continuation=evaluated.continuation).formatting
        if live.get('1a',0)!=0 or live.get('3a',0)!=0:return None
    result=_normalize_source_row_paint([e for e,_,_ in row.pieces],[row],
                                      palette_time=at,proof_required=True)
    if result is None:
        return None
    palette=[]
    for e,_,_ in sorted(result.rows[0].pieces,key=lambda item:item[2][0] if item[2] is not None else 0):
        ranges=_literal_paint_ranges([dataclass_replace(e,effect='')])
        if ranges is None:
            return None
        for literal,states in ranges:
            state=states[0]
            proof=_source_caption_paint(state,[state])
            if proof is None:return None
            palette.extend((char,proof) for char in literal if not char.isspace())
    return tuple(palette)


def _caption_paint_timeline(row: TextRow) -> CaptionPaintTimeline | None:
    sources={e.source_index:e for peers in row.paint_rows for e in peers}
    sources.update((e.source_index,e) for e in row.foreground)
    if not sources or row.base.duration<=0:
        return None
    visibility=_index_source_fragment_visibility(row)
    alternate=len(visibility)>1
    if alternate:
        # Only families accepted by the existing visibility/compositing producer
        # arrive here. Each phase may use a different complete fragmentation.
        intervals=sorted((a,b,peers) for profile,peers in visibility.items() for a,b in profile)
    else:
        points={row.base.start_s,row.base.end_s}
        for e in sources.values():
            points.update(parse_time(format_time(t)) for t in (_source_palette_boundaries(e) or ())
                          if row.base.start_s<t<row.base.end_s)
        if len(points)<3:return None
        points=sorted(points);intervals=[(a,b,row.paint_rows) for a,b in zip(points,points[1:])]
    phases=[];literal=None
    for a,b,peers in intervals:
        chosen=max(peers,key=lambda rr:(int(rr[0].layer) if rr[0].layer.lstrip('-').isdigit() else 0,len(rr)))
        phase_row=(dataclass_replace(row,base=chosen[0],pieces=[(e,OVERRIDE_RE.sub('',e.text),get_pos(e.text)) for e in chosen],
            paint_rows=peers,foreground=[e for rr in peers for e in rr]) if alternate else
            dataclass_replace(row,foreground=row.foreground or [e for rr in peers for e in rr]))
        sample=_source_row_palette(phase_row,(a+b)/2)
        if sample is None:return None
        text=''.join(char for char,paint in sample)
        if '\\' in text or literal is not None and text!=literal:return None
        literal=text;palette=tuple(paint for char,paint in sample)
        phases.append((a,b,palette))
    return _join_source_paint_phases(row.base,frozenset(sources),literal,phases)


def _join_source_paint_phases(owner: Event, members: frozenset[int], literal: str,
                              samples: list[tuple]) -> CaptionPaintTimeline | None:
    """Canonical complete palettes share synchronization and tiny-color policy."""
    phases=[]
    for a,b,palette in samples:
        if phases and _near_caption_palette(phases[-1][2],palette):
            phases[-1]=(phases[-1][0],b,phases[-1][2]);continue
        if phases:
            changed=sum(not _near_caption_palette((x,),(y,)) for x,y in zip(phases[-1][2],palette))
            if changed<math.ceil(.8*len(palette)):return None
        phases.append((a,b,palette))
    return CaptionPaintTimeline(owner,members,literal,tuple(phases)) if len(phases)>1 else None


def _collect_caption_paint_timelines(data: CollectedSourceText, families: list[TextRow],
                                     retained: list[Event], metric: FontMetrics | None) -> tuple:
    """Capture before representative row paint and alternating-source removal."""
    timelines=[];claimed=set()
    retained_by_id={e.source_index:e for e in retained}
    def clear(row):
        sources=[e for peers in row.paint_rows for e in peers]+row.foreground
        if any(not e.layer.lstrip('-').isdigit() for e in sources):return False
        low=min(int(e.layer) for e in sources);high=max(int(e.layer) for e in sources)
        members={e.source_index for e in sources}
        foreign=any(e.kind=='Dialogue' and e.source_index not in members and
            e.start_s<row.base.end_s and e.end_s>row.base.start_s and
            (not e.layer.lstrip('-').isdigit() or low<=int(e.layer)<=high)
            for e in retained)
        if not foreign or low==high:return True
        if metric is None or get_pos(row.base.text) is None:return False
        return all(_glyph_replacement_row_is_clear(dataclass_replace(e,layer=str(low)),
            (row.base.start_s,row.base.end_s),members,high,retained_by_id,metric,sources)
            for e,_,_ in row.pieces)
    accepted={row.base.source_index:row for row in families}
    for collected in data.rows:
        row=accepted.get(collected.base.source_index,collected)
        # A stable single-plane row can own an authored stroke too. Mixed
        # visibility still requires the existing complete alternation proof.
        alternate=len(_index_source_fragment_visibility(row))>1
        members={e.source_index for peers in row.paint_rows for e in peers}
        members.update(e.source_index for e in row.foreground)
        claimed.update(members)
        if alternate and row.base.source_index not in accepted:continue
        timeline=_caption_paint_timeline(row)
        if timeline is not None and clear(row):timelines.append(timeline)
    groups={}
    for e in data.events.values():
        if e.kind!='Dialogue' or e.source_index in claimed:
            continue
        if not _source_palette_boundaries(e):continue
        key=(e.start,e.end,e.style,e.name,e.margin_l,e.margin_r,e.margin_v,get_pos(e.text),data.words.get(e.source_index))
        groups.setdefault(key,[]).append(e)
    # Include static companion planes as well: a fill-only or outline-only step
    # still needs the same ownership proof on both sides of the transition.
    for e in data.events.values():
        if e.kind!='Dialogue' or e.source_index in claimed:continue
        key=(e.start,e.end,e.style,e.name,e.margin_l,e.margin_r,e.margin_v,get_pos(e.text),data.words.get(e.source_index))
        if key in groups and all(e.source_index!=p.source_index for p in groups[key]):groups[key].append(e)
    for group in groups.values():
        if any(e.source_index in claimed for e in group):continue
        top=max(group,key=lambda e:(int(e.layer) if e.layer.lstrip('-').isdigit() else 0,e.source_index))
        row=TextRow(top,[(top,OVERRIDE_RE.sub('',top.text),get_pos(top.text))],
                    paint_rows=[[e] for e in group],foreground=group)
        timeline=_caption_paint_timeline(row)
        if timeline is not None and clear(row):timelines.append(timeline)
    # Ordinary sequential static source captions are the serialized form of
    # the same whole-caption intent. Capture their existing disjoint intervals
    # before effect-sequence merging, so repeat conversion needs no marker/tag.
    static={};paint_tags=set(CAPTION_PAINT_TAGS)|{'alpha','c'}
    claimed.update(index for t in timelines for index in t.members)
    for e in data.events.values():
        if e.kind!='Dialogue' or e.source_index in claimed or e.duration<=0:continue
        phase_source=_caption_phase_source(e)
        if phase_source is None:continue
        profile=static_text_paint_geometry(phase_source.settled,paint_tags)
        key=(e.style,e.name,e.margin_l,e.margin_r,e.margin_v,profile[0])
        static.setdefault(key,{}).setdefault((e.start_s,e.end_s),[]).append(phase_source)
    for intervals in static.values():
        for run,handoffs in _caption_phase_runs(list(intervals.values())):
            if len(run)<2:continue
            samples=[];literal=None;members=set();first=None;readable=[]
            for peers,sources in run:
                e=max(peers,key=lambda p:(int(p.layer) if p.layer.lstrip('-').isdigit() else 0,p.source_index))
                row=TextRow(e,[(e,OVERRIDE_RE.sub('',e.text),get_pos(e.text))],paint_rows=[[p] for p in peers],foreground=peers)
                if not clear(row):break
                sample=_source_row_palette(row,(e.start_s+e.end_s)/2)
                if sample is None:break
                first=first or e;members.update(p.source_index for p in peers)
                origin=next(p for p in sources if p.source.source_index==e.source_index)
                readable.append((max(e.start_s,origin.core[0]),min(e.end_s,origin.core[1])))
                literal=''.join(c for c,p in sample)
                samples.append((e.start_s,e.end_s,tuple(p for c,p in sample)))
            if len(samples)!=len(run) or not literal or '\\' in literal:continue
            owner=replace_event(first,end=run[-1][0][0].end,end_s=run[-1][0][0].end_s)
            faded=any(any(p.fade) for peers,sources in run for p in sources)
            if (handoffs or faded) and (len(static_text_paint_geometry(first,paint_tags)[0])!=1 or not _caption_phase_family_is_clear(
                    [e for peers,sources in run for e in peers],(owner.start_s,owner.end_s),retained_by_id,metric)):continue
            timeline=_join_source_paint_phases(owner,frozenset(members),literal,samples)
            if timeline is not None and faded and any(not any(min(b,end)>max(a,start)+1e-6
                    for start,end in readable) for a,b,palette in timeline.phases):continue
            if timeline is not None:timelines.append(dataclass_replace(timeline,overlap_handoffs=handoffs))
    return _attach_caption_paint_companions(tuple(timelines),retained,metric)


def _attach_caption_paint_companions(timelines: tuple, events: list[Event],
                                      metric: FontMetrics | None) -> tuple:
    """Extend source ownership to synchronized outer contours, across styles.

    Whole static caption planes share exact literal geometry, continuous cue
    coverage and foreground-fill/outer-contour colors at every source boundary.
    Independent opacity, stroke, layout or color changes confer no ownership.
    The existing clearance proof protects interleaved content. No styles or
    particular colors identify a glow; blurred and sharp outer planes qualify.
    """
    if not timelines or metric is None or not metric.available:return timelines
    paint=set(CAPTION_PAINT_TAGS)|{'alpha','c'}
    literals={t.literal for t in timelines}
    profiles={};groups={};phase_sources={};by_id={e.source_index:e for e in events}
    original_by_id=by_id.copy()
    for e in events:
        if e.kind!='Dialogue' or ''.join(OVERRIDE_RE.sub('',e.text).split()) not in literals:continue
        phase_source=_caption_phase_source(e)
        if phase_source is None:continue
        phase_sources[e.source_index]=phase_source
        e=phase_source.settled
        profile=static_text_paint_geometry(e,paint)
        if profile is None or not e.layer.lstrip('-').isdigit():continue
        profiles[e.source_index]=profile[0]
        key=(profile[0],e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement)
        groups.setdefault(key,{}).setdefault((e.style,e.layer),[]).append(phase_source)
    for family in groups.values():
        for key,sources in family.items():
            normalized=[e for run,handoffs in _caption_phase_runs([[p] for p in sources])
                        for peers,originals in run for e in peers]
            family[key]=normalized
            by_id.update((e.source_index,e) for e in normalized)
    proposals=[]
    for timeline in timelines:
        owner=timeline.owner
        if any(i not in profiles for i in timeline.members):continue
        front=[by_id[i] for i in timeline.members
               if by_id[i].style==owner.style and by_id[i].layer==owner.layer]
        if not front:continue
        front.sort(key=lambda e:e.start_s)
        if (abs(front[0].start_s-owner.start_s)>1e-6 or abs(front[-1].end_s-owner.end_s)>1e-6 or
                any(abs(a.end_s-b.start_s)>1e-6 for a,b in zip(front,front[1:]))):continue
        shape=profiles[front[0].source_index]
        if len(shape)!=1 or any(profiles[e.source_index]!=shape for e in front):continue
        key=(shape,owner.name,owner.margin_l,owner.margin_r,owner.margin_v,owner.measurement)
        for group in groups.get(key,{}).values():
            back=sorted([e for e in group if e.start_s<owner.end_s and e.end_s>owner.start_s],key=lambda e:e.start_s)
            if not back or any(e.source_index in timeline.members and e.layer==owner.layer for e in back):continue
            if (abs(back[0].start_s-owner.start_s)>1e-6 or abs(back[-1].end_s-owner.end_s)>1e-6 or
                    any(abs(a.end_s-b.start_s)>1e-6 for a,b in zip(back,back[1:]))):continue
            low=int(back[0].layer);high=min(int(e.layer) for e in front)
            if low>=high:continue
            points=sorted({owner.start_s,owner.end_s,*[t for e in front+back for t in (e.start_s,e.end_s)],
                           *[t for a,b,p in timeline.phases for t in (a,b)]})
            signature=None;fill_exposure={};fill_phases=[];valid=True
            for a,b in zip(points,points[1:]):
                at=(a+b)/2
                fs=[e for e in front if e.start_s<=at<e.end_s]
                bs=[e for e in back if e.start_s<=at<e.end_s]
                if len(fs)!=1 or len(bs)!=1:valid=False;break
                if not _matching_caption_phase_opacity(phase_sources[fs[0].source_index],
                        phase_sources[bs[0].source_index],a,b):valid=False;break
                ranges=_literal_paint_ranges([fs[0],bs[0]])
                if ranges is None:valid=False;break
                current=[];exposure=[]
                for literal,(f,g) in ranges:
                    fw=tuple(f.get(k,f.get('bord',0)) for k in ('xbord','ybord'))
                    gw=tuple(g.get(k,g.get('bord',0)) for k in ('xbord','ybord'))
                    if (any(k in st for st in (f,g) for k in ('clip','iclip')) or
                            any(st.get(k,st.get('shad',0)) for st in (f,g) for k in ('xshad','yshad')) or
                            f.get('1a',0)!=0 or f.get('3a',0)!=0 or f.get('blur',0) or f.get('be',0) or
                            not 0<=g.get('3a',0)<255 or max(gw)<=0 or
                            any(x<y for x,y in zip(gw,fw)) or
                            not (gw!=fw or g.get('blur',0)>0 or g.get('be',0)>0) or
                            any(abs(int(f['1c'][i:i+2],16)-int(g['3c'][i:i+2],16))>2 for i in (0,2,4))):
                        valid=False;break
                    current.extend((g.get('3a',0),gw,g.get('blur',0),g.get('be',0),g['1c']) for c in literal if not c.isspace())
                    exposure.extend((g['1c'],g.get('1a',0)) for c in literal if not c.isspace())
                if not valid or signature is not None and signature!=current:valid=False;break
                signature=current
                phase=next(i for i,(start,end,palette) in enumerate(timeline.phases) if start<=at<end)
                if phase in fill_exposure and fill_exposure[phase]!=exposure:valid=False;break
                fill_exposure[phase]=exposure
                fill_phases.append((a,b,tuple(exposure)))
            if not valid:continue
            if not _caption_phase_family_is_clear(front+back,(owner.start_s,owner.end_s),original_by_id,metric):continue
            proposals.append((timeline,CaptionPaintCompanion(back[0],frozenset(e.source_index for e in back),tuple(fill_phases))))
    uses={}
    for t,c in proposals:
        for i in c.members:uses[i]=uses.get(i,0)+1
    result=[]
    for t in timelines:
        companions=tuple(c for owner,c in proposals if owner is t and all(uses[i]==1 for i in c.members))
        # Coextensive same-style sources can already belong to one paint proof.
        # Give the retained outer planes their own identities before emission.
        members=t.members-frozenset(i for c in companions for i in c.members)
        result.append(dataclass_replace(t,members=members,companions=companions))
    return tuple(result)


def _retained_caption_plane(events: list[Event], owner: Event, members: frozenset[int],
                            start: float, end: float, literal: str, *, allow_overlaps: bool=False) -> list[Event]:
    """Validate a source-owned plane's complete, unchanged retained interval."""
    matches=sorted([e for e in events if e.kind=='Dialogue' and e.source_index in members and
        e.style==owner.style and e.name==owner.name and
        e.start_s>=start-1e-6 and e.end_s<=end+1e-6 and
        ''.join(OVERRIDE_RE.sub('',e.text).split())==literal],key=lambda e:e.start_s)
    if not matches or abs(matches[0].start_s-start)>1e-6 or abs(max(e.end_s for e in matches)-end)>1e-6:return []
    if allow_overlaps:
        if len({e.layer for e in matches})!=1:return []
        covered=start
        for e in matches:
            if e.start_s>covered+1e-6:return []
            covered=max(covered,e.end_s)
    elif any(abs(a.end_s-b.start_s)>1e-6 for a,b in zip(matches,matches[1:])):return []
    paint=set(CAPTION_PAINT_TAGS)|{'alpha','c'}
    layouts=[static_text_paint_geometry(e,paint) for e in matches]
    if any(p is None or p[0]!=layouts[0][0] for p in layouts):return []
    return matches


def _render_caption_phase(event: Event, palette: tuple, *, companion_fill: tuple | None=None) -> str | None:
    """Map the proved phase to retained spans; companions keep all other paint."""
    ranges=_literal_paint_ranges([event])
    if ranges is None:return None
    fragments=[];paints=[];cursor=0
    for literal,states in ranges:
        for char in literal:
            index=min(cursor,len(palette)-1);proof=palette[index]
            if not char.isspace():cursor+=1
            fragments.append((char,states))
            updates=({'1c':companion_fill[index][0],'1a':companion_fill[index][1],'3c':proof.fill} if companion_fill is not None else
                {'1c':proof.fill,'3c':proof.outline,'3a':proof.outline_alpha,
                 'bord':proof.border[0],'xbord':proof.border[0],'ybord':proof.border[1]})
            paints.append({**states[0],**updates})
    tags={'1c','1a','3c'} if companion_fill is not None else set(CAPTION_PAINT_TAGS)|{'alpha','c'}
    return _render_literal_paint(event,fragments,paints,tags)


def _emit_caption_paint_timelines(events: list[Event], timelines: tuple,
                                   config: SimplifyConfig) -> tuple[list[Event],dict]:
    """Materialize producer-owned paint after layout, without rediscovering intent.

    No timing/geometry is inferred here. A complete retained caption must match
    its original owner and interval. Consumers already settled layout and lyric
    boundaries; only source-proved temporal paint is serialized now.
    """
    counts={k:0 for k in ('color_phase_captions_limited','color_phase_changes_removed',
        'color_phase_rate_limited','color_phase_hold_limited',
        'color_phase_captions_preserved','color_phase_changes_preserved')}
    counts.update(color_phase_min_hold=config.color_phase_min_hold,
                  color_phase_change_interval=config.color_phase_change_interval,color_phase_limits=[])
    replacements={}
    for timeline in timelines:
        owner=timeline.owner
        matches=_retained_caption_plane(events,owner,timeline.members,owner.start_s,owner.end_s,timeline.literal,
                                       allow_overlaps=bool(timeline.overlap_handoffs))
        if not matches:continue
        paint_tags=set(CAPTION_PAINT_TAGS)|{'alpha','c'}
        event=max(matches,key=lambda e:e.duration)
        if any(id(e) in replacements for e in matches):continue
        phases=timeline.phases;changes=len(phases)-1
        source_times=[(a+b)/2 for a,b,palette in phases]
        rate=(config.color_phase_change_interval>0 and
              changes*config.color_phase_change_interval>owner.duration+1e-6)
        hold=config.color_phase_min_hold>0 and any(b-a+1e-6<config.color_phase_min_hold for a,b,p in phases)
        if rate or hold:
            counts['color_phase_captions_limited']+=1;counts['color_phase_changes_removed']+=changes
            counts['color_phase_rate_limited']+=int(rate);counts['color_phase_hold_limited']+=int(hold)
            counts['color_phase_limits'].append(dict(style=owner.style,text=OVERRIDE_RE.sub('',event.text),
                start=owner.start_s,end=owner.end_s,changes_removed=changes,reason='both' if rate and hold else 'rate' if rate else 'hold'))
            votes={}
            for a,b,palette in phases:
                votes[palette]=votes.get(palette,0)+b-a
            selected=max(votes,key=votes.get)
            # Keep each companion's other paint from the same real source
            # appearance, including fill exposure hidden by the foreground.
            source_times=[next((a+b)/2 for a,b,palette in phases if palette==selected)]
            phases=((owner.start_s,owner.end_s,selected),)
        output=[]
        for a,b,palette in phases:
            body=_render_caption_phase(event,palette)
            start,end=format_time(a),format_time(b)
            if body is None or start==end:output=[];break
            output.append(replace_event(event,text=body,start=start,end=end,start_s=parse_time(start),end_s=parse_time(end)))
        if not output:continue
        for e in matches:replacements[id(e)]=[]
        replacements[id(matches[0])]=output
        for companion in timeline.companions:
            peers=_retained_caption_plane(events,companion.owner,companion.members,
                                          owner.start_s,owner.end_s,timeline.literal,allow_overlaps=bool(timeline.overlap_handoffs))
            if not peers or any(id(e) in replacements or e.layer!=companion.owner.layer for e in peers):continue
            if any(static_text_paint_geometry(e,paint_tags)[0]!=static_text_paint_geometry(event,paint_tags)[0] for e in peers):continue
            pieces=[]
            for (a,b,palette),at in zip(phases,source_times):
                template=next(e for e in peers if e.start_s<=at<e.end_s)
                exposure=next(fill for start,end,fill in companion.fill_phases if start<=at<end)
                body=_render_caption_phase(template,palette,companion_fill=exposure)
                if body is None:pieces=[];break
                start,end=format_time(a),format_time(b)
                pieces.append(replace_event(template,text=body,start=start,end=end,
                                           start_s=parse_time(start),end_s=parse_time(end)))
            if not pieces:continue
            for e in peers:replacements[id(e)]=[]
            replacements[id(peers[0])]=pieces
        if not (rate or hold):
            counts['color_phase_captions_preserved']+=1;counts['color_phase_changes_preserved']+=changes
    return [piece for e in events for piece in replacements.get(id(e),[e])],counts


def _normalize_source_row_paint(
    events: list[Event], source_rows: list[TextRow], *,
    palette_time: float | None = None, proof_required: bool = False,
) -> RowReconstructionResult | None:
    """Return independent paint-normalized rows without assembling or retiming them."""
    # The normal reconstruction stage owns paint for both positioned
    # fragments and assembled lines. Source cues retain their exact timing.
    normalized,rows = {},[]
    for row in source_rows:
        paint = max(row.foreground,key=lambda e:(
            int(e.layer) if e.layer.lstrip('-').isdigit() else 0,e.duration))
        state = paint.state or effective_state(paint.text,paint.defaults,paint.styles)
        originals={p.source_index:p for peers in row.paint_rows for p in peers}
        originals.update((p.source_index,p) for p in row.foreground)
        at=(palette_time if palette_time is not None else
            _representative_source_palette_time(originals.values(),row.base.start_s,row.base.end_s))
        completed=_source_palette_at(paint,at)
        completed_fill=completed[0].state.get('1c') if completed else state.get('1c','FFFFFF')
        paint_tags=set(CAPTION_PAINT_TAGS)|{'alpha','c'}
        context=StackedTextContext({},[],{},paint_tags,set(),originals)
        families={}
        for source in originals.values():
            sampled=_source_palette_at(source,at)
            if sampled is None:
                continue
            profile=static_text_paint_geometry(sampled[0],paint_tags)
            if profile is not None:
                families.setdefault(profile[0],[]).append(sampled[0])
        pieces=[]
        for e,text,pos in row.pieces:
            sampled=_source_palette_at(e,at)
            profile=static_text_paint_geometry(sampled[0],paint_tags) if sampled else None
            family=families.get(profile[0],[]) if profile else []
            chosen=max(family,key=lambda p:(int(p.layer) if p.layer.lstrip('-').isdigit() else 0,
                                           p.duration,-p.source_index)) if family else None
            contour=None
            if chosen is not None:
                ranges=_literal_paint_ranges([chosen])
                # A sharp foreground may already own its contour. Its lower
                # glow must not turn that authored stroke into ambiguous paint.
                if ranges and all(states[0].get('1a',0)==0 and
                        not states[0].get('blur',0) and not states[0].get('be',0) and
                        not any(states[0].get(k,states[0].get('shad',0)) for k in ('xshad','yshad'))
                        for _,states in ranges):
                    proofs=[_source_caption_paint(states[0],[states[0]]) for _,states in ranges]
                    if all(proof is not None for proof in proofs) and (len(family)==1 or any(max(proof.border)>0 for proof in proofs)):
                        contour=(ranges,proofs)
                if contour is None:
                    contour=_stacked_source_contour_paint(context,chosen,family,at=at)
            if contour is not None:
                # The dense-row completion proof already owns the shared fill
                # when a terminal fragment has no completed foreground copy.
                # Existing completed copies keep their own intentional variation.
                if (paint.layer.lstrip('-').isdigit() and chosen.layer.lstrip('-').isdigit() and
                        int(chosen.layer)<int(paint.layer)):
                    contour=(contour[0],[dataclass_replace(proof,fill=completed_fill) for proof in contour[1]])
                # Preserve the confirmed fragment's geometry and lifetime.
                body=_render_source_contour_paint(sampled[0],contour,paint_tags)
            else:
                if proof_required:
                    return None
                selected={**e.state,'1c':state.get('1c','FFFFFF')}
                outlines=[p.state for p in row.foreground if p.state]
                body=render_simplified_caption(selected,text,outline_states=outlines,
                    measurement=e.measurement,source_paint=_source_caption_paint(selected,outlines))
            pieces.append((replace_event(e,text=body),text,pos))
        rows.append(dataclass_replace(row,base=pieces[0][0],pieces=pieces,
            paint_rows=[list(peers) for peers in row.paint_rows],
            source_anchors={word:list(anchors) for word,anchors in row.source_anchors.items()},
            foreground=list(row.foreground)))
        normalized.update((e.source_index,e) for e,_,_ in pieces)
    return RowReconstructionResult([normalized.get(e.source_index,e) for e in events],0,0,rows,{})


def _select_row_paint_copies(
    events: list[Event], visible_map: dict[int,str], animated_sources: set[int],
    *, static_only: bool,
) -> tuple[set[int],int]:
    """Select one paint copy per matching positioned glyph before row assembly."""
    removed: set[int] = set()
    duplicate_count = 0
    # Collapse paint copies only at the same position, with matching text,
    # geometry and complete timing. This precedes row reconstruction so that
    # duplicate glyphs cannot become duplicate letters in the assembled text.
    copies: dict[tuple,list[Event]] = {}
    for e in events:
        if (not static_only and e.kind == "Dialogue" and get_pos(e.text) is not None and
                (e.lyric or e.source_index in animated_sources) and
                visible_map.get(e.source_index) and not inline_layout_key(e)):
            key = (e.start,e.end,e.style,e.name,e.row,get_pos(e.text),
                   visible_map[e.source_index],text_layout_key(e),placement_key(e))
            copies.setdefault(key,[]).append(e)
    for group in copies.values():
        if len(group) < 2:
            continue
        chosen = min(group,key=lambda e:(e.state.get("1a",0),
                     -int(e.layer) if e.layer.lstrip("-").isdigit() else 0,
                     -e.source_index))
        removed.update(e.source_index for e in group if e is not chosen)
        duplicate_count += len(group)-1
    return removed,duplicate_count


def _prepare_row_reconstruction(
    events: list[Event], visible_map: dict[int, str], space_map: dict[tuple, set[float]],
    font_metrics: FontMetrics | None, animated_sources: set[int],
    source_events: dict[int, Event] | None, *, static_only: bool,
    font_report: FontProcessingReport | None=None,
) -> tuple[RowReconstructionContext, RowReconstructionEdits]:
    """Index original eligible glyph neighbors and authored comments once."""
    removed,duplicates = _select_row_paint_copies(
        events,visible_map,animated_sources,static_only=static_only)
    eligible = []
    for e in events:
        text = visible_map.get(e.source_index, "")
        if (e.source_index in removed or e.kind != "Dialogue" or not text or
                get_pos(e.text) is None or e.duration <= 0 or e.state.get("p",0) or
                OVERRIDE_RE.search(e.text,re.match(r"(?:\{[^}]*\})*",e.text).end()) or
                "clip" in e.state or "iclip" in e.state or
                any(tag in e.text for tag in (r"\N",r"\n")) or
                any(abs(e.state.get(tag,0)) > .001
                    for tag in ("frz","frx","fry","fax","fay"))):
            continue
        eligible.append(e)

    # Keep original glyph anchors as evidence even after an earlier merge.
    # Position and start-time indexes bound checks to nearby row neighbors.
    neighbors = {}
    for e in eligible:
        px,py = get_pos(e.text)
        neighbors.setdefault(_row_family_key(e),[]).append((e,px,py,text_height(e)))
    for key,group in neighbors.items():
        spatial = sorted(group,key=lambda item:item[1])
        temporal = sorted(group,key=lambda item:item[0].start_s)
        neighbors[key] = (([px for e,px,py,height in spatial],spatial),
                          ([e.start_s for e,px,py,height in temporal],temporal))

    comments: dict[str,list[tuple[Event,str]]] = {}
    for e in events:
        if e.kind == "Comment":
            comments.setdefault(e.style,[]).append((e,simplify_text(e.text,visible_only=True)[1]))
    edits = RowReconstructionEdits(removed=removed,duplicate_count=duplicates)
    context = RowReconstructionContext(eligible,neighbors,comments,
        collections.ChainMap(edits.visibility_updates,visible_map),
        space_map,font_metrics,animated_sources,source_events, font_report=font_report)
    return context,edits


def _row_family_key(e: Event) -> tuple:
    """Group paragraph geometry while permitting sampled scale and decoration."""
    return (e.style,e.name,e.row,e.margin_l,e.margin_r,e.margin_v,
            tuple((k,v) for k,v in text_layout_key(e)
                  if k not in {"fscx","fscy","u","s"}))


def _row_has_conflicting_phase(
    context: RowReconstructionContext, ordered: list[Event], start: float, end: float,
) -> bool:
    """Reject a union that extends a glyph into an unclaimed matching phase."""
    members = {e.source_index for e in ordered}
    for piece in ordered:
        (positions, spatial), _ = context.neighbors[_row_family_key(piece)]
        px, py = get_pos(piece.text)
        tolerance = piece.unit
        for peer, x, y, height in spatial[bisect_left(positions, px-tolerance):
                                           bisect_right(positions, px+tolerance)]:
            if (peer.source_index in members or
                    abs(y-py) > .15*min(text_height(piece), height) or
                    context.visible_map[peer.source_index] != context.visible_map[piece.source_index]):
                continue
            # Only overlap added by the proposed union is a conflict.
            overlap = min(peer.end_s,end)-max(peer.start_s,start)
            original = max(0.0,min(peer.end_s,piece.end_s)-max(peer.start_s,piece.start_s))
            if overlap > original+_ROW_TIME_QUANTUM:
                return True
    return False


def _row_gap_is_occupied(
    context: RowReconstructionContext, ordered: list[Event], start: float, end: float,
    *, complete_row: bool = False,
) -> bool:
    """Check original nearby glyphs so omitted letters cannot become inferred spaces."""
    # Font advances cannot distinguish real spaces from omitted letters.
    # Persistent matching row neighbors must belong to the candidate row.
    xs = [get_pos(e.text)[0] for e in ordered]
    y = statistics.median(get_pos(e.text)[1] for e in ordered)
    tolerance = min(e.unit for e in ordered)
    height = min(text_height(e) for e in ordered)
    members = {e.source_index for e in ordered}
    (positions,spatial),(starts,temporal) = context.neighbors[_row_family_key(ordered[0])]
    reach = 2*height if complete_row else 0
    left,right = ((bisect_left(positions,xs[0]-reach),bisect_right(positions,xs[-1]+reach))
                  if complete_row else
                  (bisect_right(positions,xs[0]+tolerance),bisect_left(positions,xs[-1]-tolerance)))
    # Mutual 50% overlap implies a nearby start. These broad bounds keep
    # past/future cues out before the exact lifetime and geometry checks.
    early,late = bisect_left(starts,start-(end-start)),bisect_left(starts,end)
    peers,begin,stop = ((spatial,left,right) if right-left <= late-early else
                        (temporal,early,late))
    for index in range(begin,stop):
        peer,px,py,peer_height = peers[index]
        if (peer.source_index in members or abs(py-y) > .15*min(height,peer_height) or
                min(peer.end_s,end)-max(peer.start_s,start) < .5*max(peer.duration,end-start)):
            continue
        gap = bisect_left(xs,px)
        if 0 < gap < len(xs) and xs[gap-1]+tolerance < px < xs[gap]-tolerance:
            return True
        # Timing similarity can select only the middle of a longer row.
        # Near-coextensive candidates need the nearby edge glyphs too;
        # otherwise their partial model could falsely identify a new cue.
        if complete_row and (xs[0]-2*min(height,peer_height) <= px <= xs[0]+tolerance or
                             xs[-1]-tolerance <= px <= xs[-1]+2*min(height,peer_height)):
            return True
    return False


def _propose_shared_glyph_rows(
    context: RowReconstructionContext, family: list[Event],
) -> list[tuple]:
    """Fit complete cues containing held letters, retaining authored-text agreement."""
    family.sort(key=lambda e:e.start_s)
    starts = [e.start_s for e in family]
    latest = []
    for e in family:
        latest.append(max(latest[-1] if latest else -math.inf,e.end_s))
    cues = {}
    for e in family:
        cues.setdefault((e.start_s,e.end_s),[]).append(e)
    proposals = []
    for (start,end),seed in cues.items():
        if len(seed) < 2:
            continue
        seed_ids = {e.source_index for e in seed}
        shared = [e for e in family[bisect_left(latest,end):bisect_right(starts,start)]
                  if e.source_index not in seed_ids and e.end_s >= end]
        if not shared:
            continue
        ordered = sorted(seed+shared,key=lambda e:get_pos(e.text)[0])
        geometry = positioned_row_geometry(ordered)
        if geometry is None:
            continue
        xs,ys = geometry
        fragments = [context.visible_map[e.source_index] for e in ordered]
        literal = ''.join(fragments)
        authored = {text for comment,text in context.comments.get(seed[0].style,[]) if
                    ''.join(text.split()) == literal and
                    min(comment.end_s,end)-max(comment.start_s,start) >=
                    .8*max(comment.duration,end-start)}
        if len(authored) > 1:
            continue
        if not authored and (_row_gap_is_occupied(context,ordered,start,end) or any(
                comment.name == seed[0].name and text and
                min(comment.end_s,end)-max(comment.start_s,start) >=
                .8*max(comment.duration,end-start)
                for comment,text in context.comments.get(seed[0].style,[]))):
            continue
        fit = recover_font_row(context.font_metrics, ordered,fragments, font_report=context.font_report)
        if fit is None:
            continue
        text = next(iter(authored)) if authored else fit[0]
        if fit[0].split() != text.split():
            continue
        _,x,sx,sy,alignment = fit
        body = render_merged_caption(ordered,fragments,text,animated=False,
            an=alignment,pos=(x,statistics.median(ys)),fscx=sx,fscy=sy)
        if body is not None:
            proposals.append((seed,shared,ordered,body,text,bool(authored)))
    return proposals


def _shared_rows_cover_held_glyphs(proposals: list[tuple]) -> bool:
    """Require complete held-glyph lifetimes and disjoint unauthored fitted cues."""
    # Reject the connected proposal set if any shared member has an
    # uncovered interval, including a failed or missing adjacent cue.
    shared_ids = {e.source_index:e for _,shared,_,_,_,_ in proposals for e in shared}
    # Without authored row evidence, the fitted cues must also be
    # disjoint: an overlap would draw the held letter more than once.
    measured_ids = {e.source_index for _,shared,_,_,_,authored in proposals
                    if not authored for e in shared}
    if set(shared_ids) & {e.source_index for seed,_,_,_,_,_ in proposals for e in seed}:
        return False
    valid = bool(proposals)
    for index,e in shared_ids.items():
        intervals = sorted((seed[0].start_s,seed[0].end_s)
                           for seed,shared,ordered,body,text,authored in proposals
                           if any(p.source_index == index for p in ordered))
        covered = e.start_s
        for start,end in intervals:
            if (start > covered+.001 or
                    index in measured_ids and start < covered-.001):
                valid = False; break
            covered = max(covered,end)
        if covered < e.end_s-.001:
            valid = False
    return valid


def _reconstruct_shared_glyph_rows(
    context: RowReconstructionContext, edits: RowReconstructionEdits,
) -> None:
    """Commit shared-letter families only when every held glyph stays covered.

    Equal-time grouping sees a hole when a stationary letter spans successive
    cues. Fit complete rows, but consume that letter only if those cues cover
    its entire original lifetime and agree with authored word gaps.
    """
    families = {}
    for e in context.eligible:
        if (e.lyric and e.source_index not in context.animated_sources and e.state.get('1a',0) == 0 and
                len(context.visible_map[e.source_index]) == 1 and
                static_object_key(e,e.styles) is not None):
            key = (_row_family_key(e),e.layer,state_key(e,{'pos'}))
            families.setdefault(key,[]).append(e)
    for family in families.values():
        proposals = _propose_shared_glyph_rows(context,family)
        if not _shared_rows_cover_held_glyphs(proposals):
            continue
        for seed,shared,ordered,body,text,authored in proposals:
            first = min(seed,key=lambda e:e.source_index)
            pieces = [(e,context.visible_map[e.source_index],get_pos(e.text)) for e in ordered]
            edits.replacements[first.source_index] = replace_event(first,text=body,effect='')
            edits.visibility_updates[first.source_index] = text
            edits.row_evidence[first.source_index] = TextRow(edits.replacements[first.source_index],
                pieces)
            before = len(edits.removed)
            edits.removed.update(e.source_index for e in ordered if e is not first)
            edits.merged_count += len(edits.removed)-before
            if context.font_report is not None:
                context.font_report.rows_joined += 1


def _prove_text_row_join(
    context: RowReconstructionContext, edits: RowReconstructionEdits,
    run: list[Event], animated: bool, *, coextensive: bool = False,
) -> RowJoinCandidate | None:
    """Prove row geometry, lifetime compatibility, phase ownership and empty gaps."""
    if len(run) < 2 or any(e.source_index in edits.removed or
                          e.source_index in edits.replacements for e in run):
        return None
    ordered = sorted(run,key=lambda e:get_pos(e.text)[0])
    geometry = positioned_row_geometry(ordered)
    if geometry is None:
        return None
    xs,ys = geometry
    start,end = min(e.start_s for e in run),max(e.end_s for e in run)
    shared_interval = min(e.end_s for e in run)-max(e.start_s for e in run) > _ROW_TIME_QUANTUM
    if coextensive and (len(run) < 4 or
            min(e.end_s for e in run)-max(e.start_s for e in run) < .8*(end-start)-1e-6 or
            any(e.layer != run[0].layer or e.state.get('1a',0) != 0 or
                _row_family_key(e) != _row_family_key(run[0]) or
                state_key(e,{'pos'}) != state_key(run[0],{'pos'}) for e in run)):
        return None
    if animated:
        # Span decoration can vary; font metrics and paragraph geometry
        # must agree even when a proven source row bypasses grouping.
        reference = _row_family_key(run[0])
        if (any(_row_family_key(e) != reference for e in run) or
                not all(e.source_index in context.animated_sources for e in run) or
                any(min(a.end_s,b.end_s)-max(a.start_s,b.start_s) <= _ROW_TIME_QUANTUM
                    for a,b in zip(ordered,ordered[1:])) or
                not any(all(direction*(b.start_s-a.start_s) >= -_ROW_TIME_QUANTUM and
                                direction*(b.end_s-a.end_s) >= -_ROW_TIME_QUANTUM
                                for a,b in zip(ordered,ordered[1:]))
                        for direction in (1,-1))):
            return None
    if _row_has_conflicting_phase(context,ordered,start,end):
        return None
    y = statistics.median(ys)
    if _row_gap_is_occupied(context,ordered,start,end,complete_row=coextensive):
        return None
    return RowJoinCandidate(run,ordered,xs,ys,start,end,shared_interval,y)


def _fit_text_row_caption(
    context: RowReconstructionContext, candidate: RowJoinCandidate,
    fragments: list[str], animated: bool, *, coextensive: bool = False,
) -> RowCaptionFit | None:
    """Recover text spaces and layout from authored text, blanks or exact-font fits."""
    run,ordered,xs,ys,start,end,shared_interval = (
        candidate.run,candidate.ordered,candidate.xs,candidate.ys,
        candidate.start,candidate.end,candidate.shared_interval)
    norm = lambda value: "".join(value.split())
    authored = {words for comment,words in context.comments.get(run[0].style,[])
                if min(comment.end_s,end)-max(comment.start_s,start) >=
                   .8*max(comment.duration,end-start) and
                   norm(words) == norm("".join(fragments))}
    text = next(iter(authored)) if len(authored) == 1 else None
    x = (xs[0]+xs[-1])/2
    # Keep the authored vertical band when centering a combined row.
    alignment = ((int(ordered[0].state.get('an',5))-1)//3)*3+2
    sx = statistics.median(e.state.get("fscx",100) for e in run)
    sy = statistics.median(e.state.get("fscy",100) for e in run)
    if text is None:
        blanks = context.space_map.get((format_time(start),format_time(end),
                                run[0].style,run[0].name,run[0].row),set())
        if blanks:
            text = fragments[0]+"".join(
                (" " if any(a < space < b for space in blanks) else "")+part
                for a,b,part in zip(xs,xs[1:],fragments[1:]))
    measured = False
    tracking = None
    expected_text = text
    if (text is None or coextensive) and context.font_metrics is not None:
        # Karaoke pulses can leave different sampled scales per glyph.
        # Animated rows share their median scale; static rows are exact.
        metric_row = [dataclass_replace(e,state={**e.state,"fscx":sx,"fscy":sy})
                      for e in ordered] if animated else ordered
        if abs(metric_row[0].state.get('fsp',0)) > .001:
            fit = recover_tracked_font_row(context.font_metrics, metric_row,fragments, font_report=context.font_report)
            if fit is not None:
                text,x,sx,sy,alignment,tracking = fit
        else:
            fit = recover_font_row(context.font_metrics, metric_row,fragments, font_report=context.font_report)
            if fit is not None:
                text,x,sx,sy,alignment = fit
        if fit is not None:
            measured = True
        elif all(unicodedata.category(c) == "Lo" and
                 unicodedata.east_asian_width(c) in ("W","F")
                 for part in fragments for c in part):
            fit = fit_fullwidth_run(context.font_metrics, metric_row,fragments, font_report=context.font_report)
            if fit is not None:
                x,sx = fit
                text = "".join(fragments)
                alignment = int(ordered[0].state.get("an",5))
                measured = True
    if coextensive and (not measured or expected_text is not None and
                        expected_text.split() != text.split()):
        return None
    if text is None or animated and not shared_interval and not measured:
        return None
    return RowCaptionFit(text,x,sx,sy,alignment,tracking,measured)


def _join_text_row(
    context: RowReconstructionContext, edits: RowReconstructionEdits,
    run: list[Event], animated: bool, *, coextensive: bool = False,
    preserve_paint: bool = False,
) -> bool:
    """Render a proved fitted row and record its replacement, evidence and counts."""
    candidate = _prove_text_row_join(context,edits,run,animated,coextensive=coextensive)
    if candidate is None:
        return False
    fragments = [context.visible_map[e.source_index] for e in candidate.ordered]
    fit = _fit_text_row_caption(context,candidate,fragments,animated,coextensive=coextensive)
    if fit is None:
        return False
    run,ordered,xs,ys,start,end,shared_interval = (
        candidate.run,candidate.ordered,candidate.xs,candidate.ys,
        candidate.start,candidate.end,candidate.shared_interval)
    y = candidate.y
    text,x,sx,sy,alignment,tracking,measured = (
        fit.text,fit.x,fit.sx,fit.sy,fit.alignment,fit.tracking,fit.measured)
    chosen = ordered[0]
    body = render_merged_caption(ordered,fragments,text,animated=animated,
                                 preserve_paint=preserve_paint,an=alignment,pos=(x,y),fscx=sx,fscy=sy,fsp=tracking)
    if body is None:
        return False
    first = min(e.source_index for e in run)
    # Preserve the visible shadow-painted foreground above independent
    # decorative glyphs. Other animation reducers retain their established
    # layer normalization; their phase/echo matching relies on that order.
    layer = (chosen.layer if not animated or all(animated_shadow_painted_source(
        e,context.source_events,context.animated_sources) for e in run) else '0')
    edits.replacements[first] = replace_event(chosen,source_index=first,
        start=format_time(start),end=format_time(end),start_s=start,end_s=end,
        text=body,effect="",layer=layer)
    edits.visibility_updates[first] = text
    edits.row_evidence[first] = TextRow(edits.replacements[first],
        [(e,text,(x,y)) for e,text,x,y in zip(ordered,fragments,xs,ys)])
    if animated and not shared_interval:
        edits.chain_families.add(_row_family_key(ordered[0]))
    if coextensive:
        edits.coextensive_rows.add(first)
    edits.removed.update(e.source_index for e in run if e.source_index != first)
    edits.merged_count += len(run)-1
    if measured:
        if context.font_report is not None:
            context.font_report.rows_joined += 1
    return True


def _reconstruct_confirmed_source_rows(
    context: RowReconstructionContext, edits: RowReconstructionEdits,
    source_rows: list[TextRow],
) -> set[int]:
    """Reuse confirmed source fragments, protecting their exact cue timing."""
    # Reuse proven source rows, without redetecting their original fragments.
    current = {e.source_index:e for e in context.eligible}
    protected = set()
    for row in source_rows:
        run = [current[e.source_index] for e,_,_ in row.pieces if e.source_index in current]
        if (len(run) == len(row.pieces) and all(
                e.start == row.base.start and e.end == row.base.end for e in run)):
            protected.update(e.source_index for e in run)
            if not _join_text_row(context,edits,run,all(e.source_index in context.animated_sources for e in run),
                                  preserve_paint=True):
                idx = -1-sum(r.virtual for r in edits.row_evidence.values())
                xs = [pos[0] for _,_,pos in row.pieces]
                ys = [pos[1] for _,_,pos in row.pieces]
                base = replace_event(run[0],source_index=idx,
                    text=set_pos(run[0].text,((xs[0]+xs[-1])/2,statistics.median(ys))))
                edits.row_evidence[idx] = TextRow(base,
                    [(e,text,pos) for e,(_,text,pos) in zip(run,row.pieces)],virtual=True)
    return protected


def _reconstruct_animated_row_sweeps(
    context: RowReconstructionContext, edits: RowReconstructionEdits, protected: set[int],
) -> None:
    """Try longest monotonic animation sweeps before equal-time subsets."""
    # Animated candidates are tried as complete sweeps before equal-time
    # subsets, so a syllable is not prematurely assembled into a separate word.
    sweeps: dict[tuple,list[Event]] = {}
    for e in context.eligible:
        if (e.source_index in context.animated_sources and
                e.source_index not in protected):
            sweeps.setdefault(_row_family_key(e),[]).append(e)
    candidates = []
    for bucket in sweeps.values():
        for direction in (1,-1):
            ordered = sorted(bucket,key=lambda e:(e.start_s,direction*get_pos(e.text)[0]))
            # Keep shared-interval candidates as fallbacks when a longer chain
            # has no unambiguous font fit. Both use the same trajectory rules.
            for shared in ((True,False) if context.font_metrics is not None else (True,)):
                run = []
                for e in ordered:
                    if run and (direction*(get_pos(e.text)[0]-get_pos(run[-1].text)[0]) <= e.unit or
                                e.end_s < run[-1].end_s-_ROW_TIME_QUANTUM or
                                e.start_s >= (min(p.end_s for p in run) if shared else run[-1].end_s)-_ROW_TIME_QUANTUM or
                                abs(get_pos(e.text)[1]-get_pos(run[0].text)[1]) >
                                .15*min(text_height(e),text_height(run[0]))):
                        candidates.append(run)
                        run = []
                    run.append(e)
                candidates.append(run)
    for run in sorted(candidates,key=lambda run:-len(run)):
        _join_text_row(context,edits,run,True)


def _reconstruct_coextensive_rows(
    context: RowReconstructionContext, edits: RowReconstructionEdits, protected: set[int],
) -> None:
    """Try uniquely owned near-coextensive rows with exact-font spacing proof."""
    # The 25% seed window bounds the search; the completed row must still
    # share 80% of its entire union interval in _prove_text_row_join.
    # Never grow a cue by chaining pairwise overlaps. Conflicting memberships
    # stay separate, and original neighbors must not occupy inferred spaces.
    holds = {}
    for e in context.eligible:
        if (e.source_index not in protected and e.source_index not in edits.removed and
                e.source_index not in edits.replacements and e.state.get('1a',0) == 0):
            holds.setdefault((_row_family_key(e),e.layer,state_key(e,{'pos'})),[]).append(e)
    proposals = {}
    for bucket in holds.values():
        bucket.sort(key=lambda e:e.start_s)
        starts = [e.start_s for e in bucket]
        seeds = {(e.start_s,e.end_s,get_pos(e.text)[1]):e for e in bucket}
        for seed in seeds.values():
            window = .25*seed.duration
            row = [e for e in bucket[bisect_left(starts,seed.start_s-window):
                                    bisect_right(starts,seed.start_s+window)]
                   if abs(e.end_s-seed.end_s) <= window and
                      abs(get_pos(e.text)[1]-get_pos(seed.text)[1]) <=
                      .15*min(text_height(e),text_height(seed))]
            if len(row) < 4 or len({(e.start,e.end) for e in row}) == 1:
                continue
            start,end = min(e.start_s for e in row),max(e.end_s for e in row)
            if min(e.end_s for e in row)-max(e.start_s for e in row) >= .8*(end-start)-1e-6:
                proposals.setdefault(frozenset(e.source_index for e in row),row)
    owners = {}
    for members in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    for members,row in proposals.items():
        if all(owners[index] == 1 for index in members):
            _join_text_row(context,edits,row,False,coextensive=True)


def _reconstruct_simultaneous_rows(
    context: RowReconstructionContext, edits: RowReconstructionEdits, protected: set[int],
) -> None:
    """Assemble remaining equal-time, equal-paint fragments through the same joiner."""
    simultaneous: dict[tuple,list[Event]] = {}
    for e in context.eligible:
        if (e.source_index not in edits.removed and e.source_index not in edits.replacements and
                e.source_index not in protected):
            key = (_row_family_key(e),e.start,e.end,e.layer,state_key(e,{"pos"}))
            simultaneous.setdefault(key,[]).append(e)
    for run in simultaneous.values():
        _join_text_row(context,edits,run,False)


def _trim_reconstructed_row_tails(
    context: RowReconstructionContext, edits: RowReconstructionEdits,
) -> None:
    """Trim proved overlapping row tails only after all original fragments appear."""
    # Rolling rows may retain late syllables while the next row enters from
    # the left. Once each row is a complete caption, those tails would draw
    # whole sentences over each other. End proven chains at the next row,
    # only after every fragment has appeared and the caption spans overlap.
    sequences = {}
    for index,row in edits.row_evidence.items():
        key = _row_family_key(row.pieces[0][0])
        if not row.virtual and (key in edits.chain_families or index in edits.coextensive_rows):
            xs = [pos[0] for piece,word,pos in row.pieces]
            sequences.setdefault(key,[]).append((index,row,min(xs),max(xs),
                max(piece.start_s for piece,word,pos in row.pieces)))
    for sequence in sequences.values():
        sequence.sort(key=lambda item:item[1].base.start_s)
        for offset,(index,row,left,right,last_start) in enumerate(sequence):
            for other in range(offset+1,len(sequence)):
                _,peer,peer_left,peer_right,_ = sequence[other]
                if peer.base.start_s >= row.base.end_s:
                    break
                overlap = min(right,peer_right)-max(left,peer_left)
                if (peer.base.start_s > last_start+_ROW_TIME_QUANTUM and
                        overlap > .5*min(right-left,peer_right-peer_left)):
                    # A near-coextensive row may have a staggered exit tail.
                    # Trim only inside its same 20% boundary budget, after
                    # every original fragment has appeared. Other rows retain
                    # the established rolling-sweep timing rule.
                    if (index in edits.coextensive_rows and
                            row.base.end_s-peer.base.start_s > .2*row.base.duration+_ROW_TIME_QUANTUM):
                        continue
                    end = peer.base.start_s
                    row.base = replace_event(row.base,end=format_time(end),end_s=end)
                    edits.replacements[index] = row.base
                    break


def _collect_virtual_row_evidence(
    output: list[Event], context: RowReconstructionContext,
    edits: RowReconstructionEdits, protected: set[int],
) -> None:
    """Record unassembled rows as evidence without emitting inferred text or spacing."""
    # Record unassembled rows here too. These models supply shadow-copy
    # evidence without requiring fonts or emitting inferred word spacing.
    fragments: dict[tuple,list[Event]] = {}
    for e in output:
        if (e.kind == "Dialogue" and e.source_index not in edits.row_evidence and
                e.source_index not in protected and
                (e.lyric or e.source_index in context.animated_sources) and
                context.visible_map.get(e.source_index) and get_pos(e.text) is not None and
                not e.state.get("p",0) and not inline_layout_key(e) and
                "clip" not in e.state and "iclip" not in e.state and
                e.state.get("1a",0) == 0):
            key = (e.style,e.name,e.row,e.start,e.end,text_layout_key(e))
            fragments.setdefault(key,[]).append(e)
    virtual_count = sum(row.virtual for row in edits.row_evidence.values())
    for group in fragments.values():
        for ordered in split_positioned_row_runs(group):
            if len(ordered) < 2:
                continue
            geometry = positioned_row_geometry(ordered,min_x_step=ordered[0].unit)
            if geometry is None:
                continue
            xs,ys = geometry
            idx = -virtual_count-1
            base = replace_event(ordered[0],source_index=idx,
                text=set_pos(ordered[0].text,((xs[0]+xs[-1])/2,statistics.median(ys))))
            edits.row_evidence[idx] = TextRow(base,[(e,context.visible_map[e.source_index],(x,y))
                                            for e,x,y in zip(ordered,xs,ys)],virtual=True)
            virtual_count += 1


def reconstruct_text_rows(
    events: list[Event], visible_map: dict[int, str], space_map: dict[tuple, set[float]],
    font_metrics: FontMetrics | None, animated_sources: set[int],
    source_rows: list[TextRow] | None=None, source_only: bool=False, *, static_only: bool=False,
    source_events: dict[int, Event] | None=None, font_report: FontProcessingReport | None=None,
) -> RowReconstructionResult:
    """Reconstruct static and animated rows with shared evidence and rendering.

    Static rows share effective styling and equal timing. A timing fallback
    also accepts equal-paint fragments sharing 80% of their complete interval,
    with exact-font spacing evidence. Longer sweeps require animation evidence
    for every fragment, monotonic starts and ends, and overlapping visibility.
    A chain without a common interval also requires exact-font spacing recovery.
    Spaces come from authored
    text, explicit blank positions, or measured advances in the exact font.
    Persistent matching row neighbors cannot occupy gaps between fragments.
    If spacing is unproven, preserve the original fragment positions and timing.
    The final static-only pass assembles equal-time, equal-paint fragments;
    it neither extends lifetimes nor chooses between different paint copies.
    Borrow event, source-row and shared-map inputs. Return final events/rows
    and proved visibility updates; the caller applies the updates explicitly.
    """
    backing = {row.base.source_index:row.owned_backing for row in (source_rows or [])
               if row.phase_core is not None and not row.virtual and not static_only}
    phase_cores = {row.base.source_index:row.phase_core for row in (source_rows or [])
                   if row.phase_core is not None and not row.virtual and not static_only}
    source_rows = [row for row in (source_rows or []) if row.confirmed and not static_only]
    if source_only:
        return _normalize_source_row_paint(events,source_rows)
    context,edits = _prepare_row_reconstruction(
        events,visible_map,space_map,font_metrics,animated_sources,source_events,
        static_only=static_only, font_report=font_report)
    if font_metrics is not None and not static_only:
        _reconstruct_shared_glyph_rows(context,edits)
    protected = _reconstruct_confirmed_source_rows(context,edits,source_rows)
    if not static_only:
        _reconstruct_animated_row_sweeps(context,edits,protected)
        if font_metrics is not None and getattr(font_metrics,'available',False):
            _reconstruct_coextensive_rows(context,edits,protected)
    _reconstruct_simultaneous_rows(context,edits,protected)
    _trim_reconstructed_row_tails(context,edits)
    output = [edits.replacements.get(e.source_index,e) for e in events
              if e.source_index not in edits.removed]
    if not static_only:
        _collect_virtual_row_evidence(output,context,edits,protected)
    rows = list(edits.row_evidence.values())
    # Joining words changes the representative source ID. Carry only complete
    # core evidence, protecting the union of every constituent held interval.
    rows = [dataclass_replace(row,phase_core=(
                min(phase_cores[e.source_index][0] for e,word,pos in row.pieces),
                max(phase_cores[e.source_index][1] for e,word,pos in row.pieces)),
                owned_backing=tuple(paint for e,word,pos in row.pieces
                                    for paint in backing.get(e.source_index,())))
            if row.pieces and all(e.source_index in phase_cores for e,word,pos in row.pieces)
            else row for row in rows]
    return RowReconstructionResult(output,edits.merged_count,edits.duplicate_count,
                                   rows,edits.visibility_updates)


def match_translucent_glyph_particles(events: list[Event], row_evidence: list[TextRow],
                                      words: dict[int,str],
                                      animated_sources: set[int]) -> set[int]:
    """Prove dense, complete particle phases behind an opaque source row.

    Match original movement endpoints to authored glyph anchors, without font
    substitution or sampled geometry. Each repeated phase must cover every
    glyph exactly once; incomplete or multiply owned families remain intact.
    This matcher returns membership only and never changes foreground rows.
    """
    if not events or not row_evidence:
        return set()
    buckets = {}
    identity = lambda e: (e.style,e.name,e.margin_l,e.margin_r,e.margin_v)
    geometry = {key for key,_ in text_layout_key(row_evidence[0].base)}
    varying = {"fscx","fscy","frz","frx","fry"}
    paint = {"alpha","1a","2a","3a","4a","c","1c","2c","3c","4c","blur","be"}
    for e in events:
        word = words.get(e.source_index,"")
        if (e.kind != "Dialogue" or e.source_index not in animated_sources or
                len(word) != 1 or word.isspace() or e.duration <= 0 or
                not e.layer.lstrip('-').isdigit() or inline_layout_key(e)):
            continue
        tags = [item for block in OVERRIDE_RE.findall(e.text)
                for item in tokenize_override(block)]
        moves = [value for tag,value in tags if tag == "move"]
        if (len(moves) != 1 or any(tag not in geometry|paint|{"move","fad","t"}
                                   for tag,value in tags)):
            continue
        try:
            move = tuple(float(v.strip()) for v in moves[0][1:-1].split(','))
        except ValueError:
            continue
        if (len(move) not in (4,6) or not all(math.isfinite(v) for v in move) or
                len(move) == 6 and not 0 <= move[4] <= move[5] <= 1000*e.duration):
            continue
        evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
        state = evaluated.formatting
        final = state.copy()
        final_continuation = evaluated.continuation
        states = [state]
        safe = True
        for tag,value in tags:
            if tag != "t":
                continue
            for name,argument in tokenize_override(value[1:-1]):
                if name not in varying|paint:
                    safe = False
                    break
                final_continuation = apply_override(final,name,argument,e.styles,e.defaults,final_continuation)
                states.append(final.copy())
        if (not safe or state.get("blur",0) <= 0 or
                any(min(s.get(k,0) for k in ("1a","3a","4a")) < 128 for s in states)):
            continue
        buckets.setdefault(identity(e),[]).append((e,word,move,state,states))
    for key,group in buckets.items():
        group.sort(key=lambda item:item[0].start_s)
        buckets[key] = ([item[0].start_s for item in group],group)

    families = []
    for row in row_evidence:
        if row.virtual or len(row.pieces) < 4:
            continue
        first = row.base
        foreground = [piece for piece,word,pos in row.pieces]
        if (first.duration <= 0 or any(len(word) != 1 or word.isspace() or
                piece.start != first.start or piece.end != first.end or
                piece.state.get("1a",0) != 0 or
                not piece.layer.lstrip('-').isdigit() or
                piece.source_index in animated_sources for piece,word,pos in row.pieces)):
            continue
        index = buckets.get(identity(first))
        if index is None:
            continue
        starts,group = index
        height = min(text_height(piece) for piece in foreground)
        radius = .25*height
        foreground_layer = min(int(piece.layer) for piece in foreground)
        phases = {}
        for e,word,move,state,states in group[
                bisect_left(starts,first.start_s-.25*first.duration):
                bisect_right(starts,first.end_s+.25*first.duration)]:
            if (e.duration > .25*first.duration or
                    e.end_s > first.end_s+.25*first.duration or
                    int(e.layer) >= foreground_layer):
                continue
            matches = []
            for glyph,(piece,text,pos) in enumerate(row.pieces):
                if (word != text or math.dist(move[:2],pos) > radius or
                        math.dist(move[2:4],pos) > radius or
                        any((str(state.get(k,"")).casefold() != str(piece.state.get(k,"")).casefold()
                             if k == "fn" else state.get(k) != piece.state.get(k))
                            for k in geometry) or
                        any(not .5*piece.state.get(k,100) <= s.get(k,100) <=
                                2*piece.state.get(k,100)
                            for s in states for k in ("fscx","fscy"))):
                    continue
                matches.append(glyph)
            if len(matches) == 1:
                phases.setdefault((e.layer,e.start,e.end),[]).append((matches[0],e))
        if (len(phases) < 3 or any(len(phase) != len(row.pieces) or
                len({glyph for glyph,e in phase}) != len(row.pieces) for phase in phases.values())):
            continue
        peers = [e for phase in phases.values() for glyph,e in phase]
        if max(e.end_s for e in peers)-min(e.start_s for e in peers) < .5*first.duration:
            continue
        families.append({e.source_index for e in peers})
    owners = {}
    for family in families:
        for index in family:
            owners[index] = owners.get(index,0)+1
    return set().union(*(family for family in families if all(owners[index] == 1 for index in family)))


def _eligible_sliced_text_families(events: list[Event]) -> set[tuple[str,str]]:
    """Reject impossible strip families using raw text and exact held-phase boundaries."""
    candidates = [e for e in events if e.kind == 'Dialogue' and
                re.search(r'\\move\s*\(',e.text,re.I) and
                re.search(r'\\clip\s*\(',e.text,re.I) and
                re.search(r'\\(?:alpha|1a|3a)(?=[^A-Za-z]|$)',e.text,re.I) and
                re.search(r'\\t\s*\(',e.text,re.I)]
    if not candidates:
        return set()
    # A source family may contain tens of thousands of unrelated effects.
    # Both strip phases must touch a literal held copy; reject impossible
    # families using raw text/times before resolving their override states.
    families = {(e.style,e.name) for e in candidates}
    beginnings = {(e.style,e.name,e.start,OVERRIDE_RE.sub('',e.text)) for e in candidates}
    endings = {(e.style,e.name,e.end,OVERRIDE_RE.sub('',e.text)) for e in candidates}
    eligible = set()
    for e in events:
        if (e.kind != 'Dialogue' or (e.style,e.name) not in families or
                get_pos(e.text) is None or
                re.search(r'\\(?:move|t|clip|iclip|fad|fade)(?=[^A-Za-z]|$)',e.text,re.I)):
            continue
        literal = OVERRIDE_RE.sub('',e.text)
        if ((e.style,e.name,e.start,literal) in endings and
                (e.style,e.name,e.end,literal) in beginnings):
            eligible.add((e.style,e.name))
    families = eligible
    if not families:
        return set()
    return families


def _sliced_text_layout(e: Event, state: dict, *, scaled: bool = False) -> tuple:
    """Use the existing layout and literal-font key, optionally omitting scale."""
    sample = dataclass_replace(e,state=state)
    return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
            tuple((k,v) for k,v in text_layout_key(sample)
                  if not scaled or k not in {'fscx','fscy'}),literal_font_spans(e))


def _sliced_text_paint(state: dict) -> tuple:
    """Match the original fill, outline, alpha and contour-width channels."""
    return tuple(state.get(k,DEFAULT_STATE.get(k)) for k in
                 ('1c','3c','1a','3a','bord','xbord','ybord'))


def _profile_sliced_text_event(e: Event, families: set[tuple[str,str]]) -> SlicedTextEvent | None:
    """Resolve eligible literal text, static geometry and original movement/transform tokens."""
    if ((e.style,e.name) not in families or e.kind != 'Dialogue' or
            e.duration <= 0 or not e.layer.lstrip('-').isdigit() or
            not OVERRIDE_RE.sub('',e.text).strip() or
            any(tag in e.text for tag in (r'\N',r'\n',r'\h')) or
            literal_font_spans(e) is None):
        return None
    evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
    state = evaluated.formatting
    if (state.get('p',0) or state.get('borderstyle',1) != 1 or
            any(k in state for k in ('iclip','org')) or
            any(abs(state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay')) or
            any(abs(state.get(k,state.get('shad',0))) > .001 for k in ('xshad','yshad')) or
            any(not math.isfinite(state.get(k,0)) or state.get(k,0) <= 0
                for k in ('fs','fscx','fscy'))):
        return None
    p = dataclass_replace(e,state=state,continuation=evaluated.continuation)
    tokens = event_override_tokens(p)
    moves = [v for tag,v in tokens if tag == 'move']
    transforms = [v for tag,v in tokens if tag == 't']
    if any(tag in {'fad','fade','k','kf','ko'} for tag,value in tokens):
        return None
    pos = get_pos(e.text)
    key = _sliced_text_layout(p,state)
    return SlicedTextEvent(p,moves,transforms,pos,key)


def _sliced_text_final_state(profile: SlicedTextEvent) -> dict | None:
    """Resolve exactly one admitted transform and apply its final paint/scale state."""
    e = profile.event
    state,moves,transforms = e.state,profile.moves,profile.transforms
    if len(transforms) != 1:
        return None
    final = state.copy()
    final_continuation = e.continuation
    allowed = {'alpha','1a','3a','blur','be'} | ({'fscx','fscy'} if not moves else set())
    transform = parse_effect_transform(transforms[0],e.duration,allowed)
    if transform is None:
        return None
    for tag,value in transform[2]:
        final_continuation = apply_override(final,tag,value,e.styles,e.defaults,final_continuation)
    return final


def _index_sliced_text_pulse(index: SlicedTextIndex, profile: SlicedTextEvent, final: dict) -> None:
    """Index borderless translucent copies that fade to invisible at a fixed anchor."""
    p = profile.event
    e,state,pos = p,p.state,profile.pos
    if (0 < state.get('1a',0) < 254 and final.get('1a',0) >= 254 and
            max(state.get(k,state.get('bord',0)) for k in ('xbord','ybord')) <= .001):
        index.pulses.setdefault((_sliced_text_layout(p,state,scaled=True),e.start,e.end,pos),[]).append((p,final))


def _index_sliced_text_tile(index: SlicedTextIndex, profile: SlicedTextEvent, final: dict) -> None:
    """Index clipped moving strips only at an opaque entrance or exit endpoint."""
    p = profile.event
    e,state,moves,pos,key = p,p.state,profile.moves,profile.pos,profile.key
    rect = rectangle_clip(p)
    if len(moves) != 1 or pos is not None or rect is None:
        return
    move = parse_effect_move(moves[0],e.duration,endpoint_slack=50)
    if move is None or math.dist(move[:2],move[2:4]) <= e.unit:
        return
    if (state.get('1a',0) >= 254 and state.get('3a',0) >= 254 and
            final.get('1a',0) == 0 and final.get('3a',0) == 0):
        phase,boundary,anchor,pose = 'in',e.end,tuple(move[2:4]),final
    elif (state.get('1a',0) == 0 and state.get('3a',0) == 0 and
            final.get('1a',0) >= 254 and final.get('3a',0) >= 254):
        phase,boundary,anchor,pose = 'out',e.start,tuple(move[:2]),state
    else:
        return
    index.tiles.setdefault((key,phase,boundary,anchor,e.start,e.end,e.layer,_sliced_text_paint(pose)),[]).append((p,rect))


def _index_sliced_text_event(index: SlicedTextIndex, profile: SlicedTextEvent) -> None:
    """Classify one resolved event as a hold, pulse or strip in the original order."""
    p = profile.event
    e,state,moves,transforms,pos,key = p,p.state,profile.moves,profile.transforms,profile.pos,profile.key
    if (not moves and not transforms and pos is not None and
            opaque_text_effect_state(state) and state.get('3a',0) == 0):
        index.holds.setdefault((key,e.start,e.end,pos),[]).append(p)
        return
    final = _sliced_text_final_state(profile)
    if final is None:
        return
    if not moves and pos is not None and 'clip' not in state:
        _index_sliced_text_pulse(index,profile,final)
        return
    _index_sliced_text_tile(index,profile,final)


def _prove_sliced_text_strip_phases(tiles: dict) -> dict:
    """Require adjacent full-width strips covering the anchor text box and border."""
    proven = {}
    for (key,phase,boundary,anchor,start,end,layer,colors),peers in tiles.items():
        first = peers[0][0]
        canvas = first.measurement.canvas
        peers.sort(key=lambda item:item[1][1])
        if (len(peers) < 3 or canvas is None or
                any(rect[0] != 0 or rect[2] != canvas[0] for e,rect in peers) or
                any(a[1][3] != b[1][1] for a,b in zip(peers,peers[1:]))):
            continue
        height = text_height(first)
        alignment = int(first.state.get('an',2))
        top = anchor[1] - ((2-(alignment-1)//3)/2)*height
        border = max(first.state.get(k,first.state.get('bord',0)) for k in ('xbord','ybord'))
        if peers[0][1][1] > top-border or peers[-1][1][3] < top+height+border:
            continue
        proven.setdefault((key,phase,boundary,anchor,colors),[]).append([e for e,rect in peers])
    return proven


def _propose_sliced_text_caption(index: SlicedTextIndex, copies: list[Event], base: Event,
                                 incoming: list[list[Event]], outgoing: list[list[Event]],
                                 start: str, end: str, pos: tuple) -> tuple[set[int],Event]:
    """Collect proven phases and matching pulses, then render the recorded hold and entrance start."""
    members = {e.source_index for e in copies+incoming[0]+outgoing[0]}
    for p,final in index.pulses.get((_sliced_text_layout(base,base.state,scaled=True),start,end,pos),[]):
        # The source is a fading copy at this exact anchor and interval.
        # Its positive starting size may be larger or smaller; the exact
        # return to the proven hold identifies it, not its amplitude.
        if (int(p.layer) >= max(int(e.layer) for e in copies) and
                all(final.get(k,100) == base.state.get(k,100) for k in ('fscx','fscy'))):
            members.add(p.source_index)
    prefix = re.match(r'(?:\{[^}]*\})*',base.text).end()
    caption = replace_event(base,text=render_simplified_caption(
                {**base.state,'fn':literal_font_spans(base)[0][1]},base.text[prefix:],measurement=base.measurement,
                source_paint=_source_caption_paint(base.state,[e.state for e in copies])),
                start=incoming[0][0].start,start_s=incoming[0][0].start_s,
                source_index=min(members))
    return members,caption


def _propose_sliced_text_replacements(index: SlicedTextIndex, proven: dict) -> list[tuple[set[int],Event]]:
    """Match each unanimous hold to exactly one complete incoming and outgoing phase."""
    proposals = []
    for (key,start,end,pos),copies in index.holds.items():
        if len({_sliced_text_paint(e.state) for e in copies}) != 1:
            continue
        base = copies[0]
        colors = _sliced_text_paint(base.state)
        incoming = proven.get((key,'in',start,pos,colors),[])
        outgoing = proven.get((key,'out',end,pos,colors),[])
        if len(incoming) != 1 or len(outgoing) != 1:
            continue
        proposals.append(_propose_sliced_text_caption(index,copies,base,incoming,outgoing,start,end,pos))
    return proposals


def _accept_sliced_text_ownership(proposals: list[tuple[set[int],Event]]) -> list[tuple[set[int],Event]]:
    """Accept proposals only when every consumed source event has a single owner."""
    owners = {}
    for members,caption in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    accepted = [(members,caption) for members,caption in proposals
                if all(owners[index] == 1 for index in members)]
    return accepted


def _group_sliced_text_cues(accepted: list[tuple[set[int],Event]], holds: dict) -> dict:
    """Group accepted captions with their original held geometry and paint."""
    held_by_id = {e.source_index:e for copies in holds.values() for e in copies}
    cues = {}
    for members,caption in accepted:
        base = next(held_by_id[i] for i in members if i in held_by_id)
        cue_key = (caption.style,caption.name,caption.start,
                   get_pos(caption.text)[1],text_layout_key(base),_sliced_text_paint(base.state))
        cues.setdefault(cue_key,[]).append((members,caption,base))
    return cues


def _adjust_sliced_text_cue_timing(peers: list, comments: list[Event], adjusted: dict[int,Event]) -> None:
    """Use complete anchor-ordered authored lyrics to adjust a cue to its held timing."""
    peers.sort(key=lambda item:get_pos(item[1].text)[0])
    if len({get_pos(c.text)[0] for ids,c,base in peers}) != len(peers):
        return
    beginning = min(base.start_s for ids,c,base in peers)
    finish = max(base.end_s for ids,c,base in peers)
    literal = ''.join(OVERRIDE_RE.sub('',c.text) for ids,c,base in peers)
    norm = lambda value: ''.join(value.split())
    if any(e.style == peers[0][1].style and e.name == peers[0][1].name and
           abs(e.start_s-beginning) <= .05 and abs(e.end_s-finish) <= .05 and
           norm(simplify_text(e.text,visible_only=True)[1]) == norm(literal)
           for e in comments):
        adjusted.update((c.source_index,replace_event(c,start=format_time(beginning),
            start_s=beginning,end=format_time(finish),end_s=finish))
            for ids,c,base in peers)


def _adjust_authored_sliced_text_timing(events: list[Event], index: SlicedTextIndex,
                                        accepted: list[tuple[set[int],Event]]) -> list[tuple[set[int],Event]]:
    """Adjust only fully proven cues with coincident authored timing and complete literal text."""
    # A matching authored lyric proves the complete cue, including fragments
    # with inline fonts that the ordinary row assembler keeps positioned.
    # Its times must coincide with the first and last held phases, and every
    # literal character must be present in anchor order. Trim decorative
    # entrances/exits to those lyric bounds rather than exposing overlapping
    # full captions during neighboring strip fades.
    cues = _group_sliced_text_cues(accepted,index.holds)
    adjusted = {}
    comments = [e for e in events if e.kind == 'Comment' and e.duration > 0]
    for peers in cues.values():
        _adjust_sliced_text_cue_timing(peers,comments,adjusted)
    return [(ids,adjusted.get(c.source_index,c)) for ids,c in accepted]


def collapse_sliced_text_sequences(events: list[Event]) -> tuple[list[Event],int]:
    """Replace a tiled entrance/held-text/exit with its recorded opaque text.

    Adjacent full-width strips must cover the held text's vertical box and
    converge to, or depart from, its exact anchor at touching phase boundaries.
    Both complete strip phases prove the effect. Matching translucent size
    pulses are decoration; unrelated copies and incomplete tiles stay intact.
    """
    families = _eligible_sliced_text_families(events)
    if not families:
        return events,0
    index = SlicedTextIndex({},{},{})
    for e in events:
        profile = _profile_sliced_text_event(e,families)
        if profile is not None:
            _index_sliced_text_event(index,profile)
    proven = _prove_sliced_text_strip_phases(index.tiles)
    proposals = _propose_sliced_text_replacements(index,proven)
    accepted = _accept_sliced_text_ownership(proposals)
    if not accepted:
        return events,0
    accepted = _adjust_authored_sliced_text_timing(events,index,accepted)
    consumed = set().union(*(members for members,caption in accepted))
    output = [e for e in events if e.source_index not in consumed]
    output.extend(caption for members,caption in accepted)
    return sorted(output,key=lambda e:e.source_index),len(events)-len(output)


def index_fragment_spans(fragments: Iterable[str], *, casefold: bool = False) -> tuple:
    """Index literal text at recorded fragment boundaries without a length cap."""
    words, starts, ends = [], {}, {}
    offset = 0
    for index,fragment in enumerate(fragments):
        word = ''.join(fragment.split())
        if casefold:
            word = word.casefold()
        words.append(word)
        starts.setdefault(offset,[]).append(index)
        offset += len(word)
        ends.setdefault(offset,[]).append(index)
    return ''.join(words),starts,ends


def matching_fragment_spans(index: tuple, target: str):
    """Yield complete contiguous fragments spelling an already normalized target."""
    if not target:
        return
    text,starts,ends = index
    offset = text.find(target)
    while offset >= 0:
        for first in starts.get(offset,()):
            for last in ends.get(offset+len(target),()):
                if first <= last:
                    yield first,last
        offset = text.find(target,offset+1)


def _word_echo_layout(e: Event) -> tuple:
    """Match authored paragraph geometry independently of paint and position."""
    return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement,
            text_layout_key(e))


def _word_echo_families(events: list[Event]) -> Iterable[list[Event]]:
    """Collect nearby frame copies before testing the entire displacement box."""
    components = []
    for e in sorted(events,key=lambda e:(e.start_s,e.end_s,e.source_index)):
        pos = get_pos(e.text)
        for component,end in reversed(components):
            first = component[0]
            if (e.start_s <= end[0]+1e-6 and
                    all(abs(a-b) <= .25*text_height(first)
                        for a,b in zip(pos,get_pos(first.text)))):
                component.append(e)
                end[0] = max(end[0],e.end_s)
                break
        else:
            components.append(( [e], [e.end_s] ))
    for component,_ in components:
        yield component


def _prove_word_echo_family(members: list[Event]) -> bool:
    """Prove dense short fade frames or faint copies with repeated jitter."""
    frames = {}
    height = text_height(members[0])
    positions = [get_pos(e.text) for e in members]
    if any(max(p[axis] for p in positions)-min(p[axis] for p in positions)
           > .06*height+1e-6 for axis in (0,1)):
        return False
    for e in members:
        frames.setdefault((e.start_s,e.end_s),[]).append(e)
    ordered = sorted(frames)
    if (len(ordered) < 3 or len(members) < 8 or any(abs(a[1]-b[0]) > 1e-6
                               for a,b in zip(ordered,ordered[1:]))):
        return False
    alphas,centers = [],[]
    for interval in ordered:
        copies = frames[interval]
        values = {e.state.get('1a',0) for e in copies}
        if len(values) != 1:
            return False
        alphas.append(values.pop())
        centers.append(tuple(statistics.mean(get_pos(e.text)[axis] for e in copies)
                             for axis in (0,1)))
    fade = (alphas[0] <= 128 and alphas[-1] >= 224 and
            alphas[-1]-alphas[0] >= 64 and
            all(a <= b for a,b in zip(alphas,alphas[1:])))
    reversals = 0
    for axis in (0,1):
        signs = [1 if b[axis] > a[axis] else -1 for a,b in zip(centers,centers[1:])
                 if abs(b[axis]-a[axis]) > .001*height]
        reversals = max(reversals,sum(a != b for a,b in zip(signs,signs[1:])))
    return fade or (min(alphas) >= 128 and reversals >= 2)


def _owned_word_echo_anchors(caption: Event, literal: str, word: str,
                              metric: FontMetrics) -> list[float]:
    """Disambiguate repeated literal occurrences with the retained exact font."""
    unit = .06*text_height(caption)
    glyphs = authored_glyph_positions(metric,caption.state,literal,
                                      get_pos(caption.text)[0],unit)
    if glyphs is None:
        return []
    index = index_fragment_spans(c for c,_ in glyphs)
    # The shared index ignores spaces. Keep only actual contiguous literals;
    # a word must not match letters on opposite sides of an authored space.
    occurrences = set()
    offset = literal.find(word)
    while offset >= 0:
        occurrences.add(sum(not c.isspace() for c in literal[:offset]))
        offset = literal.find(word,offset+1)
    anchors = []
    for first,last in matching_fragment_spans(index,word):
        if first not in occurrences:
            continue
        xs = [x for _,x in glyphs[first:last+1]]
        fragments = [c for c,_ in glyphs[first:last+1]]
        anchor = fit_fragment_anchor(metric,caption.state,xs,fragments,word,unit,
                                     exact_size=True,allow_tracking=True)
        if anchor is not None:
            anchors.append(anchor)
    return anchors


def remove_owned_word_echoes(events: list[Event], visible_map: dict[int,str],
                              captions: tuple[Event,...], sources: dict[int,Event],
                              metric: FontMetrics | None, *, max_piece_duration: float=.16
                              ) -> CoveredFragmentRemoval:
    """Atomically remove original word frames owned by one accepted full line.

    Exact font/layout/position, dense fade or jitter evidence, and one cue owner
    are required. Missing fonts or competing ownership preserve the family.
    Faint tails may follow the parent; they never extend its caption interval.
    """
    if not captions or metric is None or not metric.available:
        return CoveredFragmentRemoval(events,[],0)
    owners = {}
    for caption in captions:
        owners.setdefault(_word_echo_layout(caption),[]).append(caption)
    owner_styles = {caption.style for caption in captions}
    buckets = {}
    for e in events:
        source = sources.get(e.source_index)
        literal = visible_map.get(e.source_index,'')
        if source is not None and source.style in owner_styles and not source.state:
            evaluated = event_evaluation(source)
            source = dataclass_replace(source,state=evaluated.formatting,
                                       continuation=evaluated.continuation)
        if (source is None or not literal or any(c.isspace() for c in literal) or
                source.duration <= 0 or source.duration > max_piece_duration+1e-6 or
                source.start_s != e.start_s or source.end_s != e.end_s or
                get_pos(source.text) is None or inline_layout_key(source) or
                any(k in source.state for k in ('clip','iclip','org')) or
                not unrotated_text_state(source.state) or source.state.get('p',0) or
                source.state.get('borderstyle',1) != 1 or
                not math.isfinite(text_height(source)) or text_height(source) <= 0 or
                any(not math.isfinite(v) for v in get_pos(source.text))):
            continue
        layout = _word_echo_layout(source)
        if layout not in owners:
            continue
        obj = static_object_key(source,source.styles)
        if obj is None or len(obj[-1]) != 1 or obj[-1][0][1] or obj[-1][0][2] != literal:
            continue
        paint = tuple((k,source.state.get(k,DEFAULT_STATE.get(k))) for k in
                      ('1c','2c','3c','4c','bord','xbord','ybord','shad','blur','be'))
        buckets.setdefault((layout,literal,source.layer,paint),[]).append(source)
    removed,anchors = set(),{}
    for (layout,word,_,_),bucket in buckets.items():
        for members in _word_echo_families(bucket):
            if not _prove_word_echo_family(members):
                continue
            start,end = min(e.start_s for e in members),max(e.end_s for e in members)
            matches = []
            for caption in owners[layout]:
                literal = visible_map.get(caption.source_index,'')
                if (literal == word or start < caption.start_s-1e-6 or
                        start >= caption.end_s or end > caption.end_s+.8+1e-6 or
                        min(end,caption.end_s)-start < min(.16,.5*(end-start)) or
                        any(e.end_s > caption.end_s+1e-6 and e.state.get('1a',0) < 128
                            for e in members)):
                    continue
                key = (caption.source_index,word)
                if key not in anchors:
                    anchors[key] = _owned_word_echo_anchors(caption,literal,word,metric)
                unit = .06*text_height(caption)
                y = get_pos(caption.text)[1]
                for x in anchors[key]:
                    if all(abs(get_pos(e.text)[0]-x) <= unit+1e-6 and
                           abs(get_pos(e.text)[1]-y) <= unit+1e-6 for e in members):
                        matches.append(caption)
            if len(matches) == 1:
                removed.update(e.source_index for e in members)
    return CoveredFragmentRemoval([e for e in events if e.source_index not in removed],
                                   [],len(removed))


def match_repeated_glyph_flashes(
    events: list[Event], words: dict[int, str], positions: dict[int, tuple[float, float] | None],
    metric: FontMetrics | None, *, font_report: FontProcessingReport | None=None,
) -> set[int]:
    """Prove complete repeated colour flashes over a held text row.

    Use the retained fragment geometry and exact font, including the existing
    font-size calibration for separately authored glyphs. A whole family must
    repeat every glyph, vary its paint, and stay within the foreground cue.
    Fixed same-layer flashes also qualify after their fades have been stripped.
    Return membership only; the held text, paint and timing remain untouched.
    """
    if metric is None or not metric.available:
        return set()
    paint = {'c','1c','2c','3c','4c','bord','xbord','ybord','blur','be'}
    parents, flashes = {}, {}
    for e in events:
        text,pos = words.get(e.source_index,''),positions.get(e.source_index)
        if (e.kind != 'Dialogue' or not text or pos is None or e.duration <= 0 or
                e.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'} or
                not e.layer.lstrip('-').isdigit() or
                any(not math.isfinite(v) for v in (*pos,e.start_s,e.end_s))):
            continue
        evaluated = event_evaluation(e)
        state = evaluated.formatting
        sample = dataclass_replace(e,state=state,continuation=evaluated.continuation)
        inline = inline_layout_key(sample)
        profile = static_text_paint_geometry(sample,paint) if inline else None
        if (state.get('p',0) or state.get('borderstyle',1) != 1 or
                inline and (profile is None or len(profile[0]) != 1) or
                not unrotated_text_state(state) or
                any(k in state for k in ('clip','iclip','org')) or
                any(abs(state.get(k,0)) > .001 for k in ('fax','fay'))):
            continue
        tokens = event_override_tokens(e)
        if any(tag in {'move','fade','k','kf','ko','kt'} for tag,value in tokens):
            continue
        transforms = [value for tag,value in tokens if tag == 't']
        if any(parse_effect_transform(value,e.duration,paint,allow_after_end=True) is None
               for value in transforms):
            continue
        layout = tuple((k,str(v).casefold() if k == 'fn' else v)
                       for k,v in text_layout_key(sample) if k != 'q')
        key = (e.style,e.name,placement_key(sample)[0],layout)
        border = max(state.get(k,state.get('bord',0)) for k in ('xbord','ybord'))
        if (len(text) == 1 and not text.isspace() and border == 0 and
                not transforms and not unicodedata.combining(text) and
                unicodedata.bidirectional(text) not in {'R','AL','AN'}):
            flashes.setdefault(key,{}).setdefault(e.layer,[]).append(sample)
        elif border > 0 and state.get('1a',0) == 0:
            parents.setdefault((key,e.layer,e.start,e.end,pos[1]),[]).append(sample)
    indexes = {}
    for key,layers in flashes.items():
        indexes[key] = []
        for peers in layers.values():
            peers.sort(key=lambda e:e.start_s)
            indexes[key].append(([e.start_s for e in peers],peers))
    proposals = []
    for (key,layer,start,end,y),row in parents.items():
        if key not in indexes or sum(len(''.join(words[e.source_index].split())) for e in row) < 3:
            continue
        row.sort(key=lambda e:positions[e.source_index][0])
        if len({positions[e.source_index][0] for e in row}) != len(row):
            continue
        first = row[0]
        for starts,peers in indexes[key]:
            candidates = [e for e in peers[bisect_left(starts,first.start_s-1e-6):
                                           bisect_right(starts,first.end_s)]
                          if e.end_s <= first.end_s+1e-6 and e.duration <= .25*first.duration and
                             abs(positions[e.source_index][1]-y) <= first.unit]
            slots = {}
            for e in candidates:
                slots.setdefault((positions[e.source_index][0],words[e.source_index]),[]).append(e)
            if not slots or any(len(group) < 3 or
                    len({e.state.get('1c') for e in group}) < 3 or
                    max(e.end_s for e in group)-min(e.start_s for e in group) < .5*first.duration
                    for group in slots.values()):
                continue
            ordered = sorted(slots)
            ownership = [0]*len(ordered)
            complete = True
            for parent in row:
                text = words[parent.source_index]
                target = ''.join(text.split())
                px,py = positions[parent.source_index]
                options = []
                for i in range(len(ordered)-len(target)+1):
                    span = ordered[i:i+len(target)]
                    if ''.join(c for x,c in span) != target:
                        continue
                    xs = [x for x,c in span]
                    if any(b-a <= first.unit for a,b in zip(xs,xs[1:])):
                        continue
                    if not any(c.isspace() for c in text):
                        anchor = fit_fragment_anchor(metric, parent.state,xs,list(target),text,
                                                        parent.unit,allow_tracking=True,separate_glyphs=True,
                                                        max_size_error=.1)
                        fits = anchor is not None and abs(anchor-px) <= 1.5*parent.unit
                    else:
                        glyphs = [slots[slot][0] for slot in span]
                        fit = recover_font_row(metric, glyphs,list(target),max_size_error=.1, font_report=font_report)
                        fits = (fit is not None and ' '.join(fit[0].split()) == ' '.join(text.split()) and
                                (int(parent.state.get('an',5))-1)%3 == 1 and
                                abs(fit[1]-px) <= max(1.5*parent.unit,.1*text_height(parent)))
                    if fits:
                        options.append(i)
                if len(options) != 1:
                    complete = False; break
                for i in range(options[0],options[0]+len(target)):
                    ownership[i] += 1
            if complete and all(n == 1 for n in ownership):
                proposals.append({e.source_index for group in slots.values() for e in group})
    owners = {}
    for members in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    return {index for members in proposals if all(owners[i] == 1 for i in members)
            for index in members}


def _index_source_fragment_events(events: list[Event], words: dict[int,str], positions: dict) -> dict:
    """Index the last source for each identity when it has an authored word and position."""
    parsed = {e.source_index:e for e in events}
    indexed: dict[tuple,list[Event]] = {}
    for e in parsed.values():
        if positions.get(e.source_index) is not None and words.get(e.source_index):
            indexed.setdefault((e.style,e.name,e.margin_l,e.margin_r,e.margin_v),[]).append(e)
    return indexed


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


def _prove_source_fragment_visibility(row: TextRow, removed: set[int]) -> bool | None:
    """Require layered full-row visibility and remove alternate phases only after complete coverage."""
    # Short rows may prove complete particle phases, but retain the older
    # minimum for the broader layered-effect and foreground-paint rules.
    if (sum(len(''.join(word.split())) for _,word,_ in row.pieces) < 8 or
            len({paint_row[0].layer for paint_row in row.paint_rows}) < 2):
        return None
    first = row.base
    phases = _index_source_fragment_visibility(row)
    alternating = any(profile != ((first.start_s,first.end_s),) for profile in phases)
    if alternating:
        # Different segmentations can replace each other during a cue.
        # Require complete, nonoverlapping visibility and layered text
        # in every phase; a partial row cannot prove full-cue coverage.
        if (len(phases) < 2 or any(len({paint_row[0].layer for paint_row in peers}) < 2
                                  for peers in phases.values())):
            return None
        spans = sorted(span for profile in phases for span in profile)
        cursor = first.start_s
        complete = True
        for start,end in spans:
            if abs(start-cursor) > .001:
                complete = False
                break
            cursor = end
        if not complete or abs(cursor-first.end_s) > .001:
            return None
        selected = first.evidence.opaque_spans
        assert selected is not None, "Alternating source rows require visibility evidence"
        removed.update(e.source_index for profile,peers in phases.items()
                       if profile != selected for paint_row in peers for e in paint_row)
    return alternating


def _prepare_source_fragment_row(row: TextRow) -> SourceFragmentRowContext:
    """Retain authored glyph anchors, contiguous fragment indexing and per-row syllable cache."""
    first = row.base
    chosen = [e for e, _, _ in row.pieces]
    height = text_height(first)
    anchors = row.source_anchors
    # A highlight may spell several separately positioned glyphs.
    # Retain their original anchors before paint-based reconstruction
    # divides a gradient into differently coloured caption fragments.
    span_index = index_fragment_spans(word for _,word,_ in row.pieces)
    gaps = [0]
    for left,right in zip(row.pieces,row.pieces[1:]):
        gaps.append(gaps[-1]+(right[2][0]-left[2][0] > 2*height))
    syllables = {}
    top_layer = max(int(paint_row[0].layer) if paint_row[0].layer.lstrip('-').isdigit()
                    else 0 for paint_row in row.paint_rows)
    layout_tags = ({tag for tag,_ in text_layout_key(first)} - {'fscx','fscy'} |
                   {'a','r','fr','pos','move','clip','iclip','p'})
    return SourceFragmentRowContext(row,first,chosen,height,anchors,span_index,gaps,syllables,top_layer,layout_tags)


def _profile_source_fragment_candidate(e: Event, context: SourceFragmentRowContext, words: dict[int,str], positions: dict, animated_sources: set[int]) -> SourceFragmentCandidate | None:
    """Admit candidate lifetimes and resolve source state before the independent matching proofs."""
    delayed = context.first.end_s <= e.start_s <= context.first.end_s+.25*context.first.duration
    if not (context.first.start_s-.001 <= e.start_s and
            (e.start_s < context.first.end_s or delayed and e.source_index in animated_sources)):
        return None
    pos = positions[e.source_index]
    nearby = [anchor for anchor in context.anchors.get(words[e.source_index],[]) if
              abs(pos[0]-anchor[0]) <= context.height and abs(pos[1]-anchor[1]) <= .25*context.height]
    evaluated = event_evaluation(e)
    state = evaluated.formatting
    e.state = state
    e.continuation = evaluated.continuation
    return SourceFragmentCandidate(e,pos,nearby,state,delayed)


def _source_fragment_syllable_matches(context: SourceFragmentRowContext, target: str, pos: tuple) -> list:
    """Cache matching authored fragment spans, stopping once two nearby occurrences prove ambiguity."""
    query = (target,pos)
    if query not in context.syllables:
        matches = []
        # Search only the actual effect text, not all quadratic
        # combinations of a long row. Consider every occurrence,
        # but two nearby matches already establish ambiguity.
        for start,end in matching_fragment_spans(context.span_index,target):
            if context.gaps[start] != context.gaps[end]:
                continue
            a,b = context.row.pieces[start][2],context.row.pieces[end][2]
            anchor = ((a[0]+b[0])/2,(a[1]+b[1])/2)
            if (abs(pos[0]-anchor[0]) <= .12*context.height and
                    abs(pos[1]-anchor[1]) <= .06*context.height):
                matches.append(anchor)
                if len(matches) == 2:
                    break
        context.syllables[query] = matches
    matches = context.syllables[query]
    return matches


def _match_source_fragment_highlight(candidate: SourceFragmentCandidate, context: SourceFragmentRowContext, words: dict[int,str], animated_sources: set[int], removed: set[int]) -> None:
    """Remove only a uniquely matched nested animated highlight above an existing layered row."""
    e,pos,state = candidate.event,candidate.pos,candidate.state
    # This proof removes only a nested animated copy above an
    # existing layered row. It does not confirm a dense fade family
    # or normalize the underlying row's gradient paint.
    if (e.source_index in animated_sources and e.duration < context.first.duration-.011 and
            e.end_s <= context.first.end_s and e.start_s >= context.first.start_s and
            (int(e.layer) if e.layer.lstrip('-').isdigit() else 0) > context.top_layer and
            state.get('1a',0) < 128 and not state.get('p',0) and
            'clip' not in state and 'iclip' not in state and
            not inline_layout_key(e) and text_layout_key(e) == text_layout_key(context.first) and
            not re.search(r'\\(?:move|org)\s*\(',e.text,re.I)):
        transforms = [value for block in OVERRIDE_RE.findall(e.text)
                      for tag,value in tokenize_override(block) if tag == 't']
        moving = any(tag in context.layout_tags for value in transforms
                     for tag,_ in tokenize_override(value))
        target = ''.join(words[e.source_index].split())
        matches = _source_fragment_syllable_matches(context,target,pos)
        if not moving and len(matches) == 1:
            removed.add(e.source_index)


def _source_fragment_nearby_anchors(candidate: SourceFragmentCandidate, context: SourceFragmentRowContext, words: dict[int,str], animated_sources: set[int]) -> tuple[list,dict]:
    """Keep the existing distant-origin proof for rising transparent shrinking glyph copies."""
    e,pos,nearby,state = candidate.event,candidate.pos,candidate.nearby,candidate.state
    # Some fade copies rise and shrink about a distant origin. The
    # unchanged x anchor, explicit transparency and smaller scale tie
    # them to the same glyph even after they leave the baseline.
    if not nearby and e.source_index in animated_sources:
        origin = re.search(r"\\org\(\s*("+NUM+r")\s*,\s*("+NUM+r")",e.text,re.I)
        if origin:
            state = effective_state(e.text,e.defaults,e.styles)
            if (state.get("1a",0) > 0 and state.get("fscx",100) <= context.first.state.get("fscx",100)
                    and abs(float(origin[2])-pos[1]) > 20*context.height):
                nearby = [p for p in context.anchors.get(words[e.source_index],[]) if
                          abs(pos[0]-p[0]) <= .06*context.height and
                          abs(float(origin[1])-p[0]) <= .06*context.height and
                          abs(pos[1]-p[1]) <= 2*context.height]
    return nearby,state


def _source_fragment_layout_matches(state: dict, first: Event) -> bool:
    """Require compatible glyph font, size, alignment and unclipped nondrawing paint."""
    if (state.get("p",0) or "clip" in state or "iclip" in state or
            str(state.get("fn","")).casefold() != str(first.state.get("fn","")).casefold() or
            abs(state.get("fs",75)-first.state.get("fs",75)) > .05*first.state.get("fs",75) or
            any(state.get(k,DEFAULT_STATE.get(k)) != first.state.get(k,DEFAULT_STATE.get(k))
                for k in ("b","i","an"))):
        return False
    return True


def _source_fragment_delayed_particle_is_safe(candidate: SourceFragmentCandidate, state: dict, context: SourceFragmentRowContext, row_evidence: list[TextRow], words: dict[int,str], positions: dict) -> bool:
    """Require an actual fade and give a matching later stable row ownership of its glyph."""
    e,pos = candidate.event,candidate.pos
    # Delayed particles must actually fade. A new opaque lyric at
    # the same position is never an old row's decorative tail.
    if state.get("1a",0) <= 0 or not re.search(r"\\(?:move|fad|t)\(",e.text,re.I):
        return False
    # A matching anchor in a later stable row takes precedence;
    # repeated syllables alone cannot identify their owner.
    if any(other[0].start_s > context.first.start_s and
           other[0].start_s <= e.start_s < other[0].end_s and
           other[0].style == context.first.style and other[0].name == context.first.name and
           any(words[g.source_index] == words[e.source_index] and
               math.dist(positions[g.source_index],pos) <= .06*context.height for g in other)
           for peer in row_evidence for other in peer.paint_rows):
        return False
    return True


def _collect_source_fragment_candidates(context: SourceFragmentRowContext, indexed: dict, row_evidence: list[TextRow], words: dict[int,str], positions: dict, animated_sources: set[int], removed: set[int]) -> SourceFragmentEvidence:
    """Run highlight and particle safeguards before collecting dense-family paint evidence."""
    first = context.first
    candidates,evidence = [],set()
    for e in indexed.get((first.style,first.name,first.margin_l,first.margin_r,first.margin_v),[]):
        candidate = _profile_source_fragment_candidate(e,context,words,positions,animated_sources)
        if candidate is None:
            continue
        _match_source_fragment_highlight(candidate,context,words,animated_sources,removed)
        nearby,state = _source_fragment_nearby_anchors(candidate,context,words,animated_sources)
        if not nearby or not _source_fragment_layout_matches(state,first):
            continue
        if candidate.delayed and not _source_fragment_delayed_particle_is_safe(
                candidate,state,context,row_evidence,words,positions):
            continue
        pos = candidate.pos
        if e.source_index in animated_sources:
            anchor = min(nearby,key=lambda p:math.dist(p,pos))
            evidence.add((words[e.source_index],anchor[0]))
            candidates.append(e)
        elif (e.end_s <= first.end_s+.001 and any(math.dist(pos,p) <= .06*context.height for p in nearby)):
            candidates.append(e)
    return SourceFragmentEvidence(candidates,evidence)


def _select_source_fragment_foreground(row: TextRow, context: SourceFragmentRowContext, matched: SourceFragmentEvidence, alternating: bool, animated_sources: set[int], removed: set[int]) -> list[Event] | None:
    """Confirm only a dense nonalternating family, retaining static foreground paint and base sources."""
    candidates,evidence = matched.candidates,matched.evidence
    # Ordinary layered signs and isolated highlights are insufficient.
    if (alternating or len(evidence) < max(3, math.ceil(len(context.chosen)/2)) or
            sum(e.source_index in animated_sources for e in candidates) < 3*len(evidence)):
        return
    # Static foreground highlight paint provides the fill, while the base
    # row supplies geometry and timing. Use one paint across the whole row.
    paints = [e for e in candidates if e.source_index not in animated_sources]
    if not paints:
        paints = [e for paint_row in row.paint_rows for e in paint_row]
    kept = {e.source_index for e in context.chosen}
    removed.update(e.source_index for e in candidates if e.source_index not in kept)
    return paints


def remove_source_fragment_effects(
    events: list[Event], row_evidence: list[TextRow], words: dict[int, str],
    positions: dict[int, tuple[float, float] | None], animated_sources: set[int] | None=None, *,
    font_metrics: FontMetrics | None=None, font_report: FontProcessingReport | None=None,
) -> SourceFragmentRemoval:
    """Remove effects proven by original source rows and visibility phases.

    Use source text and anchors before freezing or coalescing glyph lifetimes.
    Return stable-row confirmation and foreground paint in independent row
    successors for reconstruction. Ambiguous or incomplete evidence stays
    intact. Source events and all supplied row containers are borrowed.
    """
    # Candidate profiling lazily resolves formatting. Isolate only unresolved
    # events, without resolving them earlier or changing matching order. Reuse
    # one successor for every reference to the same authored object.
    sources = {id(e):e for e in events}
    for row in row_evidence:
        sources[id(row.base)] = row.base
        for e,_,_ in row.pieces:
            sources[id(e)] = e
        for paint_row in row.paint_rows:
            sources.update((id(e),e) for e in paint_row)
        sources.update((id(e),e) for e in row.foreground)
    successors = {key:dataclass_replace(e,state={},continuation=OverrideContinuation()) for key,e in sources.items() if not e.state}
    events = [successors.get(id(e),e) for e in events]
    rows = [dataclass_replace(row,
        base=successors.get(id(row.base),row.base),
        pieces=[(successors.get(id(e),e),word,pos) for e,word,pos in row.pieces],
        paint_rows=[[successors.get(id(e),e) for e in paint_row] for paint_row in row.paint_rows],
        source_anchors={word:list(anchors) for word,anchors in row.source_anchors.items()},
        foreground=[successors.get(id(e),e) for e in row.foreground]) for row in row_evidence]
    animated_sources = animated_sources or set()
    indexed = _index_source_fragment_events(events,words,positions)
    removed = match_translucent_glyph_particles(events,rows,words,animated_sources)
    removed.update(match_repeated_glyph_flashes(events,words,positions,font_metrics, font_report=font_report))
    paint_families=[]
    for index,row in enumerate(rows):
        alternating = _prove_source_fragment_visibility(row,removed)
        if alternating is None:
            continue
        context = _prepare_source_fragment_row(row)
        matched = _collect_source_fragment_candidates(
            context,indexed,rows,words,positions,animated_sources,removed)
        foreground = _select_source_fragment_foreground(
            row,context,matched,alternating,animated_sources,removed)
        if foreground is not None:
            rows[index] = dataclass_replace(row,foreground=foreground,confirmed=True)
        paint_families.append(rows[index])
    output,pulses = collapse_backed_glyph_pulses(
        [e for e in events if e.source_index not in removed],words,positions,font_metrics)
    output,slices = collapse_sliced_text_sequences(output)
    return SourceFragmentRemoval(output,rows,len(removed)+pulses+slices,paint_families)


def nearby_boundary_groups(index: dict, key: tuple, boundary: float) -> list[tuple[float,list]]:
    """Look up whole phase groups within 50 ms of a caption boundary.

    Groups retain their authored times. Query a fixed boundary rather than
    chaining nearby times, which could join separate repetitions.
    """
    times, groups = index.get(key, ([], {}))
    slack = .05+1e-6
    left = bisect_left(times, boundary-slack)
    right = bisect_right(times, boundary+slack)
    return [(time,groups[time]) for time in times[left:right]]


def _boundary_glyph_geometry(e: Event, y: float) -> tuple:
    return (e.style,e.name,placement_key(e),y,
            tuple((k,v) for k,v in text_layout_key(e)
                  if k not in {'frz','frx','fry'}))


def _boundary_glyph_caption_key(e: Event, original: Event, word: str, pos: tuple | None):
    """Admit an opaque upright word anchored at its original source position."""
    if (e.duration > 0 and word and pos is not None and upright_text_state(e.state) and
            e.state.get('1a',0) == 0 and not any(c.isspace() for c in word) and
            not any(k in e.state for k in ('clip','iclip','org')) and
            get_pos(original.text) == pos):
        return _boundary_glyph_geometry(e,pos[1])
    return None


def _parse_simple_source_fade(tokens: list):
    """Require exactly one finite nonnegative two-part fad and no fade."""
    fades = [value for tag,value in tokens if tag == 'fad']
    if len(fades) != 1 or any(tag == 'fade' for tag,value in tokens):
        return None
    try:
        fade = [float(v) for v in fades[0].strip('()').split(',')]
    except ValueError:
        return None
    if len(fade) != 2 or not all(math.isfinite(v) and v >= 0 for v in fade):
        return None
    return fade


def _classify_boundary_glyph_phase(original: Event, state: dict, tokens: list, fade: list, unit: float, *,
                                    continuation: OverrideContinuation):
    """Classify a fading rotation into an upright entrance or a moving flying exit."""
    moves = [value for tag,value in tokens if tag == 'move']
    transforms = [value for tag,value in tokens if tag == 't']
    phase = None
    if not moves and len(transforms) == 1 and get_pos(original.text) is not None:
        transform = parse_effect_transform(transforms[0],original.duration,
                                           {'fr','frz','frx','fry','blur','be'})
        if transform is None:
            return None
        begin,end,changes = transform
        final = state.copy()
        final_continuation = continuation
        for tag,value in changes:
            final_continuation = apply_override(final,tag,value,original.styles,original.defaults,final_continuation)
        # Source fade parameters may finish one frame beyond the record,
        # matching exit validation. The event boundary itself stays exact.
        if (unrotated_text_state(state) or not unrotated_text_state(final) or
                not 0 < fade[0] <= 1000*original.duration+50 or fade[1] != 0):
            return None
        phase,boundary,pos = 'entrance',original.end_s,get_pos(original.text)
    elif len(moves) == 1 and not transforms and unrotated_text_state(state):
        move = parse_effect_move(moves[0],original.duration,endpoint_slack=50)
        if (move is None or math.dist(move[:2],move[2:4]) < unit or
                get_pos(original.text) is not None or
                fade[0] != 0 or not 0 < fade[1] <= 1000*original.duration+50):
            return None
        phase,boundary,pos = 'exit',original.start_s,tuple(move[:2])
    return (phase,boundary,pos) if phase is not None else None


def _profile_boundary_glyph_source(original: Event, unit: float):
    """Require one authored glyph and supported opaque geometry before phase classification."""
    glyph = simplify_text(original.text,visible_only=True)[1]
    if (len(glyph) != 1 or glyph.isspace() or unicodedata.combining(glyph) or
            original.duration <= 0):
        return None
    tokens = event_override_tokens(original)
    evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
    state = evaluated.formatting
    if (not opaque_text_effect_state(state) or
            any(abs(state.get(k,0)) > .001 for k in ('fax','fay'))):
        return None
    fade = _parse_simple_source_fade(tokens)
    if fade is None:
        return None
    classified = _classify_boundary_glyph_phase(original,state,tokens,fade,unit,continuation=evaluated.continuation)
    if classified is None:
        return None
    phase,boundary,pos = classified
    return BoundaryGlyphPhase(phase,boundary,pos,state,glyph,evaluated.continuation)


def _boundary_glyph_protection(e: Event, original: Event, word: str, phase: str, pos: tuple, glyph: str):
    """Protect an absorbed held entrance; reject extended sources without that proof."""
    if e.duration > original.duration+.001:
        # A one-letter syllable may already include its entrance in
        # the retained cue. It proves its slot but must never be
        # removed along with its decorative peers. Compare source
        # coverage instead of guessing from the event's duration.
        if (phase != 'entrance' or word != glyph or get_pos(e.text) != pos or
                not upright_text_state(e.state) or e.state.get('1a',0) != 0):
            return None
        return True
    return False


def _index_boundary_glyph_events(events: list[Event], visible_map: dict[int,str], source_events: dict[int,Event]):
    """Collect retained caption candidates, classified effects and protected source IDs."""
    groups, captions = {}, {}
    caption_candidates = []
    boundary_sources, protected = set(), set()
    for e in events:
        original = source_events.get(e.source_index)
        if original is None or e.kind != 'Dialogue' or inline_layout_key(original):
            continue
        word = visible_map.get(e.source_index,'')
        pos = get_pos(e.text)
        key = _boundary_glyph_caption_key(e,original,word,pos)
        if key is not None:
            caption_candidates.append((e,key))
        profile = _profile_boundary_glyph_source(original,e.unit)
        if profile is None:
            continue
        phase,boundary,pos = profile.phase,profile.boundary,profile.pos
        source = dataclass_replace(original,state=profile.state,continuation=profile.continuation)
        key = (phase,_boundary_glyph_geometry(source,pos[1]))
        boundary_sources.add(e.source_index)
        protect = _boundary_glyph_protection(e,original,word,phase,pos,profile.glyph)
        if protect is None:
            continue
        if protect:
            protected.add(e.source_index)
            captions.setdefault(key,{}).setdefault(boundary,[]).append(e)
        groups.setdefault((key,boundary),[]).append((e,pos,profile.glyph))
    return BoundaryGlyphIndex(groups,captions,caption_candidates,boundary_sources,protected)


def _index_boundary_glyph_captions(index: BoundaryGlyphIndex):
    """Index independent held captions and protected absorbed phases at both boundaries."""
    # A long frozen entrance is still an entrance, not another held word.
    # Only a source-independent caption or an absorbed held phase can prove
    # the destination. This distinction also permits genuinely brief holds.
    for e,key in index.caption_candidates:
        if e.source_index not in index.boundary_sources or e.source_index in index.protected:
            for phase,boundary in (('entrance',e.start_s),('exit',e.end_s)):
                index.captions.setdefault((phase,key),{}).setdefault(boundary,[]).append(e)

    return {key:(sorted(phases),phases) for key,phases in index.captions.items()}


def _match_boundary_glyph_words(key: tuple, boundary: float, peers: list, caption_index: dict, visible_map: dict[int,str]):
    """Match the complete ordered glyph sequence to nearby words using each closest source anchor once."""
    nearby = nearby_boundary_groups(caption_index,key,boundary)
    # An absorbed one-letter entrance can appear at both its emitted and
    # original stable boundary. Use its closest anchor once; independent
    # nearby repetitions retain distinct source IDs and fail the proof.
    candidates = {}
    for time,words in nearby:
        for e in words:
            previous = candidates.get(e.source_index)
            if previous is None or abs(time-boundary) < abs(previous[0]-boundary):
                candidates[e.source_index] = (time,e)
    times = [time for time,e in candidates.values()]
    if not times or max(times)-min(times) > .05+1e-6:
        return None
    words = sorted((e for time,e in candidates.values()),key=lambda e:get_pos(e.text)[0])
    if (sum(len(visible_map[e.source_index]) for e in words) != len(peers) or
            len(peers) < 3 or len({pos[0] for e,pos,char in peers}) != len(peers) or
            ''.join(visible_map[e.source_index] for e in words) != ''.join(c for e,p,c in peers)):
        return None
    return words


def _fit_boundary_glyph_words(
    peers: list, words: list[Event], visible_map: dict[int, str], metric: FontMetrics,
):
    """Fit every authored word anchor with the exact font and original tracking allowance."""
    offset = 0
    for word in words:
        text = visible_map[word.source_index]
        letters = peers[offset:offset+len(text)]
        offset += len(text)
        anchor = fit_fragment_anchor(metric, word.state,[p[0] for e,p,c in letters],
                                       [c for e,p,c in letters],text,word.unit,
                                       allow_tracking=True)
        if anchor is None or abs(anchor-get_pos(word.text)[0]) > 1.5*word.unit:
            return False
    return True


def _collect_boundary_glyph_proposals(
    index: BoundaryGlyphIndex, caption_index: dict, visible_map: dict[int, str],
    metric: FontMetrics,
):
    """Build complete boundary proposals only after literal and font-anchor proofs."""
    proposals = []
    for (key,boundary),peers in index.groups.items():
        peers.sort(key=lambda item:item[1][0])
        words = _match_boundary_glyph_words(key,boundary,peers,caption_index,visible_map)
        if words is None or not _fit_boundary_glyph_words(peers,words,visible_map,metric):
            continue
        proposals.append((key[0],peers,words))
    return proposals


def _resolve_boundary_glyph_ownership(proposals: list, protected: set[int]):
    """Require unique effect ownership and one caption owner per phase, retaining protected glyphs."""
    effect_owners, caption_owners = {}, {}
    for phase,peers,words in proposals:
        for e,p,c in peers:
            effect_owners[e.source_index] = effect_owners.get(e.source_index,0)+1
        for e in words:
            owner = (phase,e.source_index)
            caption_owners[owner] = caption_owners.get(owner,0)+1
    return {e.source_index for phase,peers,words in proposals
            if all(effect_owners[e.source_index] == 1 for e,p,c in peers) and
               all(caption_owners[(phase,e.source_index)] == 1 for e in words)
            for e,p,c in peers if e.source_index not in protected and
            all(e.source_index != word.source_index for word in words)}


def match_boundary_glyph_effects(
    events: list[Event], visible_map: dict[int, str], source_events: dict[int, Event],
    metric: FontMetrics | None,
) -> set[int]:
    """Prove whole rotating entrances and flying exits of retained words.

    The source phase must meet the static caption within 50 ms, spell every
    fragment in order, and fit each authored word anchor with the exact font,
    including tracking. Partial groups, duplicate letters and unrelated labels cannot
    authorize removal. The retained words supply text; no spaces are inferred.
    """
    if metric is None or not metric.available:
        return set()
    index = _index_boundary_glyph_events(events,visible_map,source_events)
    caption_index = _index_boundary_glyph_captions(index)
    proposals = _collect_boundary_glyph_proposals(index,caption_index,visible_map,metric)
    return _resolve_boundary_glyph_ownership(proposals,index.protected)


def match_departing_glyph_effects(
    events: list[Event], row_evidence: list[TextRow], source_events: dict[int, Event],
    metric: FontMetrics | None,
) -> set[int]:
    """Prove complete outline exits from retained fragments' original anchors.

    A whole letter group must spell its source fragment, begin within 50 ms
    of that fragment's end, and fit the exact font at its authored position.
    Moving, fading contours are decorative exits; partial or ambiguous groups stay.
    This proof uses source trajectories rather than frozen effect positions.
    """
    if metric is None or not metric.available or not any(not row.virtual for row in row_evidence):
        return set()
    groups = {}
    for e in events:
        original = source_events.get(e.source_index)
        if (original is None or e.kind != "Dialogue" or
                not re.search(r"\\move\s*\(",original.text,re.I)):
            continue
        word = simplify_text(original.text,visible_only=True)[1]
        if len(word) != 1 or word.isspace() or unicodedata.combining(word):
            continue
        tokens = [token for block in OVERRIDE_RE.findall(original.text)
                  for token in tokenize_override(block)]
        moves = [value for tag,value in tokens if tag == "move"]
        if len(moves) != 1 or inline_layout_key(original):
            continue
        move = parse_effect_move(moves[0],original.duration,endpoint_slack=.001)
        if move is None or move[:2] == move[2:4]:
            continue
        evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
        state = evaluated.formatting
        final = state.copy()
        final_continuation = evaluated.continuation
        opaque_fill = False
        for tag,value in tokens:
            if tag == "t":
                for name,argument in tokenize_override(value[1:-1]):
                    final_continuation = apply_override(final,name,argument,original.styles,original.defaults,final_continuation)
                    opaque_fill |= final.get("1a",0) < 254
        if (opaque_fill or state.get("1a",0) < 254 or state.get("3a",0) >= 128 or
                final.get("1a",0) < 254 or final.get("3a",0) < 254 or
                any(s.get("p",0) or s.get("borderstyle",1) != 1 or
                    any(k in s for k in ("clip","iclip","org")) or
                    any(abs(s.get(k,s.get("shad",0))) > 0 for k in ("xshad","yshad"))
                    for s in (state,final)) or
                any(abs(state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        layout = tuple((k,str(v).casefold() if k == "fn" else v)
                       for k,v in text_layout_key(dataclass_replace(original,state=state,continuation=evaluated.continuation)))
        key = (original.style,original.name,
               placement_key(dataclass_replace(original,state=state,continuation=evaluated.continuation))[0],layout)
        groups.setdefault(key,{}).setdefault(original.start_s,[]).append((e,move,word))
    boundary_index = {key:(sorted(phases),phases) for key,phases in groups.items()}
    proofs = []
    for row in row_evidence:
        if row.virtual:
            continue
        for piece,word,pos in row.pieces:
            original = source_events.get(piece.source_index)
            if (original is None or get_pos(original.text) is None or
                    math.dist(get_pos(original.text),pos) > piece.unit or
                    not word or any(c.isspace() or unicodedata.combining(c) or
                        unicodedata.bidirectional(c) in {"R","AL","AN"} for c in word) or
                    piece.state.get("1a",255) != 0 or inline_layout_key(original)):
                continue
            layout = tuple((k,str(v).casefold() if k == "fn" else v)
                           for k,v in text_layout_key(piece))
            key = (piece.style,piece.name,placement_key(piece)[0],layout)
            for boundary,candidates in nearby_boundary_groups(boundary_index,key,original.end_s):
                peers = sorted(candidates,key=lambda item:item[1][0])
                if (len(peers) != len(word) or "".join(item[2] for item in peers) != word or
                        not original.layer.lstrip("-").isdigit() or
                        any(not source_events[e.source_index].layer.lstrip("-").isdigit() or
                            int(source_events[e.source_index].layer) <= int(original.layer)
                            for e,move,char in peers) or
                        any(abs(move[1]-pos[1]) > piece.unit for e,move,char in peers)):
                    continue
                expected = fit_fragment_anchor(metric, piece.state,
                    [move[0] for e,move,char in peers],[char for e,move,char in peers],word,piece.unit)
                if expected is None or abs(expected-pos[0]) > 1.5*piece.unit:
                    continue
                proofs.append((piece.source_index,{e.source_index for e,move,char in peers}))
    effect_owners, caption_owners = {}, {}
    for source_index,members in proofs:
        caption_owners[source_index] = caption_owners.get(source_index,0)+1
        for index in members:
            effect_owners[index] = effect_owners.get(index,0)+1
    return {index for source_index,members in proofs
            if caption_owners[source_index] == 1 and
               all(effect_owners[index] == 1 for index in members)
            for index in members}


def match_staggered_row_effects(
    events: list[Event], row_evidence: list[TextRow], source_events: dict[int, Event],
    animated_sources: set[int], metric: FontMetrics | None,
) -> set[int]:
    """Prove complete animated copies at a recorded row's source phase ends.

    Normalize vertical alignment at the stable pose. Every source fragment
    must belong to exactly one copy, with phase offsets within 50 ms,
    monotonic timing and matching font geometry. Partial and ambiguous
    families stay.
    """
    if metric is None or not metric.available or not any(not row.virtual for row in row_evidence):
        return set()
    buckets = {}
    identity = lambda e: (e.style,e.name,placement_key(e)[0],
        tuple((k,str(v).casefold() if k == "fn" else v)
              for k,v in text_layout_key(e) if k not in {"an","org"}),
        (int(e.state.get("an",5))-1)%3)
    for e in events:
        original = source_events.get(e.source_index)
        if (original is None or e.kind != "Dialogue" or
                e.source_index not in animated_sources or get_pos(original.text) is None or
                inline_layout_key(original) or not re.search(r"\\t\s*\(",original.text,re.I)):
            continue
        # Literal edge spaces affect alignment. The visible-word collector
        # intentionally strips them, so retain the unrendered source payload.
        words = OVERRIDE_RE.sub("",original.text).replace(r"\h"," ")
        if not words.strip() or original.duration <= 0 or any(tag in words for tag in (r"\N",r"\n")):
            continue
        evaluated = evaluate_effective_state(original.text,original.defaults,original.styles)
        state = evaluated.formatting
        final = state.copy()
        final_continuation = evaluated.continuation
        moving = False
        for block in OVERRIDE_RE.findall(original.text):
            for tag,value in tokenize_override(block):
                if tag == "t":
                    for name,argument in tokenize_override(value[1:-1]):
                        moving |= name in {"pos","move","org","clip","iclip","p","r",
                                           "fn","fs","fsp","an","pbo","encoding","q"}
                        final_continuation = apply_override(final,name,argument,original.styles,original.defaults,final_continuation)
        if (moving or any(s.get("p",0) or s.get("1a",0) >= 128 or
                         any(k in s for k in ("clip","iclip")) or
                         any(abs(s.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))
                         for s in (state,final))):
            continue
        stable = dataclass_replace(original,state=final,continuation=final_continuation)
        if identity(dataclass_replace(original,state=state,continuation=evaluated.continuation)) != identity(stable):
            continue
        pos = get_pos(original.text)
        # For equal horizontal alignment, only the vertical box anchor moves.
        y = pos[1]+((int(final.get("an",5))-1)//3-1)*text_height(stable)/2
        buckets.setdefault(identity(stable),[]).append((original,words,(pos[0],y)))
    families = []
    for row in row_evidence:
        if row.virtual or len(row.pieces) < 4:
            continue
        first = row.pieces[0][0]
        key = identity(first)
        peers = buckets.get(key,[])
        if not peers:
            continue
        originals = [source_events.get(piece.source_index) for piece,word,pos in row.pieces]
        if any(e is None or e.duration <= 0 for e in originals):
            continue
        height = min(text_height(piece) for piece,word,pos in row.pieces)
        ys = [pos[1]+((int(piece.state.get("an",5))-1)//3-1)*text_height(piece)/2
              for piece,word,pos in row.pieces]
        duration = max(e.end_s for e in originals)-min(e.start_s for e in originals)
        longest = max(len("".join(words.split())) for e,words,pos in peers)
        spans = {}
        for index in range(len(row.pieces)):
            text = ""
            for last in range(index,len(row.pieces)):
                text += "".join(row.pieces[last][1].split())
                if len(text) > longest:
                    break
                spans.setdefault(text,[]).append((index,last))
        matched = []
        covered = [0]*len(row.pieces)
        for original,words,pos in peers:
            if abs(pos[1]-statistics.median(ys)) > .06*height:
                continue
            options = []
            for index,last in spans.get("".join(words.split()),[]):
                pieces = row.pieces[index:last+1]
                x = fit_fragment_anchor(metric, first.state,[point[0] for piece,word,point in pieces],
                                           [word for piece,word,point in pieces],words,first.unit)
                sources = originals[index:last+1]
                ends = [e.end_s for e in sources]
                delta = original.start_s-max(ends)
                if (x is None or max(ends)-min(ends) > .011 or abs(delta) > .05*duration or
                        abs(pos[0]-x) > .12*height or
                        not original.layer.lstrip("-").isdigit() or
                        any(not e.layer.lstrip("-").isdigit() or
                            (int(original.layer),original.source_index) <= (int(e.layer),e.source_index)
                            for e in sources)):
                    continue
                options.append((index,last,delta))
            if len(options) == 1:
                index,last,delta = options[0]
                matched.append((index,original,delta))
                for glyph in range(index,last+1):
                    covered[glyph] += 1
        if len(matched) < 4 or any(count != 1 for count in covered):
            continue
        matched.sort(key=lambda item:item[0])
        offsets = [delta for index,e,delta in matched]
        # Authored handoffs can vary by a few centiseconds across syllables.
        # Keep the tolerance bounded; the epsilon only absorbs float rounding.
        if (max(offsets)-min(offsets) > .05+1e-6 or
                any(a.start_s > b.start_s+.011 or a.end_s > b.end_s+.011
                    for (_,a,_),(_,b,_) in zip(matched,matched[1:]))):
            continue
        families.append({e.source_index for index,e,delta in matched})
    counts = {}
    for family in families:
        for index in family:
            counts[index] = counts.get(index,0)+1
    return set().union(*(family for family in families if all(counts[index] == 1 for index in family)))


def _collect_covered_held_glyphs(row_evidence: list[TextRow], animated_sources: set[int]):
    """Validate recorded held glyphs against the emitted per-character caption paint."""
    # A row extended across animation phases may also cover surviving held
    # glyphs. Match its recorded pieces and emitted per-character paint, not
    # substrings or nearby positions. Requiring unchanged scales avoids
    # treating an approximate font fit as proof of identical glyph geometry.
    static_glyphs = {}
    for row in row_evidence:
        if (row.virtual or len(row.pieces) < 2 or
                any(piece.source_index not in animated_sources or len(text) != 1 or
                    text.isspace() or unicodedata.combining(text) or
                    unicodedata.bidirectional(text) in {'R','AL','AN'} or
                    piece.layer != row.base.layer
                    for piece,text,pos in row.pieces)):
            continue
        state = row.base.defaults.copy()
        continuation = OverrideContinuation()
        painted = []
        for part in re.split(r"(\{[^}]*\})",row.base.text):
            if part.startswith('{'):
                for tag,value in tokenize_override(part[1:-1]):
                    continuation = apply_override(state,tag,value,row.base.styles,
                                                  row.base.defaults,continuation)
            else:
                painted.extend((char,state.copy(),continuation) for char in part if not char.isspace())
        if ''.join(char for char,state,_ in painted) != ''.join(text for piece,text,pos in row.pieces):
            continue
        glyphs = []
        for (piece,text,pos),(char,paint,paint_continuation) in zip(row.pieces,painted):
            if (piece.state.get('1a',0) != 0 or
                    paint.get('1a',0) != 0 or paint.get('3a',0) != 0 or
                    (int(paint.get('an',2))-1)//3 != (int(piece.state.get('an',2))-1)//3 or
                    abs(get_pos(row.base.text)[1]-pos[1]) > .001):
                continue
            emitted = dataclass_replace(piece,state=paint,continuation=paint_continuation)
            # Assembly preserves proved contours and simplifies uncertain paint,
            # shadows and blur. Validate the conversion rather than equating output
            # paint with the unsimplified held phase. Foreground formatting
            # and geometry, including per-glyph colours and scales, must agree.
            paint_key = state_key(emitted,{'pos','an'})
            if paint_key != state_key(piece,{'pos','an'}):
                normalized = replace_event(piece,text=render_simplified_caption(piece.state,text,measurement=piece.measurement,
                    source_paint=_source_caption_paint(piece.state,[piece.state])))
                if paint_key != state_key(normalized,{'pos','an'}):
                    continue
            glyphs.append((piece,text,pos))
        static_glyphs[row.base.source_index] = glyphs
    return static_glyphs


def _index_covered_row_times(rows: dict[str,list[Event]]):
    """Index original row order with start times and prefix maximum end times."""
    # Index each style's original row order by start time. Prefix maximum
    # ends keep earlier long-running captions in the candidate window.
    row_indexes = {}
    for style,group in rows.items():
        if any(not math.isfinite(t) for base in group for t in (base.start_s,base.end_s)):
            row_indexes[style] = None
            continue
        ordered = sorted(enumerate(group),key=lambda item:item[1].start_s)
        starts = [base.start_s for order,base in ordered]
        latest = []
        for order,base in ordered:
            latest.append(max(latest[-1] if latest else -math.inf,base.end_s))
        row_indexes[style] = (starts,latest,ordered)
    return row_indexes


def _prepare_covered_fragments(
    visible_map: dict[int, str], row_evidence: list[TextRow], animated_sources: set[int],
    source_events: dict[int, Event] | None, font_metrics: FontMetrics | None,
):
    """Build pass-local row evidence and indexes without rediscovering geometry."""
    anchors = {row.base.source_index: row.anchors for row in row_evidence}
    models = {row.base.source_index: row for row in row_evidence}
    layouts = {row.base.source_index: tuple(
        (key,str(value).casefold() if key == "fn" else value)
        for key,value in text_layout_key(row.pieces[0][0])
        if key not in {"fscx","fscy"}) for row in row_evidence}
    rows: dict[str,list[Event]] = {}
    virtual: set[int] = set()
    for row in row_evidence:
        rows.setdefault(row.base.style,[]).append(row.base)
        if row.virtual:
            virtual.add(row.base.source_index)
    static_glyphs = _collect_covered_held_glyphs(row_evidence,animated_sources)
    row_indexes = _index_covered_row_times(rows)
    return CoveredFragmentContext(visible_map,animated_sources,source_events,font_metrics,
        anchors,models,layouts,rows,virtual,static_glyphs,row_indexes)


def _covered_fragment_spans(context: CoveredFragmentContext, base: Event, visible: str, shadow_only: bool):
    """Cache recorded fragment spans separately for exact and shadow casefold matching."""
    key = (base.source_index,shadow_only)
    if key not in context.span_indexes:
        context.span_indexes[key] = index_fragment_spans(
            (text for text,x in context.anchors[base.source_index]),casefold=shadow_only)
    target = ''.join(visible.split())
    if shadow_only:
        target = target.casefold()
    yield from matching_fragment_spans(context.span_indexes[key],target)


def _covered_animated_shadow_source(context: CoveredFragmentContext, e: Event):
    """Cache original animated shadow paint, including copies transferred to foreground."""
    # Copy reduction can transfer animated shadow paint into the primary
    # channel. Retain the original evidence when checking its highlight
    # fragments; actor labels need not identify the same effect phase.
    if e.source_index not in context.shadow_sources:
        context.shadow_sources[e.source_index] = animated_shadow_painted_source(e,context.sources,context.animated)
    return context.shadow_sources[e.source_index]


def _covered_held_glyph_copy(context: CoveredFragmentContext, e: Event, visible: str, pos: tuple, base: Event):
    """Prove one stationary letter repeats an exactly placed recorded held glyph."""
    if (not context.static_glyphs.get(base.source_index) or
            e.source_index in context.animated or len(visible) != 1 or
            e.style != base.style or e.name != base.name or
            e.start_s < base.start_s or e.end_s > base.end_s):
        return False
    matches = [piece for piece,text,anchor in
               context.static_glyphs.get(base.source_index,[]) if text == visible and
               math.dist(pos,anchor) <= .001]
    if len(matches) != 1:
        return False
    piece = matches[0]
    return (e.layer == piece.layer and placement_key(e) == placement_key(piece) and
            state_key(e,{'pos'}) == state_key(piece,{'pos'}) and
            static_object_key(e,e.styles) is not None)


def _timed_covered_rows(context: CoveredFragmentContext, style: str, e: Event):
    """Search the indexed timing window while retaining original row order and tolerance."""
    index = context.row_indexes.get(style)
    if index is None or not all(math.isfinite(t) for t in (e.start_s,e.end_s)):
        return list(context.rows.get(style,[]))
    starts,latest,ordered = index
    # Expand the bounds by one floating-point step. The unchanged exact
    # comparisons below decide equality at the existing 0.15 s tolerance.
    left = bisect_left(latest,math.nextafter(e.end_s-.15,-math.inf))
    right = bisect_right(starts,math.nextafter(e.start_s+.15,math.inf))
    candidates = [(order,base) for order,base in ordered[left:right]
                  if not (e.start_s < base.start_s-.15 or e.end_s > base.end_s+.15)]
    return [base for order,base in sorted(candidates,key=lambda item:item[0])]


def _prepare_covered_shadow_rows(context: CoveredFragmentContext):
    """Identify complete animated shadow rows and their original source layers."""
    # A shadow-painted highlight may already have become a partial caption.
    # Prove ownership using its recorded source fragments, before inferred
    # tracking or its new paragraph anchor obscures the original glyph row.
    shadow_rows = {index for index,row in context.models.items() if not row.virtual and
                   row.pieces and all(_covered_animated_shadow_source(context,piece) for piece,_,_ in row.pieces)}
    shadow_layers = {index:max(int(piece.layer) if piece.layer.lstrip('-').isdigit() else 0
                             for piece,_,_ in context.models[index].pieces) for index in shadow_rows}
    context.shadow_rows.update(shadow_rows)
    context.shadow_layers.update(shadow_layers)


def _shared_covered_shadow_fade_core(context: CoveredFragmentContext, row: TextRow, base: Event):
    """Use one shared positive source fade to protect a completed remuxed lyric core."""
    fades = set()
    for piece,_,_ in row.pieces:
        original = (context.sources or {})[piece.source_index]
        values = [value for tag,value in event_override_tokens(original) if tag == 'fad']
        try:
            pair = tuple(float(v)/1000 for v in values[0].strip('()').split(','))
        except (IndexError,ValueError):
            break
        if (len(values) != 1 or len(pair) != 2 or
                not all(math.isfinite(v) and v > 0 for v in pair) or
                sum(pair) >= original.duration):
            break
        fades.add(pair)
    else:
        if len(fades) == 1:
            entrance,tail = next(iter(fades))
            return (round(base.start_s+entrance,2),round(base.end_s-tail,2))
    return None


def _select_covered_shadow_timing(events: list[Event], context: CoveredFragmentContext) -> dict[int,tuple[float,float]]:
    """Return proved cores keyed by row identity without modifying input evidence.

    Identity preserves the selected model when rows share a source index, and
    applies the same proof to repeated references to that model.
    """
    # Authored cue intervals protect the completed lyric while the shared
    # overlap pass trims only the surrounding reconstructed entrance/tail.
    # Require a complete, equally timed source glyph row and one exact cue.
    cue_comments = {}
    cores = {}
    if context.shadow_rows:
        for e in events:
            if e.kind == 'Comment':
                words = simplify_text(e.text,visible_only=True)[1]
                cue_comments.setdefault((e.style,words),[]).append(e)
    for index in context.shadow_rows:
        row = context.models[index]
        base = row.base
        if row.phase_core is not None or not all(
                round((context.sources or {})[piece.source_index].start_s,2) == round(base.start_s,2) and
                round((context.sources or {})[piece.source_index].end_s,2) == round(base.end_s,2)
                for piece,_,_ in row.pieces):
            continue
        cues = {(cue.start_s,cue.end_s) for cue in
                cue_comments.get((base.style,context.visible.get(index,'')),[]) if
                base.start_s < cue.start_s < cue.end_s < base.end_s}
        if len(cues) == 1:
            cores[id(row)] = next(iter(cues))
        elif not cue_comments.get((base.style,context.visible.get(index,''))):
            # Remuxed tracks often omit the authored Comment lines. A complete
            # coextensive shadow row can still prove its entrance/tail from one
            # shared fade. Animation/paint ownership was checked above; these
            # fades supply timing only, never permission to remove other rows.
            core = _shared_covered_shadow_fade_core(context,row,base)
            if core is not None:
                cores[id(row)] = core
    return cores


def _covered_shadow_fragment_copy(context: CoveredFragmentContext, piece: Event, text: str, pos: tuple, base: Event):
    """Match a nested shadow-painted fragment using the existing upright-pose proof."""
    if (not _covered_animated_shadow_source(context,piece) or base.source_index not in context.shadow_rows or
            piece.state.get('p',0) or inline_layout_key(piece) or
            any(k in piece.state for k in ('clip','iclip','org')) or
            piece.duration >= base.duration-.011 or
            piece.start_s < base.start_s-.15 or piece.end_s > base.end_s+.15 or
            piece.state.get('1a',0) != 0 or base.state.get('1a',0) != 0 or
            piece.state.get('1c') != base.state.get('1c') or
            not piece.layer.lstrip('-').isdigit() or
            int(piece.layer) <= context.shadow_layers[base.source_index] or
            placement_key(piece)[0] != placement_key(base)[0] or
            abs(pos[1]-get_pos(base.text)[1]) > .06*min(text_height(piece),text_height(base))):
        return False
    if piece.source_index not in context.shadow_poses:
        # The final rotation cleanup would select this same authored
        # upright pose. Use that helper here too, so a late pulse is not
        # mistaken for an independent angled letter merely because the
        # initial frozen sample preceded its readable pose.
        context.shadow_poses[piece.source_index] = prefer_surviving_upright_poses(
            [piece],context.sources or {})[0]
    pose = context.shadow_poses[piece.source_index]
    layout = tuple((key,str(value).casefold() if key == 'fn' else value)
                   for key,value in text_layout_key(pose) if key not in {'fscx','fscy'})
    if layout != context.layouts[base.source_index]:
        return False
    glyphs = context.anchors[base.source_index]
    matches = [(first,last) for first,last in _covered_fragment_spans(context,base,text,False) if
               abs(pos[0]-(glyphs[first][1]+glyphs[last][1])/2) <=
               .12*min(text_height(piece),text_height(base))]
    return len(matches) == 1


def _remove_covered_shadow_fragments(events: list[Event], context: CoveredFragmentContext, removed: set[int]):
    """Remove shadow fragment rows only when exactly one complete row owns them."""
    for e in events:
        pos = get_pos(e.text)
        text = context.visible.get(e.source_index,'')
        if e.kind != 'Dialogue' or not text or pos is None or e.source_index in removed:
            continue
        model = context.models.get(e.source_index)
        pieces = model.pieces if model is not None and not model.virtual else [(e,text,pos)]
        if not pieces or not all(_covered_animated_shadow_source(context,piece) for piece,_,_ in pieces):
            continue
        owners = [base for base in _timed_covered_rows(context,e.style,e) if base.source_index != e.source_index and
                  all(_covered_shadow_fragment_copy(context,piece,word,point,base) for piece,word,point in pieces)]
        if len(owners) == 1:
            removed.add(e.source_index)


def _covered_fragment_candidates(context: CoveredFragmentContext, e: Event, visible: str, pos: tuple):
    """Collect same-style rows and strictly nested animated cross-style highlights."""
    candidates = _timed_covered_rows(context,e.style,e)
    if e.source_index in (context.animated or set()):
        # Highlight copies may use a different style. Require matching
        # font geometry, exact fragment position/text and nested lifetime.
        for style in context.rows:
            if style == e.style:
                continue
            for base in _timed_covered_rows(context,style,e):
                if (e.name == base.name and e.duration <= .5*base.duration
                        and e.start_s >= base.start_s and e.end_s <= base.end_s
                        and all(e.state.get(tag) == base.state.get(tag)
                                for tag in ("fn","fs","an","b","i","frz"))
                        and abs(pos[1]-get_pos(base.text)[1]) <= e.unit
                        and any(text == visible and abs(pos[0]-x) <= e.unit
                                for text,x in context.anchors[base.source_index])):
                    candidates.append(base)
    return candidates


def _covered_fragment_copy_matches(context: CoveredFragmentContext, e: Event, visible: str, pos: tuple,
    base: Event, layout: tuple, shadow_only: bool):
    """Prove held, shadow or animated foreground copies from original row evidence."""
    if _covered_held_glyph_copy(context,e,visible,pos,base):
        return True
    # A substring and nearby anchor do not identify an effect copy.
    # Compare the source fragment layout: assembly may change the
    # row's alignment and scales, but not its font or caption identity.
    if (e.name != base.name or layout != context.layouts[base.source_index] or
            placement_key(e)[0] != placement_key(base)[0]):
        return False
    # Unassembled rows prove only shadow copies. Their font/layout
    # identity is checked above along with assembled rows.
    if base.source_index in context.virtual and not shadow_only:
        return False
    if not shadow_only:
        # Visible syllables need the same nested animated foreground
        # evidence as early source-row removal. Static labels remain
        # independent even when their text and position happen to fit.
        source_layer = max(int(piece.layer) if piece.layer.lstrip("-").isdigit() else 0
                           for piece,_,_ in context.models[base.source_index].pieces)
        if (e.source_index not in context.animated or
                e.duration >= base.duration-.011 or
                e.start_s < base.start_s or e.end_s > base.end_s or
                abs(pos[1]-get_pos(base.text)[1]) > .06*min(text_height(e),text_height(base)) or
                not e.layer.lstrip("-").isdigit() or int(e.layer) <= source_layer):
            return False
    if (e.duration > .8*base.duration and e.layer == base.layer or
            e.start_s < base.start_s-.15 or e.end_s > base.end_s+.15 or
            abs(pos[1]-get_pos(base.text)[1]) > .15*text_height(base)):
        return False
    glyphs = context.anchors[base.source_index]
    matches = []
    for index,last in _covered_fragment_spans(context,base,visible,shadow_only):
        if (abs(pos[0]-(glyphs[index][1]+glyphs[last][1])/2)
                <= ((.6 if len(visible)>2 else .24)*text_height(base)
                    if shadow_only else .12*min(text_height(e),text_height(base)))):
            matches.append((index,last))
    return len(matches) == 1


def _remove_covered_fragment_copies(events: list[Event], context: CoveredFragmentContext, removed: set[int]):
    """Test remaining fragments in event and candidate order, committing proved copies."""
    for e in events:
        pos = get_pos(e.text)
        visible = context.visible.get(e.source_index,"")
        if (e.kind != "Dialogue" or e.source_index in removed or e.source_index in context.anchors or pos is None or
                not visible or e.state.get("p",0) or
                inline_layout_key(e) or "clip" in e.state or "iclip" in e.state):
            continue
        layout = tuple((key,str(value).casefold() if key == "fn" else value)
                       for key,value in text_layout_key(e)
                       if key not in {"fscx","fscy"})
        shadow_only = (e.state.get("1a",0) >= 254 and e.state.get("3a",0) >= 254 and
                       e.state.get("4a",0) < 254 and
                       any(abs(e.state.get(k,e.state.get("shad",0))) > 0
                           for k in ("xshad","yshad")))
        candidates = _covered_fragment_candidates(context,e,visible,pos)
        for base in candidates:
            if _covered_fragment_copy_matches(context,e,visible,pos,base,layout,shadow_only):
                removed.add(e.source_index)
                break


def remove_covered_fragment_effects(
    events: list[Event], visible_map: dict[int, str], row_evidence: list[TextRow],
    animated_sources: set[int] | None=None, source_events: dict[int, Event] | None=None,
    font_metrics: FontMetrics | None=None,
) -> CoveredFragmentRemoval:
    """Remove copies proven to repeat reconstructed, authored or virtual rows.

    Consume shared fragment anchors without guessing spacing or rediscovering
    rows. Visible overlays require nested animation evidence. Static glyphs
    can repeat an animated row's recorded glyphs with identical placement and
    source styling, provided the emitted paint is unchanged or matches its
    simplified caption form; virtual rows authorize only matching shadow copies. Original
    trajectories and exact font measurements prove entrance and exit groups.
    Input events, visibility and rows are borrowed. Return timing evidence in
    independent row successors, including proofs when no copies are removed.
    """
    animated_sources = animated_sources or set()
    context = _prepare_covered_fragments(visible_map,row_evidence,animated_sources,
        source_events,font_metrics)
    removed = (match_departing_glyph_effects(events,row_evidence,source_events,font_metrics)
               if source_events is not None else set())
    if source_events is not None:
        removed.update(match_boundary_glyph_effects(events,visible_map,source_events,font_metrics))
        removed.update(match_staggered_row_effects(events,row_evidence,source_events,animated_sources,font_metrics))
    _prepare_covered_shadow_rows(context)
    cores = _select_covered_shadow_timing(events,context)
    _remove_covered_shadow_fragments(events,context,removed)
    _remove_covered_fragment_copies(events,context,removed)
    rows = [dataclass_replace(row,
        pieces=list(row.pieces),
        paint_rows=[list(paint_row) for paint_row in row.paint_rows],
        source_anchors={word:list(anchors) for word,anchors in row.source_anchors.items()},
        foreground=list(row.foreground),
        phase_core=cores.get(id(row),row.phase_core)) for row in row_evidence]
    return CoveredFragmentRemoval(
        [e for e in events if e.source_index not in removed],rows,len(removed))


@dataclass(frozen=True)
class GlyphPhaseLife:
    """One source-proved glyph position through its complete paint lifecycle."""
    members: tuple[Event,...]
    pose: Event
    literal: str
    start_s: float
    end_s: float
    core: tuple[float,float]
    # A syllable can bridge several glyphs. Its whole source family must be
    # owned by the completed row before any shared replacement is consumed.
    required_members: frozenset[int] = frozenset()


def _index_glyph_phase_slots(parsed: dict[int,Event], metric: FontMetrics,
                              max_piece_duration: float,
                              font_report: FontProcessingReport | None) -> tuple[list,dict,list]:
    """Normalize exact-font anchors, retaining rejected nearby text as blockers."""
    profiles = {}
    for e in parsed.values():
        if e.kind != 'Dialogue' or e.duration <= 0:
            continue
        literal = OVERRIDE_RE.sub('',e.text)
        if len(literal) != 1 or literal.isspace():
            continue
        profile = profiles.setdefault((e.style,e.name),[0,0])
        profile[0] += bool(re.search(r'\\fad\s*\(',e.text,re.I))
        profile[1] += e.duration <= max_piece_duration+1e-6
    families = {key for key,(fades,frames) in profiles.items() if fades >= 8 and frames >= 12}
    families.update((e.style,e.name) for e in parsed.values() if e.kind == 'Dialogue' and
                    re.search(r'\\t\s*\(',e.text) and re.search(r'\\fsc[xy]',e.text))
    slots,spatial,obstacles,widths,endpoints = [],{}, {},{},[]
    forbidden = {'t','move','fade','clip','iclip','org','p','r','k','kf','ko','kt'}
    for source in sorted(parsed.values(),key=lambda e:(e.start_s,e.end_s,e.source_index)):
        family = (source.style,source.name)
        if family not in families or source.kind != 'Dialogue' or source.duration <= 0:
            continue
        literal = OVERRIDE_RE.sub('',source.text)
        if not literal.strip():
            continue
        evaluated = event_evaluation(source)
        e = dataclass_replace(source,state=evaluated.formatting,continuation=evaluated.continuation)
        pos = get_pos(e.text)
        height = text_height(e)
        alignment = int(e.state.get('an',5))
        if not math.isfinite(height) or height <= 0 or alignment not in range(1,10):
            continue
        if pos is None:
            obstacles.setdefault(family,[]).append([e,None,height])
            continue
        if any(not math.isfinite(v) for v in pos):
            continue
        # Rejected geometry is still evidence of a possible missing glyph.
        approximate = (pos[0],pos[1]+((alignment-1)//3-1)*height/2)
        obstacle = [e,approximate,height]
        obstacles.setdefault(family,[]).append(obstacle)
        prefix = re.match(r'(?:\{[^}]*\})*',e.text).end()
        tokens = event_override_tokens(e)
        if (len(literal) != 1 or literal.isspace() or unicodedata.combining(literal) or
                unicodedata.bidirectional(literal) in {'R','AL','AN'} or
                OVERRIDE_RE.search(e.text,prefix) or _faded_cue_is_scrolling(e) or
                any(tag in forbidden for tag,value in tokens) or
                not unrotated_text_state(e.state) or
                any(abs(e.state.get(k,0)) > .001 for k in ('fax','fay','fsp','pbo')) or
                any(not math.isfinite(e.state.get(k,0)) or e.state.get(k,0) <= 0
                    for k in ('fs','fscx','fscy')) or
                e.state.get('borderstyle',1) != 1 or
                str(e.state.get('fn','')).startswith('@') or
                not e.layer.lstrip('-').isdigit()):
            continue
        fade_values = [value for tag,value in tokens if tag=='fad']
        fade = None
        if fade_values:
            if len(fade_values) != 1 or not re.fullmatch(r'\(\s*'+NUM+r'\s*,\s*'+NUM+r'\s*\)',fade_values[0]):
                continue
            fade = tuple(float(v)/1000 for v in fade_values[0][1:-1].split(','))
            if any(not math.isfinite(v) or v < 0 for v in fade) or (fade[0]>0)==(fade[1]>0):
                continue
        elif e.duration > max_piece_duration+1e-6:
            continue
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement,
               tuple((k,v) for k,v in text_layout_key(e) if k != 'an'))
        width_key = (key,literal)
        if width_key not in widths:
            face = metric.matching_face(str(e.state.get('fn','')),e.state.get('b',0),bool(e.state.get('i',0)))
            factor = metric.ass_em_scale(face) if face is not None else None
            width = None
            if face is not None and factor is not None and ord(literal) in face.cmap:
                try:
                    width = metric.measure(face,literal,bool(e.state.get('kerning',False)))*e.state.get('fs',20)*e.state.get('fscx',100)/100/1024*factor
                except (OSError,ValueError,RuntimeError):
                    pass
            widths[width_key] = width
            if width is None and font_report is not None:
                font_report.missing_families.add(str(e.state.get('fn','')))
        width = widths[width_key]
        if width is None or not math.isfinite(width) or width <= 0:
            continue
        center = (pos[0]+(.5-((alignment-1)%3)/2)*width,approximate[1])
        obstacle[1] = center
        tags = ''.join('\\'+tag+value for tag,value in tokens if tag not in {'pos','an','a'})
        canonical = replace_event(e,text='{'+tags+r'\an5'+('\\pos('+','.join(format(v,'.12g') for v in center)+')')+'}'+literal)
        if fade is not None:
            endpoints.append((canonical,fade))
        unit = .06*height
        cell = (math.floor(center[0]/unit),math.floor(center[1]/unit))
        candidates = {i for dx in (-1,0,1) for dy in (-1,0,1)
                      for i in spatial.get((key,literal,cell[0]+dx,cell[1]+dy),[])
                      if all(abs(a-b) <= unit+1e-6 for a,b in zip(center,get_pos(slots[i][0][0].text))) and
                      (any(other_fade is not None and other_fade[0] and
                           other.layer != canonical.layer and
                           abs(other.start_s-canonical.start_s) <= 1e-6 and
                           abs(other.end_s-canonical.end_s) <= 1e-6 and
                           all(abs(a-b) <= .001*height+1e-6 for a,b in zip(center,get_pos(other.text)))
                           for other,other_fade in slots[i])
                       if fade is not None and fade[0] else
                       any(abs(other.end_s-canonical.start_s) <= 1e-6 and
                           (other_fade is None or other_fade[1] == 0)
                           for other,other_fade in slots[i]))}
        if len(candidates) > 1:
            continue
        if candidates:
            index = candidates.pop()
        else:
            if fade is None or not fade[0]:
                continue
            index = len(slots);slots.append([])
            spatial.setdefault((key,literal,*cell),[]).append(index)
        slots[index].append((canonical,fade))
    return slots,obstacles,endpoints


def _profile_glyph_replacement(source: Event) -> tuple[Event,dict,float] | None:
    """Recognize one stationary readable syllable shrinking into a fading exit."""
    literal = OVERRIDE_RE.sub('',source.text)
    if (source.kind != 'Dialogue' or source.duration <= 0 or not literal or
            any(c.isspace() or unicodedata.combining(c) or
                unicodedata.bidirectional(c) in {'R','AL','AN'} for c in literal) or
            '\\' in literal or _faded_cue_is_scrolling(source) or not source.layer.lstrip('-').isdigit()):
        return None
    evaluated = event_evaluation(source)
    e = dataclass_replace(source,state=evaluated.formatting,continuation=evaluated.continuation)
    state = e.state
    if (get_pos(e.text) is None or inline_layout_key(e) or not unrotated_text_state(state) or
            state.get('an') != 5 or state.get('borderstyle',1) != 1 or
            any(k in state for k in ('clip','iclip','org')) or
            any(abs(state.get(k,0)) > .001 for k in ('fax','fay','fsp','p','pbo')) or
            any(abs(state.get(k,state.get('shad',0))) > .001 for k in ('xshad','yshad')) or
            not all(math.isfinite(v) for v in get_pos(e.text)) or
            not 0 <= state.get('1a',0) < 128):
        return None
    final = state.copy();continuation = e.continuation;scaled = False;fade_begin = None
    for tag,value in event_override_tokens(e):
        if tag in {'move','fad','fade','r','k','kf','ko','kt'}:
            return None
        if tag != 't':
            continue
        # A target-free transform has no visual effect (including template
        # annotations with unused timing); it supplies no evidence either.
        if not tokenize_override(value[1:-1]):
            continue
        transform = parse_effect_transform(value,e.duration,
            {'fscx','fscy','alpha','1a','3a','4a','blur','be'},allow_instant=True)
        if transform is None:
            return None
        begin,_,changes = transform
        previous = final.copy()
        for name,argument in changes:
            continuation = apply_override(final,name,argument,e.styles,e.defaults,continuation)
        for axis in ('fscx','fscy'):
            a,b = previous.get(axis,100),final.get(axis,100)
            if not all(math.isfinite(v) and v > 0 for v in (a,b)) or b > a+.001:
                return None
            scaled |= b < a-.001
        if final.get('1a',0) < previous.get('1a',0):
            return None
        if final.get('1a',0) > previous.get('1a',0):
            fade_begin = e.start_s+begin/1000
    if not scaled or final.get('1a',0) < 254:
        return None
    return e,final,fade_begin


def _prove_replacement_glyph_lives(endpoints: list, parsed: dict[int,Event],
                                  metric: FontMetrics) -> list[GlyphPhaseLife]:
    """Bridge complete letter stacks through uniquely owned whole-syllable phases.

    Only original source evidence is used. Shared pulse ownership is provisional
    until the ordinary whole-row font, obstacle and competing-claim proofs pass.
    """
    def family(e):
        return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement,
                tuple((k,v) for k,v in text_layout_key(e) if k not in {'an','fscx','fscy'}))
    entries,tails = {},{}
    for e,fade in endpoints:
        if e.state.get('1a',0) != 0 or e.state.get('3a',0) != 0:
            continue
        key = family(e)
        if fade[0]:
            entries.setdefault(key,[]).append((e,fade))
        else:
            tails.setdefault((key,e.layer,get_pos(e.text),OVERRIDE_RE.sub('',e.text)),[]).append((e,fade))
    profiles,cohorts = [],{}
    for source in parsed.values():
        # Avoid parsing unrelated ordinary text and already sampled frames.
        if not re.search(r'\\t\s*\(',source.text) or not re.search(r'\\fsc[xy]',source.text):
            continue
        profile = _profile_glyph_replacement(source)
        if profile is None:
            continue
        profiles.append(profile)
        pulse,final,fade_begin = profile;key = family(pulse);pos = get_pos(pulse.text)
        literal = OVERRIDE_RE.sub('',pulse.text);groups = {}
        for entry,fade in entries.get(key,[]):
            anchor = get_pos(entry.text);height = text_height(entry)
            if (abs(entry.end_s-pulse.start_s) > .011 or
                    abs(anchor[1]-pos[1]) > .02*height):
                continue
            word = OVERRIDE_RE.sub('',entry.text)
            options = [(tail,exit_fade) for tail,exit_fade in tails.get((key,entry.layer,anchor,word),[])
                       if pulse.start_s-.011 <= tail.start_s <= pulse.end_s+.011 and
                       tail.end_s >= fade_begin-.011 and
                       text_layout_key(entry) == text_layout_key(tail)]
            if len(options) != 1:
                continue
            tail,exit_fade = options[0]
            groups.setdefault((entry.start_s,tail.end_s,tail.start_s,entry.layer),[]).append(
                (entry,tail,fade,exit_fade))
        stacks = []
        for group,pairs in groups.items():
            pairs.sort(key=lambda p:get_pos(p[0].text)[0])
            xs = [get_pos(p[0].text)[0] for p in pairs]
            if (''.join(OVERRIDE_RE.sub('',p[0].text) for p in pairs) != literal or
                    len(set(xs)) != len(xs) or int(group[-1]) >= int(pulse.layer) or
                    not matches_authored_glyph_positions(metric,final,xs,literal,pos[0],.05*text_height(pairs[0][0]))):
                continue
            stacks.append((group,pairs))
        if (not stacks or len({g[-1] for g,p in stacks}) != len(stacks) or
                len({g[:3] for g,p in stacks}) != 1 or
                len({tuple(get_pos(p[0].text) for p in pairs) for g,pairs in stacks}) != 1):
            continue
        for group,pairs in stacks:
            cohort = cohorts.setdefault((key,group[0],group[1],pos[1]),{})
            cohort.setdefault(group[-1],{}).update({p[0].source_index:p for p in pairs})

    # Complete interior pairs prove cue bounds and the observed before/after
    # paint relation. Boundary syllables may legitimately have no entrance or
    # no post-highlight hold; borrow that relation only when it is unambiguous.
    proposals = []
    paint_tags = set(CAPTION_PAINT_TAGS)
    def paint_key(state):
        return tuple((k,state.get(k,DEFAULT_STATE.get(k))) for k in sorted(paint_tags))
    for pulse,final,fade_begin in profiles:
        pos = get_pos(pulse.text);literal = OVERRIDE_RE.sub('',pulse.text)
        expected = authored_glyph_positions(metric,final,literal,pos[0],.05*text_height(pulse))
        if expected is None:
            continue
        for (key,start,end,y),layers in cohorts.items():
            if (family(pulse) != key or not start-.011 <= pulse.start_s < end or
                    abs(y-pos[1]) > .02*text_height(pulse)):
                continue
            stacks = [];donors = set()
            for layer,known in sorted(layers.items(),key=lambda item:int(item[0])):
                if int(layer) >= int(pulse.layer):
                    break
                palette = {}
                for entry,tail,ingress,exit_fade in known.values():
                    palette.setdefault(paint_key(entry.state),{}).setdefault(paint_key(tail.state),tail.state)
                    donors.update((entry.source_index,tail.source_index))
                reference = next(iter(known.values()))
                pairs = []
                for char,x in expected:
                    radius = .075*text_height(reference[0])
                    before = [(e,f) for e,f in entries.get(key,[]) if e.layer == layer and
                              e.start_s == start and abs(e.end_s-pulse.start_s) <= .011 and
                              OVERRIDE_RE.sub('',e.text) == char and
                              abs(get_pos(e.text)[0]-x) <= radius and abs(get_pos(e.text)[1]-y) <= .001]
                    after = [(e,f) for (k,l,anchor,word),phases in tails.items()
                             if k == key and l == layer and word == char and
                             abs(anchor[0]-x) <= radius and abs(anchor[1]-y) <= .001
                             for e,f in phases if e.end_s == end and
                             pulse.start_s-.011 <= e.start_s <= pulse.end_s+.011]
                    if (len(before)>1 or len(after)>1 or not before and not after or
                            not before and abs(pulse.start_s-start)>.011 or
                            not after and abs(fade_begin-end)>.011):
                        break
                    entry,ingress = before[0] if before else (None,reference[2])
                    tail,exit_fade = after[0] if after else (None,reference[3])
                    if entry is not None and tail is not None and (
                            get_pos(entry.text) != get_pos(tail.text) or
                            text_layout_key(entry) != text_layout_key(tail)):
                        break
                    if tail is not None:
                        state = tail.state
                    else:
                        choices = palette.get(paint_key(entry.state),{})
                        if len(choices) != 1:
                            break
                        selected = next(iter(choices.values()))
                        state = {**entry.state,**{k:selected[k] for k in paint_tags if k in selected}}
                    pairs.append((entry,tail,ingress,exit_fade,state))
                else:
                    stacks.append((layer,pairs))
                    continue
                break
            if len(stacks) != len(layers):
                continue
            # Every plane must describe the same letters and anchors. Shared
            # source IDs authorize only atomic whole-cue ownership downstream.
            anchors = [tuple(get_pos((p[1] or p[0]).text) for p in pairs) for layer,pairs in stacks]
            if len(set(anchors)) != 1:
                continue
            members = tuple(e for layer,pairs in stacks for p in pairs for e in p[:2] if e is not None)+(pulse,)
            required = frozenset(donors)|frozenset(e.source_index for e in members)
            lives = []
            for i,(entry,tail,ingress,exit_fade,state) in enumerate(stacks[-1][1]):
                supports = [pairs[i][4] for layer,pairs in stacks]
                proof = _source_caption_paint(state,supports)
                if proof is None:
                    break
                source = tail or entry
                text = render_simplified_caption(state,expected[i][0],source_paint=proof,measurement=source.measurement)
                # Keep original anchor precision until the whole-row advance
                # fit finishes; this is an evidence pose, not final output.
                anchor = get_pos(source.text)
                text = POS_RE.sub(lambda _: '\\pos('+','.join(format(v,'.12g') for v in anchor)+')',text,count=1)
                pose = replace_event(source,text=text,effect='')
                owned = tuple(e for layer,pairs in stacks for e in pairs[i][:2] if e is not None)+(pulse,)
                core = (min(entry.end_s,start+ingress[0]) if entry is not None else start,
                        max(tail.start_s,end-exit_fade[1]) if tail is not None else fade_begin)
                if core[1]-core[0] < .32-1e-6:
                    break
                lives.append(GlyphPhaseLife(owned,pose,expected[i][0],start,max(end,pulse.end_s),core,required))
            else:
                proposals.append((frozenset(e.source_index for e in members),lives))
    claims = collections.Counter(i for ids,lives in proposals for i in ids)
    return [life for ids,lives in proposals if all(claims[i] == 1 for i in ids) for life in lives]


def _prove_glyph_phase_lives(slots: list, max_piece_duration: float) -> list[GlyphPhaseLife]:
    """Walk unique touching entrance/frame/exit paths, then own their paint stack."""
    lives = []
    for slot in slots:
        starts = {}
        for e,fade in slot:
            starts.setdefault((e.layer,round(e.start_s,6)),[]).append((e,fade))
        paths = {}
        for entry,fade in slot:
            if fade is None or not fade[0] or fade[1]:
                continue
            path = [entry];current = entry;exit_event = None;exit_fade = None
            while len(path) <= len(slot):
                following = starts.get((entry.layer,round(current.end_s,6)),[])
                if len(following) != 1:
                    break
                event,tail = following[0]
                if tail is not None:
                    if (tail[0] == 0 and tail[1] > 0 and
                            all(abs(a-b) <= .001*text_height(entry)+1e-6
                                for a,b in zip(get_pos(entry.text),get_pos(event.text)))):
                        path.append(event);exit_event,exit_fade = event,tail
                    break
                if event.duration > max_piece_duration+1e-6:
                    break
                path.append(event);current = event
            if exit_event is None or len(path)-2 < 1:
                continue
            start,end = entry.start_s,exit_event.end_s
            core = (min(entry.end_s,start+fade[0]),max(exit_event.start_s,end-exit_fade[1]))
            if core[1]-core[0] < .32-1e-6:
                continue
            paths.setdefault((start,end),[]).append((entry.layer,path,core))
        for (start,end),layers in paths.items():
            if len({layer for layer,path,core in layers}) != len(layers):
                continue
            readable = [p for p in layers if all(e.state.get('1a',0)<128 for e in p[1])]
            if not readable:
                continue
            foreground = max(readable,key=lambda p:int(p[0]))
            members = [e for layer,path,core in layers for e in path]
            claimed = {e.source_index for e in members}
            pulse_start,pulse_end = foreground[1][0].end_s,foreground[1][-1].start_s
            extra = [e for e,fade in slot if e.source_index not in claimed and
                     start < e.end_s and e.start_s < end]
            # Only short lower paint layers wholly inside the highlight may
            # be owned without their own complete entrance/exit path.
            if any(e.duration > max_piece_duration+1e-6 or int(e.layer) >= int(foreground[0]) or
                   e.start_s < pulse_start-1e-6 or e.end_s > pulse_end+1e-6 for e in extra):
                continue
            members += extra
            pose = foreground[1][0]
            positions = [get_pos(e.text) for e in members]
            if any(max(p[a] for p in positions)-min(p[a] for p in positions) > .12*text_height(pose)+1e-6 for a in (0,1)):
                continue
            # Readable saturated source intervals provide colour dwell. Fade
            # ramps cannot overweight a brief foreground against a long hold.
            paint_events = []
            for e in members:
                fades = [v for tag,v in event_override_tokens(e) if tag=='fad']
                a,b = e.start_s,e.end_s
                if fades:
                    ingress,tail = (float(v)/1000 for v in fades[0][1:-1].split(','))
                    a,b = min(b,a+ingress),max(a,b-tail)
                if b > a:
                    paint_events.append(replace_event(e,start_s=a,end_s=b,start=format_time(a),end=format_time(b)))
            paint = dict(select_static_state(pose.state,[],set(),pose.styles,pose.defaults,
                paint_events=paint_events,continuation=pose.continuation).state)
            contours = [e.state for e in members if e.state.get('3c')==paint.get('3c') and
                        e.state.get('3a',0)==0 and max(e.state.get(k,e.state.get('bord',0)) for k in ('xbord','ybord'))>0]
            if contours:
                paint.update(bord=2,xbord=2,ybord=2,**{'3a':0})
            tags = ''.join('\\'+tag+value for tag,value in event_override_tokens(pose) if tag!='fad')
            tags += ''.join(render_tag(k,paint[k]) for k in ('1c','3c','1a','3a','bord','xbord','ybord') if k in paint)
            chosen = replace_event(pose,text='{'+tags+'}'+OVERRIDE_RE.sub('',pose.text))
            lives.append(GlyphPhaseLife(tuple(members),chosen,OVERRIDE_RE.sub('',pose.text),start,end,foreground[2]))
    return lives


def _caption_implicit_anchor(event: Event) -> tuple[Event | None,float | None]:
    """Resolve a static ASS margin anchor for measured clearance only.

    Return the available width so callers reject unknown automatic wrapping.
    This never changes serialized placement or renderer collision policy.
    """
    if get_pos(event.text) is not None:return event,None
    if event.measurement.canvas is None or re.search(r'\\(?:move|t)\s*\(',event.text):return None,None
    width,height=event.measurement.canvas
    st=event.state;alignment=int(st.get('an',2))
    if alignment not in range(1,10):return None,None
    left,right,vertical=(float(value) or st.get(tag,0) for value,tag in
        ((event.margin_l,'marginl'),(event.margin_r,'marginr'),(event.margin_v,'marginv')))
    x=(left,(width+left-right)/2,width-right)[(alignment-1)%3]
    y=(height-vertical,height/2,vertical)[(alignment-1)//3]
    return replace_event(event,text=set_pos(event.text,(x,y))),width-left-right


def _glyph_replacement_row_is_clear(caption: Event, core: tuple[float,float],
                                    members: set[int], highest: int,
                                    parsed: dict[int,Event], metric: FontMetrics,
                                    poses: list[Event]) -> bool:
    """Prove intervening paint cannot obscure newly assembled readable content.

    The established fade-core handoff owns neighboring cue tails. This check
    covers independent content during the common readable core, including
    other styles and ordinary implicit-position captions.
    """
    # Layout and source advances have already been proved for every glyph.
    # Measure the common geometry with the union of its contour footprints;
    # intentional paint spans must not make that geometry unknown again.
    state = caption.state.copy()
    for k in ('bord','xbord','ybord','blur','be'):
        state[k] = max(e.state.get(k,e.state.get('bord',0) if k.endswith('bord') else 0) for e in poses)
    probe = dataclass_replace(caption,state=state,
        text='{'+render_tag('pos',get_pos(caption.text))+'}'+OVERRIDE_RE.sub('',caption.text))
    box = caption_bounds(probe,metric)
    if box is None:
        return False
    for other in parsed.values():
        if (other.kind != 'Dialogue' or other.source_index in members or
                other.start_s >= core[1] or other.end_s <= core[0]):
            continue
        if other.layer.lstrip('-').isdigit() and not int(caption.layer) <= int(other.layer) <= highest:
            continue
        evaluated = event_evaluation(other)
        peer = dataclass_replace(other,state=evaluated.formatting,continuation=evaluated.continuation)
        geometry = {k for k,_ in text_layout_key(peer)}|{'pos','move','clip','iclip','r','fr','a','fe',
            'bord','xbord','ybord','shad','xshad','yshad','blur','be','p'}
        bounded = {'fscx','fscy','bord','xbord','ybord','shad','xshad','yshad','blur','be'}
        samples = [peer.state];live = peer.state.copy();continuation = peer.continuation
        for tag,value in event_override_tokens(peer):
            if tag != 't':
                continue
            changes = tokenize_override(value[1:-1])
            if any(k in geometry-bounded for k,_ in changes):
                return False
            if not changes:
                continue
            transform = parse_effect_transform(value,peer.duration,bounded|set(CAPTION_PAINT_TAGS)|{'alpha','c'},allow_instant=True)
            if transform is None:
                return False
            for name,argument in changes:
                continuation = apply_override(live,name,argument,peer.styles,peer.defaults,continuation)
            samples.append(live.copy())
        # Fixed-anchor, fixed-font scale/stroke changes have a conservative
        # envelope from component maxima, even with overlapping transforms.
        # This keeps distant animated peers eligible without trusting just
        # their initial box or mistaking a growing peer for disjoint content.
        envelope = peer.state.copy()
        for k in bounded:
            values = [st.get(k,st.get(k[1:],0) if k in {'xbord','ybord','xshad','yshad'} else
                             100 if k in {'fscx','fscy'} else 0) for st in samples]
            if any(not math.isfinite(v) or k in {'fscx','fscy'} and v<=0 for v in values):
                return False
            envelope[k] = max(abs(v) for v in values)
        envelope['1a'] = 0  # Bound possible primary ink, including fade-ins.
        peer = dataclass_replace(peer,state=envelope)
        implicit = get_pos(peer.text) is None
        available = None
        if implicit:
            peer,available = _caption_implicit_anchor(peer)
            if peer is None:return False
        peer_box = caption_bounds(peer,metric)
        if implicit and peer_box is not None and available is not None and peer_box[2]-peer_box[0] > available:
            peer_box = None  # Automatic wrapping could change its footprint.
        if (peer_box is None or not (peer_box[2] < box[0] or box[2] < peer_box[0] or
                                     peer_box[3] < box[1] or box[3] < peer_box[1])):
            return False
    return True


def reconstruct_glyph_lifecycles(parsed: dict[int,Event], metric: FontMetrics | None, *,
                                  max_piece_duration: float=.16,
                                  font_report: FontProcessingReport | None=None) -> TextPhaseRowsResult:
    """Replace only complete source-owned, exact-font letter phase rows.

    Geometry/timing determine membership independently of colour. Every glyph
    needs a readable entrance-to-exit path with explicit highlight frames.
    Unclaimed nearby content and competing rows reject atomic replacement.
    """
    events = list(parsed.values())
    if metric is None or not metric.available:
        return TextPhaseRowsResult(events,0,[],{})
    slots,obstacles,endpoints = _index_glyph_phase_slots(parsed,metric,max_piece_duration,font_report)
    lives = _prove_glyph_phase_lives(slots,max_piece_duration)
    lives += _prove_replacement_glyph_lives(endpoints,parsed,metric)
    groups = {}
    bands = {}
    for life in sorted(lives,key=lambda l:get_pos(l.pose.text)[1]):
        e = life.pose
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,e.measurement,text_layout_key(e))
        y = get_pos(e.text)[1]
        anchors = bands.setdefault(key,[])
        if not anchors or abs(y-anchors[-1]) > .02*text_height(e):
            anchors.append(y)
        groups.setdefault((key,len(anchors)-1),[]).append(life)
    runs = []
    for group in groups.values():
        run = []
        for life in sorted(group,key=lambda l:(l.start_s,get_pos(l.pose.text)[0],l.end_s)):
            if run:
                first,last = run[0],run[-1]
                x,y = get_pos(life.pose.text);lx,ly = get_pos(last.pose.text)
                height = text_height(first.pose)
                core_start = max(l.core[0] for l in run+[life]);core_end = min(l.core[1] for l in run+[life])
                if (x <= lx+.02*height or abs(y-ly) > .02*height or
                        life.end_s < last.end_s-.011 or core_end-core_start < .32-1e-6):
                    runs.append(run);run=[]
            run.append(life)
        if run:runs.append(run)
    proposals = []
    for run in runs:
        if len(run) < 4:
            continue
        ordered = [l.pose for l in run];fragments = [l.literal for l in run]
        replacement = any(l.required_members for l in run)
        fit = recover_font_row(metric,ordered,fragments,max_size_error=.05,
                               font_report=font_report,fit_scale=replacement)
        if fit is None:
            continue
        literal,center,sx,sy,alignment = fit
        core = (max(l.core[0] for l in run),min(l.core[1] for l in run))
        start,end = min(l.start_s for l in run),max(l.end_s for l in run)
        members = {e.source_index for l in run for e in l.members}
        if any(not life.required_members <= members for life in run):
            continue
        xs = [get_pos(e.text)[0] for e in ordered];y = statistics.median(get_pos(e.text)[1] for e in ordered);height=text_height(ordered[0])
        if any(e.source_index not in members and e.start_s < core[1] and e.end_s > core[0] and
               (pos is None or abs(pos[1]-y) <= .15*height and
                xs[0]-height <= pos[0] <= xs[-1]+height)
               for e,pos,h in obstacles.get((ordered[0].style,ordered[0].name),[])):
            continue
        # Verify every glyph against the completed literal at the retained
        # font size, not merely successive pairwise spacing fits.
        measured = {**ordered[0].state,'fscx':sx}
        if not matches_authored_glyph_positions(metric,measured,xs,literal,center,.05*height):
            continue
        body = render_merged_caption(ordered,fragments,literal,animated=True,
            an=alignment,pos=(center,y),fscx=sx,fscy=sy,fsp=0)
        if body is None:
            continue
        index = min(members)
        caption = replace_event(ordered[0],text=body,source_index=index,
            start=format_time(start),end=format_time(end),start_s=start,end_s=end,effect='')
        if replacement:
            highest = max(int(e.layer) for life in run for e in life.members)
            if not _glyph_replacement_row_is_clear(caption,core,members,highest,parsed,metric,ordered):
                continue
        row = TextRow(caption,[(e,word,get_pos(e.text)) for e,word in zip(ordered,fragments)],phase_core=core)
        proposals.append((members,row,literal))
    claims = collections.Counter(i for ids,row,literal in proposals for i in ids)
    accepted = [(ids,row,literal) for ids,row,literal in proposals if all(claims[i]==1 for i in ids)]
    removed = set().union(*(ids for ids,row,literal in accepted)) if accepted else set()
    replacements = {row.base.source_index:row.base for ids,row,literal in accepted}
    output = [replacements.get(e.source_index,e) for e in events if e.source_index not in removed or e.source_index in replacements]
    return TextPhaseRowsResult(output,len(removed)-len(accepted),[row for ids,row,literal in accepted],
                               {row.base.source_index:literal for ids,row,literal in accepted})


def _source_fragment_opacity_is_coupled(e: Event) -> bool:
    """A fill visibility profile owns only contours/shadows fading with it."""
    # Fill-only visibility cannot stand for a still-visible outline
    # or shadow. Require every painted plane to share the opacity
    # progression; otherwise it remains independent source content.
    tokens = event_override_tokens(e)
    body = OVERRIDE_RE.sub(lambda m:'{'+''.join('\\'+k+v
        for k,v in tokenize_override(m[1]) if k != 't')+'}',e.text)
    base = evaluate_effective_state(body,e.defaults,e.styles)
    states = [base.formatting]
    continuation = base.continuation
    for tag,value in tokens:
        if tag != 't':
            continue
        transform = parse_effect_transform(value,e.duration,
            set(CAPTION_PAINT_TAGS)|{'alpha','c'},allow_instant=True)
        if transform is None:
            return False
        state = states[-1].copy()
        for k,v in transform[2]:
            continuation = apply_override(state,k,v,e.styles,e.defaults,continuation)
        states.append(state)
    for state in states:
        for channel,widths,default in [(3,('xbord','ybord'),'bord'),(4,('xshad','yshad'),'shad')]:
            if (max(abs(state.get(k,state.get(default,0))) for k in widths)>0 and
                    state.get(f'{channel}a',0) != state.get('1a',0)):
                return False
    return True


def _matching_source_row_fragmentations(rows: list[list[Event]], positions: dict,
                                         metric: FontMetrics) -> bool:
    """Compare literal glyph anchors independently of word/letter segmentation.

    Expand each authored fragment with its exact font at its held size. This
    compares real anchors, including spaces within complete captions, without
    fitting a different size or inventing spacing for the fragmented version.
    Contextual shaping and missing glyphs remain unproved.
    """
    reference = None
    layout = text_layout_key(rows[0][0])
    for row in rows:
        glyphs = []
        for e in row:
            if (text_layout_key(e) != layout or
                    OVERRIDE_RE.search(e.text,re.match(r'(?:\{[^}]*\})*',e.text).end())):
                return False
            # The visible-word map trims edge whitespace. ASS anchoring still
            # includes that authored advance, so measure the literal itself.
            literal = OVERRIDE_RE.sub('',e.text)
            expanded = authored_glyph_positions(metric,e.state,literal,
                                                 positions[e.source_index][0],e.unit)
            if expanded is None:
                return False
            glyphs.extend(expanded)
        if reference is None:
            reference = glyphs
        elif (len(glyphs) != len(reference) or
                any(a != b or abs(x-y)>1.5*row[0].unit
                    for (a,x),(b,y) in zip(reference,glyphs))):
            return False
    return True


def collect_source_text_rows(parsed: dict[int, Event], animated: set[int], *,
                              font_metrics: FontMetrics | None = None) -> CollectedSourceText:
    """Record duplicated layout-stable rows before transformations lose timing.

    This collector records text and geometry only. Effect membership belongs
    to remove_source_fragment_effects; paint and text output belong to
    reconstruct_text_rows. Color-only transforms do not change row geometry.
    Visibility intervals distinguish whole-cue rows from alternating layouts.
    Resolve eligible working events into the returned map, never the inputs.
    Sampled row paint and opacity history belong to separate row successors.
    """
    groups: dict[tuple, list[Event]] = {}
    words = {}
    positions = {}
    resolved = dict(parsed)
    for index, e in parsed.items():
        if e.kind != "Dialogue" or e.duration <= 0:
            continue
        words[e.source_index] = simplify_text(e.text,visible_only=True)[1]
        pos = get_pos(e.text)
        if pos is None:
            move = re.search(r"\\move\(\s*("+NUM+r")\s*,\s*("+NUM+r")", e.text, re.I)
            if move:
                pos = (float(move[1]), float(move[2]))
        positions[e.source_index] = pos
        transforms = [value for block in OVERRIDE_RE.findall(e.text)
                      for tag,value in tokenize_override(block) if tag == "t"]
        moving_layout = any(re.search(r"\\(?:fs(?:c[xy]|p)?|fr[xyz]?|fa[xy]|pos|move|org|clip|iclip|fn|an)(?=[^A-Za-z]|$)",
                                     value,re.I) for value in transforms)
        if (pos is None or not words[e.source_index] or moving_layout or
                re.search(r"\\(?:move|clip|iclip|p[1-9]\d*|org|fad|fade)\b", e.text, re.I)):
            continue
        evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
        e = dataclass_replace(e,state=evaluated.formatting,continuation=evaluated.continuation)
        resolved[index] = e
        if (inline_layout_key(e) or any(abs(e.state.get(k,100)) <= .01 for k in ('fscx','fscy')) or
                any(abs(e.state.get(k,0)) > .001 for k in ("frz","frx","fry","fax","fay"))):
            continue
        profile = ((e.start_s,e.end_s),)
        if transforms and any(tag in {'alpha','1a','r'} for transform in transforms
                              for tag,_ in tokenize_override(transform[1:-1])):
            frozen = freeze_block(''.join(OVERRIDE_RE.findall(e.text)),e.duration,
                                  e.defaults,e.defaults,e.styles,0,prior_opaque_spans=())
            state = frozen.selection.state
            opaque_spans = frozen.selection.opaque_spans
            if not opaque_spans:
                continue
            profile = tuple((e.start_s+a/1000,e.start_s+b/1000) for a,b in opaque_spans)
            e = dataclass_replace(e,state=state,continuation=frozen.selection.continuation)
        if e.state.get('1a',0) != 0:
            continue
        e = dataclass_replace(e,state=dict(e.state),
                              evidence=dataclass_replace(e.evidence,opaque_spans=profile))
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
               e.start,e.end,pos[1],
               tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
                     ("fn","fs","fscx","fscy","fsp","b","i","an")))
        groups.setdefault((*key,profile,e.layer),[]).append(e)

    families: dict[tuple,list[list[Event]]] = {}
    norm = lambda value: "".join(value.split())
    for key, group in groups.items():
        ordered = sorted(group,key=lambda e: positions[e.source_index][0])
        if ((len(ordered) < 4 and (font_metrics is None or not font_metrics.available)) or
                len({positions[e.source_index][0] for e in ordered}) != len(ordered)):
            continue
        text = norm("".join(words[e.source_index] for e in ordered))
        families.setdefault((*key[:-2],text),[]).append(ordered)

    evidence = []
    for rows in families.values():
        mixed = len({tuple(words[e.source_index] for e in row) for row in rows}) > 1
        short_layout = any(len(row)<4 for row in rows)
        profiles = {row[0].evidence.opaque_spans for row in rows}
        measured_alternation = (mixed and len(profiles)>1 and
                                font_metrics is not None and font_metrics.available)
        if measured_alternation:
            if (not _matching_source_row_fragmentations(rows,positions,font_metrics) or
                    not all(_source_fragment_opacity_is_coupled(e) for row in rows for e in row)):
                continue
            members = {e.source_index for row in rows for e in row}
            if any(not e.layer.lstrip('-').isdigit() for row in rows for e in row):
                continue
            low = min(int(e.layer) for row in rows for e in row)
            high = max(int(e.layer) for row in rows for e in row)
            # Reuse the source-row compositing proof. Holding a selected phase
            # over the cue must not move it across independent intervening ink.
            probes = min(rows,key=len)
            poses = [e for row in rows for e in row]
            if any(not _glyph_replacement_row_is_clear(
                    dataclass_replace(e,layer=str(low)),(e.start_s,e.end_s),members,high,
                    parsed,font_metrics,poses) for e in probes):
                continue
        elif short_layout:
            # Complete/short layouts enter only the source alternation proof,
            # never the dense-particle or ordinary stable-row heuristics.
            continue
        chosen = max(rows,key=lambda row:(sum(b-a for a,b in row[0].evidence.opaque_spans),
                                         -row[0].evidence.opaque_spans[0][0] if measured_alternation else 0,
                                         len(row),int(row[0].layer) if row[0].layer.lstrip('-').isdigit() else 0))
        first = chosen[0]
        height = text_height(first)
        if not measured_alternation and any(abs(positions[row[0].source_index][0]-positions[first.source_index][0]) > .5*height or
               abs(positions[row[-1].source_index][0]-positions[chosen[-1].source_index][0]) > .5*height
               for row in rows):
            continue
        anchors: dict[str,list[tuple[float,float]]] = {}
        for paint_row in rows:
            for e in paint_row:
                anchors.setdefault(words[e.source_index],[]).append(positions[e.source_index])
        evidence.append(TextRow(
            first, [(e, words[e.source_index], positions[e.source_index]) for e in chosen],
            paint_rows=rows, source_anchors=anchors))
    return CollectedSourceText(resolved,evidence,words,positions)


def shadow_lyric_fade_core(e: Event) -> tuple[dict,float,float] | None:
    """Prove one shadow glyph's opaque hold between entrance and fade tail.

    Only a short, one-way shadow-opacity entrance and stationary literal
    geometry qualify. Shadow offsets and colour may animate; other geometry,
    alpha pulses, clips, inline state and unsupported fade forms cannot prove
    a handoff. This supplies timing evidence, never a replacement caption.
    """
    e = without_inert_spacing_tail(e)
    evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
    state = evaluated.formatting
    if (e.duration <= 0 or get_pos(e.text) is None or inline_layout_key(e) or
            state.get('1a',0) < 254 or state.get('3a',0) < 254 or
            state.get('borderstyle',1) != 1 or state.get('p',0) or
            not unrotated_text_state(state) or
            not any(abs(state.get(k,state.get('shad',0))) > 0
                    for k in ('xshad','yshad')) or
            any(k in state for k in ('clip','iclip','org'))):
        return None
    tokens = event_override_tokens(e)
    fades = [v for k,v in tokens if k == 'fad']
    if len(fades) != 1 or any(k in {'move','fade','r','alpha','k','kf','ko','kt'} for k,v in tokens):
        return None
    try:
        fade_in,fade_out = [float(v)/1000 for v in fades[0].strip('()').split(',')]
    except ValueError:
        return None
    if (not fades[0].startswith('(') or not fades[0].endswith(')') or
            not all(math.isfinite(v) and v >= 0 for v in (fade_in,fade_out)) or
            fade_out <= 0):
        return None
    entrance = fade_in
    reveals = []
    allowed = {'4a','4c','shad','xshad','yshad'}
    for tag,value in tokens:
        if tag != 't':
            continue
        transform = parse_effect_transform(value,e.duration,allowed,
            allow_instant=True,allow_after_end=True)
        if transform is None:
            return None
        begin,end,changes = transform
        if any(k == '4a' for k,v in changes):
            target = state.copy()
            target_continuation = evaluated.continuation
            for k,v in changes:
                target_continuation = apply_override(target,k,v,e.styles,e.defaults,target_continuation)
            if (target.get('4a') != 0 or end > 500*e.duration or
                    len([1 for k,v in changes if k == '4a']) != 1):
                return None
            reveals.append(end/1000)
    if state.get('4a',0) != 0:
        if state.get('4a',0) < 254 or len(reveals) != 1:
            return None
    elif reveals:
        return None
    entrance = max([entrance]+reveals)
    start,end = e.start_s+entrance,e.end_s-fade_out
    if not e.start_s <= start < end < e.end_s:
        return None
    return {**state,'1a':0,'3a':0,'shad':0,'xshad':0,'yshad':0},start,end


@dataclass(frozen=True)
class CueFadeFamily:
    """Current fragments and their source-proven protected display interval."""
    members: tuple[Event,...]
    core: tuple[float,float]
    xspan: tuple[float,float]


def text_cue_lane(e: Event, pos: tuple[float,float], state: dict) -> tuple:
    return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,
            round(pos[1],4),(int(state.get('an',2))-1)//3)


def derive_staggered_fade_cores(events: list[Event], rows: list[TextRow],
                                sources: dict[int,Event]) -> list[TextRow]:
    """Attach complete source-fade cores to already validated reconstructed rows.

    Each fragment must match one stationary original source in text, font,
    layout and anchor. Protect the intersection of their fully readable
    intervals, without requiring synchronized glyph entrances or exits.
    Borrow all inputs; only returned row successors receive the new core.
    Existing phase proofs and ambiguous or incomplete rows are untouched.
    """
    current = {e.source_index:e for e in events}
    claims = collections.Counter(row.base.source_index for row in rows if not row.virtual)
    forbidden = {'t','move','clip','iclip','org','fade','r','k','kf','ko','kt','fax','fay','p'}
    cache = {}
    output = []
    for row in rows:
        caption = current.get(row.base.source_index)
        pos = get_pos(caption.text) if caption is not None else None
        if (row.virtual or row.phase_core is not None or
                claims[row.base.source_index] != 1 or caption is None or
                caption.kind != 'Dialogue' or caption.text != row.base.text or len(row.pieces) < 2 or
                pos is None or not all(math.isfinite(v) for v in pos) or
                _faded_cue_is_scrolling(caption) or
                not opaque_text_effect_state(caption.state) or
                not unrotated_text_state(caption.state) or
                re.search(r'\\[Nn]|[\r\n]',caption.text) or
                ''.join(OVERRIDE_RE.sub('',caption.text).split()) !=
                ''.join(''.join(word.split()) for piece,word,anchor in row.pieces) or
                len({piece.source_index for piece,word,anchor in row.pieces}) != len(row.pieces)):
            output.append(row)
            continue
        lane = text_cue_lane(caption,pos,caption.state)
        intervals = []
        for piece,word,anchor in row.pieces:
            index = piece.source_index
            source = sources.get(index)
            if index not in cache:
                cache[index] = (_parse_faded_source_evidence(source,forbidden)
                                if source is not None and source.source_index == index and
                                source.kind == 'Dialogue' and not _faded_cue_is_scrolling(source) and
                                not OVERRIDE_RE.search(source.text,
                                    re.match(r'(?:\{[^}]*\})*',source.text).end()) and
                                source.duration > 0 and all(math.isfinite(v) for v in
                                    (source.start_s,source.end_s)) else None)
            proof = cache[index]
            slot = _faded_cue_slot(piece,anchor) if anchor is not None and len(anchor) == 2 else None
            if (source is None or proof is None or not word.strip() or
                    piece.kind != 'Dialogue' or anchor is None or len(anchor) != 2 or
                    not all(math.isfinite(v) for v in anchor) or
                    source.style != caption.style or proof[0] != lane or
                    # Reconstruction serializes anchors to two decimals in
                    # some paths. Permit only that subpixel rounding error;
                    # text/font/layout identity must still match exactly.
                    math.dist(proof[1][0],anchor) > .0071 or
                    slot is None or proof[1][1:] != slot[1:] or
                    OVERRIDE_RE.sub('',piece.text).strip() != word.strip() or
                    proof[2] <= 0 or proof[3] <= 0 or
                    source.start_s < caption.start_s-1e-7 or
                    source.end_s > caption.end_s+1e-7):
                break
            intervals.append((source.start_s+proof[2],source.end_s-proof[3]))
        if len(intervals) != len(row.pieces):
            output.append(row)
            continue
        core = max(start for start,end in intervals),min(end for start,end in intervals)
        output.append(dataclass_replace(row,phase_core=core)
                      if caption.start_s < core[0] < core[1] < caption.end_s else row)
    return output


def collect_faded_cue_families(events: list[Event], rows: list[TextRow],
                               sources: dict[int,Event]) -> list[CueFadeFamily]:
    """Recover fade boundaries across source-backed staggered fragments.

    Every retained fragment must match its original text, anchor and layout.
    Only stationary opaque sources with paint-only transforms qualify; the
    caller may supply sources whose oscillating rotations were already proved
    and normalized. Common starts/ends identify fade families, not arbitrary
    temporal proximity. This helper supplies evidence, never trims timing.
    Rows are borrowed successors adopted from preceding evidence passes.
    """
    provenance = {}
    for row in rows:
        if not row.virtual:
            provenance.setdefault(row.base.source_index,[]).append(row)
    layout = ('fn','fs','fscx','fscy','fsp','an','b','i','u','s','fax','fay','pbo')
    paint = {'c','1c','2c','3c','4c','bord','xbord','ybord','shad','xshad','yshad','blur','be'}
    cache = {}
    def proof(piece,word,pos):
        index = piece.source_index
        if index not in cache:
            source = sources.get(index)
            data = None
            if source is not None and source.kind == 'Dialogue' and source.duration > 0:
                source = without_inert_spacing_tail(source)
                tokens = event_override_tokens(source)
                prefix = re.match(r'(?:\{[^}]*\})*',source.text).end()
                state = effective_state(source.text,source.defaults,source.styles)
                fades = [v for k,v in tokens if k == 'fad']
                if (fades and all(re.fullmatch(r'\(\s*'+NUMBER+r'\s*,\s*'+NUMBER+r'\s*\)',v)
                                  for v in fades) and
                        get_pos(source.text) is not None and not state.get('p',0) and
                        state.get('1a',0) == 0 and unrotated_text_state(state) and
                        not OVERRIDE_RE.search(source.text,prefix) and
                        not any(k in {'move','fade','clip','iclip','org','p','r','k','kf','ko','kt'}
                                for k,v in tokens) and
                        all(k in paint for tag,value in tokens if tag == 't'
                            for k,v in tokenize_override(value[1:-1]))):
                    values = [tuple(float(v)/1000 for v in fade[1:-1].split(',')) for fade in fades]
                    if all(math.isfinite(v) and v >= 0 for fade in values for v in fade):
                        # If repeated fade tags differ, protect the union of
                        # their fully visible intervals. No parser-order guess
                        # can authorize cutting a possibly stable frame.
                        ingress = min(f[0] for f in values)
                        tail = min(f[1] for f in values)
                        if ingress+tail < source.duration:
                            data = (source,state,ingress,tail)
            cache[index] = data
        data = cache[index]
        if data is None:
            return None
        source,state,ingress,tail = data
        if (source.style != piece.style or source.name != piece.name or
                (source.margin_l,source.margin_r,source.margin_v) !=
                (piece.margin_l,piece.margin_r,piece.margin_v) or
                OVERRIDE_RE.sub('',source.text).strip() != word.strip() or
                math.dist(get_pos(source.text),pos) > .001 or
                any(state.get(k,DEFAULT_STATE.get(k)) != piece.state.get(k,DEFAULT_STATE.get(k))
                    for k in layout)):
            return None
        return source,ingress,tail
    groups = {}
    for e in events:
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or pos is None or not opaque_text_effect_state(e.state) or
                not unrotated_text_state(e.state) or e.effect.split(';',1)[0].strip().casefold()
                in {'banner','scroll up','scroll down'}):
            continue
        evidence = provenance.get(e.source_index,[])
        valid = not (len(evidence) > 1 or evidence and evidence[0].base.text != e.text)
        pieces = evidence[0].pieces if valid and evidence else [(e,OVERRIDE_RE.sub('',e.text),pos)]
        details = [proof(piece,word,anchor) for piece,word,anchor in pieces] if valid else []
        # Record one-sided proofs too: a held suffix can prove the outgoing
        # tail while an incoming word phase independently proves its entrance.
        for phase,boundary in ((0,e.start_s),(1,e.end_s)):
            supported = (details and all(item is not None for item in details) and
                all(abs((source.start_s if phase == 0 else source.end_s)-boundary) < .001 and
                    (ingress if phase == 0 else tail) > 0 for source,ingress,tail in details))
            key = (text_cue_lane(e,pos,e.state),phase,round(boundary,2))
            groups.setdefault(key,[]).append((e,pieces,details if supported else None))
    candidates = {}
    for (lane,phase,boundary),items in groups.items():
        if any(details is None for e,pieces,details in items):
            continue
        anchors = [(anchor[0],word,piece) for e,pieces,details in items
                   for piece,word,anchor in pieces if word.strip()]
        anchors.sort(key=lambda item:item[0])
        if (sum(len(word.strip()) for x,word,piece in anchors) < 4 or
                len({round(x,4) for x,word,piece in anchors}) != len(anchors) or
                any(b[0]-a[0] > 2*max(text_height(a[2]),text_height(b[2]))
                    for a,b in zip(anchors,anchors[1:]))):
            continue
        members = tuple(e for e,pieces,details in items)
        details = [item for e,pieces,data in items for item in data]
        core = (min(source.start_s+ingress for source,ingress,tail in details),
                max(source.end_s-tail for source,ingress,tail in details))
        if not core[0] < core[1]:
            continue
        identity = tuple(sorted(e.source_index for e in members))
        family = CueFadeFamily(members,core,(anchors[0][0],anchors[-1][0]))
        if identity in candidates:
            previous = candidates[identity]
            family = CueFadeFamily(members,(min(core[0],previous.core[0]),
                                            max(core[1],previous.core[1])),family.xspan)
        candidates[identity] = family
    # Phase coordinators may already have proved a settled core without an
    # opaque source \fad (for example separate opacity-transform legs). Adopt
    # that evidence only for complete, unchanged current cue groups.
    explicit = {}
    for e in events:
        pos = get_pos(e.text)
        if pos is not None and opaque_text_effect_state(e.state) and unrotated_text_state(e.state):
            explicit.setdefault((text_cue_lane(e,pos,e.state),e.start,e.end),[]).append(e)
    for members in explicit.values():
        evidence = [provenance.get(e.source_index,[]) for e in members]
        if not all(len(rs) == 1 and rs[0].base.text == e.text and rs[0].phase_core is not None
                   and e.start_s <= rs[0].phase_core[0] < rs[0].phase_core[1] <= e.end_s
                   for e,rs in zip(members,evidence)):
            continue
        cores = [rs[0].phase_core for rs in evidence]
        xs = [pos[0] for rs in evidence for piece,word,pos in rs[0].pieces]
        if not xs:
            continue
        core = (min(c[0] for c in cores),max(c[1] for c in cores))
        identity = tuple(sorted(e.source_index for e in members))
        candidates[identity] = CueFadeFamily(tuple(members),core,(min(xs),max(xs)))
    claims = collections.Counter(index for identity in candidates for index in identity)
    return [family for identity,family in candidates.items()
            if all(claims[index] == 1 for index in identity)]


def _faded_cue_is_scrolling(e: Event) -> bool:
    """Exclude legacy scrolling effects from stationary cue evidence."""
    return e.effect.split(';',1)[0].strip().casefold() in {'banner','scroll up','scroll down'}


def _faded_cue_slot(e: Event, pos: tuple[float,float]) -> tuple | None:
    """Identify literal font spans and layout at the original fragment anchor."""
    e = without_inert_spacing_tail(e)
    spans = literal_font_spans(e)
    if not spans or any(re.search(r'\\[Nn]|[\r\n]',text) for text,font in spans):
        return None
    # Outer whitespace does not identify a glyph; internal spaces do.
    spans = list(spans)
    spans[0] = (spans[0][0].lstrip(),spans[0][1])
    spans[-1] = (spans[-1][0].rstrip(),spans[-1][1])
    spans = tuple((text,font.casefold()) for text,font in spans if text)
    if not spans:
        return None
    return (tuple(round(v,4) for v in pos),spans,
            tuple(e.state.get(k,DEFAULT_STATE.get(k)) for k in
                  ('fs','fscx','fscy','fsp','an','b','i','u','s','q','pbo','encoding')))


def _apply_faded_cue_families(context: FadedCueContext, cue_families: list[CueFadeFamily] | None) -> None:
    """Regroup only complete proved families, preserving separately painted cues."""
    for family in cue_families or ():
        members = family.members
        key = text_cue_lane(members[0],get_pos(members[0].text),members[0].state)
        timed = context.groups.get(key,{})
        ids = {e.source_index for e in members}
        if not ids <= {e.source_index for group in timed.values() for e in group}:
            continue
        start,end = min(e.start_s for e in members),max(e.end_s for e in members)
        timing = (round(start,2),round(end,2))
        # Do not absorb a separately painted caption into a proved family.
        if any(e.source_index not in ids for e in timed.get(timing,())):
            continue
        for old in list(timed):
            timed[old] = [e for e in timed[old] if e.source_index not in ids]
            if not timed[old]:
                del timed[old]
        timed[timing] = list(members)
        context.family_proofs[key,timing] = (*family.core,*family.xspan)


def _find_faded_cue_collisions(groups: dict) -> tuple[list,set]:
    """Find isolated consecutive overlaps before inspecting source overrides."""
    # Examine source overrides only for boundaries involved in a collision.
    # This avoids another expensive state-parsing pass over large animations.
    pairs = []
    wanted = set()
    for key,timed in groups.items():
        ordered = sorted(timed)
        previous_end = float('-inf')
        for i,(start,end) in enumerate(ordered[:-1]):
            next_start,next_end = ordered[i+1]
            if (start < next_start < end < next_end and
                    previous_end <= next_start and
                    (i+2 == len(ordered) or ordered[i+2][0] >= end)):
                pairs.append((key,(start,end),(next_start,next_end)))
                wanted.update(((key,0,start),(key,1,end),
                               (key,0,next_start),(key,1,next_end)))
            previous_end = max(previous_end,end)
    return pairs,wanted


def _parse_faded_source_evidence(e: Event, forbidden: set) -> tuple | None:
    """Require one finite source fade and stationary opaque fragment identity."""
    tokens = event_override_tokens(e)
    fades = [value for tag,value in tokens if tag == 'fad']
    if (len(fades) != 1 or not fades[0].startswith('(') or not fades[0].endswith(')') or
            any(tag in forbidden for tag,value in tokens)):
        return None
    try:
        fade_in,fade_out = [float(v) / 1000 for v in fades[0].strip('()').split(',')]
    except ValueError:
        return None
    # A final syllable may begin partway through the cue-wide fade tail.
    # Its nominal fade can exceed this phase's duration; the complete row
    # must still agree on a positive non-fading cue interval below.
    if not all(math.isfinite(v) and v >= 0 for v in (fade_in,fade_out)):
        return None
    pos = get_pos(e.text)
    evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
    state = evaluated.formatting
    if (pos is None or not opaque_text_effect_state(state) or
            not unrotated_text_state(state)):
        return None
    key = text_cue_lane(e,pos,state)
    identity = _faded_cue_slot(dataclass_replace(e,state=state,continuation=evaluated.continuation),pos)
    if identity is None:
        return None
    return key,identity,fade_in,fade_out


def _collect_faded_cue_evidence(source_events: dict[int,Event], wanted: set) -> FadedCueEvidence:
    """Inspect only collision boundaries, preferring complete shadow-fade proofs."""
    evidence = FadedCueEvidence({},set())
    families = {key[:5] for key,phase,time in wanted}
    boundaries = {(key[:5],phase,time) for key,phase,time in wanted}
    forbidden = {'t','move','clip','iclip','org','fade','k','kf','ko','kt'}
    for e in source_events.values():
        family = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v)
        start,end = round(e.start_s,2),round(e.end_s,2)
        if (e.kind != 'Dialogue' or _faded_cue_is_scrolling(e) or family not in families or
                r'\fad(' not in e.text.lower() or
                (family,0,start) not in boundaries and (family,1,end) not in boundaries):
            continue
        shadow_core = shadow_lyric_fade_core(e)
        if shadow_core is not None:
            state,core_start,core_end = shadow_core
            pos = get_pos(e.text)
            key = text_cue_lane(e,pos,state)
            identity = _faded_cue_slot(dataclass_replace(e,state=state,continuation=OverrideContinuation()),pos)
            if identity is not None:
                for phase,time,core in ((0,start,core_start),(1,end,core_end)):
                    phase_key = (key,phase,time)
                    if phase_key in wanted:
                        evidence.phase_slots.setdefault(phase_key,{}).setdefault(identity,set()).add(round(core,2))
                        evidence.shadow_phases.add(phase_key)
            continue
        source = _parse_faded_source_evidence(e,forbidden)
        if source is None:
            continue
        key,identity,fade_in,fade_out = source
        for phase,time,fade,core in ((0,start,fade_in,start+fade_in),
                                     (1,end,fade_out,end-fade_out)):
            phase_key = (key,phase,time)
            if fade > 0 and phase_key in wanted:
                evidence.phase_slots.setdefault(phase_key,{}).setdefault(identity,set()).add(round(core,2))
    return evidence


def _prove_faded_source_core(evidence: FadedCueEvidence, key: tuple, timing: tuple,
                              identities: list) -> tuple | None:
    """Require complete unambiguous entrances and tails for the fully visible row."""
    unique = set(identities)
    entrance = evidence.phase_slots.get((key,0,timing[0]),{})
    tail = evidence.phase_slots.get((key,1,timing[1]),{})
    if (None in unique or len(unique) != len(identities) or
            unique != entrance.keys() or unique != tail.keys()):
        return None
    starts = set().union(*entrance.values())
    ends = set().union(*tail.values())
    shadow_pair = ((key,0,timing[0]) in evidence.shadow_phases and
                   (key,1,timing[1]) in evidence.shadow_phases)
    if shadow_pair:
        # Staggered reveal endpoints can differ between letters. Every
        # glyph still needs one unambiguous entrance and tail; protect the
        # interval during which the complete row is fully visible.
        if any(len(v) != 1 for v in (*entrance.values(),*tail.values())):
            return None
    elif len(starts) != 1 or len(ends) != 1:
        return None
    core_start,core_end = (max(starts),min(ends)) if shadow_pair else (next(iter(starts)),next(iter(ends)))
    xs = [identity[0][0] for identity in identities]
    return ((core_start,core_end,min(xs),max(xs))
                          if timing[0] < core_start < core_end < timing[1] else None)


def _prove_faded_cue_core(context: FadedCueContext, evidence: FadedCueEvidence,
                           key: tuple, timing: tuple) -> tuple | None:
    """Prefer family and ordered phase cores before fragment source-fade proofs."""
    members = context.groups[key][timing]
    if (key,timing) in context.family_proofs:
        return context.family_proofs[key,timing]
    if len(members) == 1:
        e = members[0]
        row_evidence = context.provenance.get(e.source_index,[])
        if (len(row_evidence) == 1 and row_evidence[0].phase_core is not None and
                row_evidence[0].base.text == e.text):
            row = row_evidence[0]
            start,end = row.phase_core
            xs = [pos[0] for piece,text,pos in row.pieces]
            return ((start,end,min(xs),max(xs))
                if timing[0] < start < end < timing[1] else None)
    identities = []
    for e in members:
        row_evidence = context.provenance.get(e.source_index,[])
        if len(row_evidence) > 1 or row_evidence and row_evidence[0].base.text != e.text:
            identities.append(None)
        elif row_evidence:
            identities.extend(_faded_cue_slot(piece,pos) for piece,text,pos in row_evidence[0].pieces)
        else:
            identities.append(_faded_cue_slot(e,get_pos(e.text)))
    return _prove_faded_source_core(evidence,key,timing,identities)


def _select_readable_core_handoff(left: tuple, right: tuple, a: tuple,
                                   b: tuple) -> float | None:
    """Choose a representable centisecond inside both the collision and protected gap."""
    if a[1] > b[0]:return None
    # A handoff inside both the collision and the gap between stable cores
    # preserves every stable frame and all exposure outside the collision.
    low,high = max(right[0],a[1]),min(left[1],b[0])
    if low > high:
        return None
    # ASS cue boundaries have centisecond precision. A rounded midpoint
    # outside this interval would cut a protected frame.
    first,last = math.ceil(low*100-1e-7),math.floor(high*100+1e-7)
    if first > last:
        return None
    boundary = min(last/100,max(first/100,round((low+high)/2,2)))
    return boundary


def _select_faded_cue_handoff(left: tuple, right: tuple, a: tuple | None,
                               b: tuple | None) -> float | None:
    """Require shared row extent before the common readable-core clock proof."""
    if a is None or b is None or min(a[3],b[3]) < max(a[2],b[2]):return None
    return _select_readable_core_handoff(left,right,a,b)


def synchronize_faded_cue_handoffs(context: FadedCueContext, pairs: list,
                                   proven: dict) -> dict:
    """Choose shared safe boundaries for uniquely paired separate text lanes.

    Touching captions can supply an authored boundary. Overlapping lanes can
    instead share the intersection of their source-protected handoff windows.
    All evidence is borrowed; ambiguous associations keep independent timing.
    """
    records = {}
    def caption(key,timing):
        members = context.groups[key][timing]
        if len(members) != 1:
            return None
        e = members[0]
        size = float(e.state.get('fs',20))
        literal = OVERRIDE_RE.sub('',e.text).replace(r'\h',' ').strip()
        if (not math.isfinite(size) or size <= 0 or
                not all(math.isfinite(v) for v in get_pos(e.text)) or
                not literal or re.search(r'\\[Nn]|[\r\n]',literal) or
                e.state.get('p',0) or
                any(tag in {'move','t','clip','iclip','org','fade','fad','k','kf','ko','kt','p','r'}
                    for tag,value in event_override_tokens(e))):
            return None
        evidence = context.provenance.get(e.source_index,[])
        if len(evidence) > 1 or evidence and evidence[0].base.text != e.text:
            return None
        xs = [anchor[0] for piece,word,anchor in evidence[0].pieces] if evidence else [get_pos(e.text)[0]]
        if not xs or not all(math.isfinite(x) for x in xs):
            return None
        return literal,(min(xs),max(xs)),size
    for key,left,right in pairs:
        a,b = proven.get((key,left)),proven.get((key,right))
        if _select_faded_cue_handoff(left,right,a,b) is None:
            continue
        outgoing,incoming = caption(key,left),caption(key,right)
        if outgoing is None or incoming is None or outgoing[0] == incoming[0]:
            continue
        low = math.ceil(max(right[0],a[1])*100-1e-7)
        high = math.floor(min(left[1],b[0])*100+1e-7)
        records[key,left,right] = (low,high,a[:2],b[:2],outgoing,incoming)
    anchors = {}
    for key,timed in context.groups.items():
        ordered = sorted(timed)
        for left,right in zip(ordered,ordered[1:]):
            if left[1] != right[0]:
                continue
            outgoing,incoming = caption(key,left),caption(key,right)
            if outgoing is None or incoming is None or outgoing[0] == incoming[0]:
                continue
            boundary = round(left[1]*100)
            if any(t not in (left,right) and t[0] <= boundary/100 <= t[1] for t in ordered):
                continue
            anchors[key,left,right] = (boundary,boundary,left,right,outgoing,incoming)
    def related(one,two):
        key,left,right = one
        other,other_left,other_right = two
        if key == other:
            return False
        a,b = records[one],(records.get(two) or anchors[two])
        size = max(a[4][2],a[5][2],b[4][2],b[5][2])
        # Require distinct visual rows, including top/bottom translations.
        if not math.isfinite(size) or size <= 0 or abs(key[5]-other[5]) < .5*size:
            return False
        if max(a[0],b[0]) > min(a[1],b[1]):
            return False
        for phase in (2,3):
            if max(a[phase][0],b[phase][0]) >= min(a[phase][1],b[phase][1]):
                return False
            if two in anchors and not (b[phase][0] <= a[phase][0] and a[phase][1] <= b[phase][1]):
                return False
            x,y = a[phase+2][1],b[phase+2][1]
            if min(x[1],y[1]) < max(x[0],y[0]):
                return False
        return True
    neighbors = {identity:[] for identity in records}
    for one in records:
        for two in (*records,*anchors):
            if related(one,two):
                neighbors[one].append(two)
    result,visited = {},set()
    for identity in records:
        if identity in visited:
            continue
        component,pending = set(),[identity]
        while pending:
            one = pending.pop()
            if one in component:
                continue
            component.add(one)
            pending.extend(two for two in neighbors[one] if two in records)
        visited.update(component)
        references = {two for one in component for two in neighbors[one] if two in anchors}
        all_items = component | references
        # At most one transition per lane; conflicting authored boundaries
        # or competing overlap pairs cannot establish a common handoff.
        if len({item[0] for item in all_items}) != len(all_items):
            continue
        # An authored transition must also be unique to this component.
        if any(other not in component and ref in linked
               for ref in references for other,linked in neighbors.items()):
            continue
        values = [records.get(item) or anchors[item] for item in all_items]
        low,high = max(v[0] for v in values),min(v[1] for v in values)
        if low > high or len(all_items) < 2:
            continue
        boundary = min(high,max(low,round((low+high)/2)))/100
        result.update({item:boundary for item in component})
    return result


def _trim_owned_cue_backing(events: list[Event], rows: list[TextRow],
                             replacements: dict[int,dict]) -> None:
    """Share a proved foreground handoff with its exact retained paint copies.

    Use ownership returned by the stack coordinator, including complete row
    successors. Neither similar text nor nearby timing can establish ownership.
    Ambiguous parents, incomplete joined paint rows and changed copies remain
    untouched. This only adds timing successors to the caller-owned buffer.
    """
    current = {e.source_index:e for e in events}
    owners,snapshots,provenance = {},{},{}
    for row in rows:
        if row.virtual or row.base.source_index not in current:
            continue
        parent = current[row.base.source_index]
        if row.base.text != parent.text:
            continue
        provenance.setdefault(parent.source_index,[]).append(row)
        for paint in row.owned_backing:
            owners.setdefault(paint.source_index,set()).add(parent.source_index)
            snapshots.setdefault(paint.source_index,[]).append(paint)
    def owner(piece):
        # Source-backed paint may already have acquired boundary phases;
        # timing is deliberately separate from its exact rendered identity.
        claims = owners.get(piece.source_index,set())
        copies = snapshots.get(piece.source_index,[])
        return (next(iter(claims)) if len(claims) == 1 and copies and
                all(piece.fields()[:1]+piece.fields()[3:] == p.fields()[:1]+p.fields()[3:]
                    for p in copies) else None)
    for paint in events:
        parent = owner(paint)
        parents = [parent] if parent is not None else []
        if not parents:
            evidence = provenance.get(paint.source_index,[])
            if len(evidence) == 1 and evidence[0].pieces:
                parents = [owner(piece) for piece,word,pos in evidence[0].pieces]
        if not parents or any(p is None for p in parents) or not any(p in replacements for p in parents):
            continue
        parents = set(parents)
        # A joined backing may have several word owners, but all must still
        # belong to the same cue before and after the proposed handoff.
        before = {(current[p].start,current[p].end) for p in parents}
        after = {(replacements.get(p,{}).get('start_s',current[p].start_s),
                  replacements.get(p,{}).get('end_s',current[p].end_s)) for p in parents}
        if len(before) != 1 or len(after) != 1:
            continue
        start,end = next(iter(after))
        start,end = max(paint.start_s,start),min(paint.end_s,end)
        if start >= end:
            continue
        changes = replacements.setdefault(paint.source_index,{})
        if start > paint.start_s:
            changes.update(start=format_time(start),start_s=start)
        if end < paint.end_s:
            changes.update(end=format_time(end),end_s=end)


def trim_faded_cue_overlaps(events: list[Event], rows: list[TextRow],
                            source_events: dict[int,Event], *,
                            cue_families: list[CueFadeFamily] | None = None) -> tuple[list[Event],int]:
    """Give consecutive static rows a clean handoff within their source fades.

    Reconstructed rows supply their original fragment anchors. Every retained
    fragment, including separate font spans, must match complete source fade
    entrances and tails at the cue's boundaries. Matched fragment phases can
    instead supply their complete ordered word-activation interval. Only rows
    whose protected cores are disjoint qualify. Ambiguous or incomplete groups,
    simultaneous cores and independent positions keep their original timing.
    Consume the caller's adopted row successors without updating their cores
    or historical fragment intervals. Only returned event timing changes.
    """
    provenance: dict[int,list[TextRow]] = {}
    for row in rows:
        if not row.virtual:
            provenance.setdefault(row.base.source_index,[]).append(row)
    groups: dict[tuple,dict[tuple,list[Event]]] = {}
    for e in events:
        pos = get_pos(e.text)
        if (e.kind != 'Dialogue' or _faded_cue_is_scrolling(e) or pos is None or
                not opaque_text_effect_state(e.state) or not unrotated_text_state(e.state)):
            continue
        timing = (round(e.start_s,2),round(e.end_s,2))
        groups.setdefault(text_cue_lane(e,pos,e.state),{}).setdefault(timing,[]).append(e)
    context = FadedCueContext(provenance,groups,{})
    _apply_faded_cue_families(context,cue_families)
    pairs,wanted = _find_faded_cue_collisions(context.groups)
    if not pairs:
        return events,0
    evidence = _collect_faded_cue_evidence(source_events,wanted)
    proven = {}
    candidates = {(key,timing) for key,left,right in pairs for timing in (left,right)}
    for key,timing in candidates:
        proven[key,timing] = _prove_faded_cue_core(context,evidence,key,timing)

    synchronized = synchronize_faded_cue_handoffs(context,pairs,proven)
    replacements = {}
    trimmed = 0
    for key,left,right in pairs:
        a,b = proven.get((key,left)),proven.get((key,right))
        boundary = synchronized.get((key,left,right),_select_faded_cue_handoff(left,right,a,b))
        if boundary is None:
            continue
        for timing,time_field in ((left,'end'),(right,'start')):
            for e in context.groups[key][timing]:
                changes = replacements.setdefault(e.source_index,{})
                # A staggered family contains fragments that can already end
                # before (or begin after) the common handoff. Never extend them.
                value = min(e.end_s,boundary) if time_field == 'end' else max(e.start_s,boundary)
                changes.update({time_field:format_time(value),time_field+'_s':value})
        trimmed += 1
    _trim_owned_cue_backing(events,rows,replacements)
    return [replace_event(e,**replacements[e.source_index])
            if e.source_index in replacements else e for e in events],trimmed


def normalize_animated_rotations(events: dict[int,Event]) -> dict[int,Event]:
    """Expose opaque oscillating text as upright source rows of fixed geometry.

    Preserve paint animation and provenance; only rotations and their unused
    origin are removed. Moving/resizing text is frozen normally later, where
    its complete pose can be selected at the same instant.
    """
    result = dict(events)
    for index,e in events.items():
        if (e.kind != 'Dialogue' or e.duration <= 0 or
                not re.search(r'\\t\s*\(',e.text) or
                not re.search(r'\\fr(?:[xyz])?(?=[+\-\d.])',e.text)):
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',e.text).group()
        if not prefix or OVERRIDE_RE.search(e.text,len(prefix)):
            continue
        tokens = [token for block in OVERRIDE_RE.findall(prefix)
                  for token in tokenize_override(block)]
        if any(tag in {'move','r','p'} for tag,_ in tokens):
            continue
        changing = {'fs','fscx','fscy','fsp','fn','b','i','u','s','a','an','r','p',
                    'fax','fay','pos','move','org','clip','iclip','t'}
        if any(tag in changing for name,value in tokens if name == 't'
               for tag,_ in tokenize_override(value[1:-1])):
            continue
        # One-way entrances/exits remain recognizable by the source effect
        # matchers. Only a repeated oscillation supplies an early static row.
        turns = []
        for name,value in tokens:
            if name == 't':
                for tag,argument in tokenize_override(value[1:-1]):
                    if tag in {'fr','frz'}:
                        try: turns.append(math.remainder(float(argument),360))
                        except ValueError: pass
        if len(turns) < 2 or not any(a*b < 0 for a,b in zip(turns,turns[1:])):
            continue
        frozen = freeze_block(''.join(OVERRIDE_RE.findall(prefix)),e.duration,
                              e.defaults,e.defaults,e.styles,0,prefer_upright=True)
        state = frozen.selection.state
        if not frozen.selection.pose.upright_rotation or not unrotated_text_state(state):
            continue
        if not (state.get('1a',0) == 0 or state.get('1a',0) >= 254 and
                state.get('3a',0) == 0 and
                max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0):
            continue
        block = re.sub(r'\\fr(?:[xyz])?'+NUMBER,'',prefix)
        block = re.sub(r'\\org\([^)]*\)','',block)
        result[index] = replace_event(e,text=r'{\frz0\frx0\fry0}'+block+e.text[len(prefix):])
    return result


def adjacent_sustained_geometry(sources: dict[int,Event], targets: list[Event]) -> dict[int,dict]:
    """Prove a short phase's layout from a touching, longer source hold.

    Exact text/style context, compatible boundary geometry and one unique
    held layout are required. Rotation and paint are intentionally separate.
    A matching letter elsewhere on the screen supplies no evidence.
    """
    def family(e):
        return (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,OVERRIDE_RE.sub('',e.text))
    wanted = {family(e) for e in targets}
    layout = ('pos','fn','fs','fscx','fscy','fsp','an','b','i','u','s','fax','fay','pbo','q')
    forbidden = {*layout,'fr','frz','frx','fry','r','p','clip','iclip','org'}
    starts,ends = {},{}
    for held in sources.values():
        key = family(held)
        if (held.kind != 'Dialogue' or held.duration < .25 or key not in wanted or
                inline_layout_key(held) or get_pos(held.text) is None):
            continue
        tokens = event_override_tokens(held)
        if (any(tag in {'move','fade','clip','iclip','org','p'} for tag,value in tokens) or
                any(tag in forbidden for name,value in tokens if name == 't'
                    for tag,value in tokenize_override(value[1:-1]))):
            continue
        state = effective_state(held.text,held.defaults,held.styles)
        if (state.get('p',0) or state.get('fs',20) <= 0 or
                not upright_text_state(state,include_shadow=True,include_outline=True)):
            continue
        changing_alpha = {tag for name,value in tokens if name == 't'
                          for tag,_ in tokenize_override(value[1:-1])
                          if tag in {'alpha','1a','3a','4a'}}
        visible_channel = '1a' if state.get('1a',0) < 239 else (
            '3a' if state.get('3a',0) < 239 and
            max(abs(state.get(k,state.get('bord',0))) for k in ('xbord','ybord')) > 0 else '4a')
        if 'alpha' in changing_alpha or visible_channel in changing_alpha:
            continue
        fades = [re.findall(NUMBER,value) for name,value in tokens if name == 'fad']
        if len(fades) > 1 or any(len(values) != 2 for values in fades):
            continue
        fade = sum(max(0,float(v)) for values in fades for v in values)/1000
        dwell = max(0,held.duration-fade)
        if dwell < .25:
            continue
        data = (held,state,dwell)
        starts.setdefault((key,round(held.start_s*100)),[]).append(data)
        ends.setdefault((key,round(held.end_s*100)),[]).append(data)
    proven = {}
    for original in targets:
        if (original.kind != 'Dialogue' or original.duration <= 0 or inline_layout_key(original) or
                any(tag in {'clip','iclip','org','p'} for tag,_ in event_override_tokens(original))):
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',original.text).group()
        evaluation,transforms,_,_ = _freeze_inputs(''.join(OVERRIDE_RE.findall(prefix)),original.duration,
            original.defaults,original.defaults,original.styles)
        options = {}
        for at,index,boundary in ((0,ends,original.start_s),
                                  (original.duration*1000,starts,original.end_s)):
            pose = sample_transform_state(evaluation.formatting,transforms,at,original.styles,original.defaults,
                                          continuation=evaluation.continuation).formatting
            for centisecond in range(round(boundary*100)-1,round(boundary*100)+2):
                for held,state,dwell in index.get((family(original),centisecond),[]):
                    touching = held.end_s if at == 0 else held.start_s
                    if abs(touching-boundary) > .011 or dwell < max(.25,2*original.duration):
                        continue
                    # Centisecond cue rounding can cut a millisecond-based
                    # entrance slightly short. Allow two script pixels of
                    # boundary rounding, never a different screen location.
                    unit = 2*max(original.unit,held.unit)
                    if any(pose.get(k,DEFAULT_STATE.get(k)) != state.get(k,DEFAULT_STATE.get(k))
                           for k in layout if k not in {'pos','fs','fscx','fscy','fsp'}):
                        continue
                    if (pose.get('pos') is None or math.dist(pose['pos'],state['pos']) > unit or
                            abs(pose.get('fs',20)-state.get('fs',20)) > unit or
                            abs(pose.get('fsp',0)-state.get('fsp',0)) > unit or
                            any(abs(pose.get(k,100)-state.get(k,100))*state.get('fs',20)/100 > unit
                                for k in ('fscx','fscy'))):
                        continue
                    key = tuple(state.get(k,DEFAULT_STATE.get(k)) for k in layout)
                    options[key] = {k:state[k] for k in layout if k in state}
        if len(options) == 1:
            proven[original.source_index] = next(iter(options.values()))
    return proven


def prefer_surviving_upright_poses(events: list[Event], sources: dict[int,Event]) -> list[Event]:
    """Apply the general rotation policy after source effect cleanup.

    Earlier proofs use their established frozen geometry. Revisit only intact
    retained text, preserving its selected paint, timing and assembled rows.
    """
    geometry = {'fn','fs','fscx','fscy','fsp','b','i','u','s','an','a','pos','org',
                'fr','frz','frx','fry','fax','fay','pbo'}
    def inline_geometry(e):
        if not inline_layout_key(e):
            return False
        painted = False
        for part in re.split(r'(\{[^}]*\})',e.text):
            if part.startswith('{'):
                if painted and any(tag in geometry|{'r','t','p','clip','iclip'}
                                   for tag,_ in tokenize_override(part[1:-1])):
                    return True
            elif part:
                painted = True
        return False
    targets = {}
    for e in events:
        original = sources.get(e.source_index)
        if (e.kind == 'Dialogue' and original is not None and e.style == original.style and
                any(abs(e.state.get(k,0)) > .001 for k in ('frz','frx','fry')) and
                not inline_geometry(e) and not inline_geometry(original) and
                re.search(r'\\t\s*\(',original.text) and
                re.search(r'\\fr(?:[xyz])?(?=[+\-\d.])',original.text) and
                OVERRIDE_RE.sub('',e.text) == OVERRIDE_RE.sub('',original.text)):
            targets[e.source_index] = original
    if not targets:
        return events
    output = []
    proven_geometry = None
    for e in events:
        original = targets.get(e.source_index)
        if original is None:
            output.append(e)
            continue
        prefix = re.match(r'(?:\{[^}]*\})*',original.text).group()
        frozen = freeze_block(''.join(OVERRIDE_RE.findall(prefix)),original.duration,
                              original.defaults,original.defaults,original.styles,0,
                              prefer_upright=True)
        state = frozen.selection.state
        if not frozen.selection.pose.upright_rotation or not unrotated_text_state(state):
            output.append(e)
            continue
        if proven_geometry is None:
            proven_geometry = adjacent_sustained_geometry(sources,list(targets.values()))
        protected = dict(frozen.selection.pose.sustained_geometry or ())
        state.update(proven_geometry.get(original.source_index,{}))
        state.update(protected)
        prefix_end = re.match(r'(?:\{[^}]*\})*',e.text).end()
        paint = ''.join('\\'+tag+value for block in OVERRIDE_RE.findall(e.text[:prefix_end])
                        for tag,value in tokenize_override(block) if tag not in geometry)
        pose = ''.join(render_tag(k,v) for k,v in state.items() if k in geometry-{'a','fr'})
        output.append(replace_event(e,text='{'+paint+pose+'}'+e.text[prefix_end:]))
    return output


def infer_vector_text_cues(
    runs: dict, parsed: dict[int, Event], metric: FontMetrics, authored_styles: set[str], *,
    font_report: FontProcessingReport | None=None, outline_matcher: FontOutlineMatcher | None=None,
) -> list[tuple[Event, str]]:
    """Recover missing cue evidence only from decoded complete animation rows.

    Ordered instantaneous opacity switches prove syllable activation intervals.
    A synchronized full line may share that interval when its font, layer,
    placement margins, frame boundaries and entrance/exit fades agree. Neither
    guessed words nor a renderer-dependent frame rounding offset supplies timing.
    """
    if outline_matcher is None:
        outline_matcher = FontOutlineMatcher(metric)
    alphabet = set()
    for e in parsed.values():
        if e.kind == 'Dialogue' and not re.search(r'\\p[1-9]',e.text,re.I):
            alphabet.update(simplify_text(e.text,visible_only=True)[1])
    families = {}
    for style,group in runs.items():
        if style in authored_styles:
            continue
        for key,items in group:
            if len(items) < 3:
                continue
            lane = key[:6]+(key[6][1],key[7],round(items[0][0].start_s,2),round(items[-1][0].end_s,2))
            families.setdefault(lane,[]).append((key,items))
    decoded = []
    for family in families.values():
        family.sort(key=lambda run:run[0][6][0])
        activations = []
        for key,items in family:
            first = items[0][0]
            switches = []
            for tag,value in event_override_tokens(first):
                if tag != 't':
                    continue
                transform = parse_effect_transform(value,first.duration,{'1a','3a'},
                    allow_instant=True,allow_after_end=True)
                if transform is None or transform[0] != transform[1]:
                    continue
                target = first.defaults.copy()
                target_continuation = OverrideContinuation()
                for name,arg in transform[2]:
                    target_continuation = apply_override(target,name,arg,first.styles,first.defaults,target_continuation)
                if any(name == '1a' for name,arg in transform[2]):
                    switches.append((first.start_s+transform[0]/1000,target.get('1a',0)))
            if (len(switches) != 2 or switches[0][1] != 255 or switches[1][1] != 0 or
                    switches[0][0] >= switches[1][0]):
                break
            activation = (switches[0][0],switches[1][0])
            # Generated frames may retain transforms scheduled beyond their
            # own end. Those annotations alone are not timing evidence: the
            # subsequent frames must actually hide/show this backing glyph.
            starts = [e.start_s for e,p,s in items]
            def opacity_at(at):
                offset = bisect_right(starts,at)-1
                if offset < 0 or at >= items[offset][0].end_s:
                    return None
                event,_,base = items[offset]
                transforms = []
                for tag,value in event_override_tokens(event):
                    if tag == 't':
                        t = parse_effect_transform(value,event.duration,{'1a','3a','alpha'},
                            allow_instant=True,allow_after_end=True)
                        if t is not None:
                            transforms.append((t[0],t[1],1,t[2]))
                return sample_transform_state(base,transforms,1000*(at-event.start_s),
                    event.styles,event.defaults,continuation=event.continuation).formatting.get('1a',0)
            inside = [activation[0]+fraction*(activation[1]-activation[0]) for fraction in (.25,.75)]
            outside = [(a+b)/2 for a,b in ((items[0][0].end_s,activation[0]),
                        (activation[1],items[-1][0].start_s)) if a < b]
            if (not outside or any((opacity_at(at) or 0) < 254 for at in inside) or
                    not any((value := opacity_at(at)) is not None and value < 16 for at in outside)):
                break
            activations.append(tuple(round(v,2) for v in activation))
        core = None
        if (len(activations) == len(family) and all(a[0] <= b[0] and a[1] <= b[1]
                for a,b in zip(activations,activations[1:]))):
            core = (activations[0][0],activations[-1][1])
        first,last = family[0][1][0][0],family[0][1][-1][0]
        state = family[0][1][0][2]
        sync = (first.layer,first.name,first.margin_l,first.margin_r,first.margin_v,
                tuple(state.get(k) for k in ('fn','fs','fscx','fscy','b','i')),
                round(first.start_s,2),round(last.end_s,2))
        # Require whole-frame alpha entrances and exits for cross-row timing.
        def edge_fade(e,alpha):
            return any(tag == 't' and not re.match(r'\(\s*'+NUMBER,value) and
                (t := parse_effect_transform(value,e.duration,{'1a','3a'})) is not None and
                any(k == '1a' and v.upper().removeprefix('&H').rstrip('&') == alpha
                    for k,v in t[2]) for tag,value in event_override_tokens(e))
        synchronized = all(edge_fade(items[0][0],'00') and edge_fade(items[-1][0],'FF')
                           for key,items in family)
        if core is None and not synchronized:
            continue
        row,words = [],[]
        for key,items in family:
            sample,state = items[0][0],items[0][2]
            face = metric.matching_face(str(state.get('fn','')),state.get('b',0),False)
            if face is None:
                break
            path = tuple(v if isinstance(v,str) else statistics.median(item[1][i] for item in items)
                         for i,v in enumerate(items[0][1]))
            try:
                text = outline_matcher.decode_cubic_outline(face,path,state.get('fs',20),sample.unit,alphabet)
            except (OSError,ValueError,RuntimeError):
                text = None
            if text is None:
                break
            row.append(replace_event(sample,text=render_simplified_caption(state,text,p=0,fsp=0,measurement=sample.measurement)))
            words.append(text)
        else:
            if sum(c.isalnum() for text in words for c in text) < 3:
                continue
            text = words[0]
            if len(row) > 1:
                fit = recover_font_row(metric, row,words,max_size_error=.2, font_report=font_report)
                if fit is not None:
                    text = fit[0]
                elif all(not any(c.isspace() for c in word) for word in words):
                    text = ''.join(words)
                    if fit_fragment_anchor(metric, row[0].state,[get_pos(e.text)[0] for e in row],
                            words,text,row[0].unit,max_size_error=.2) is None:
                        continue
                else:
                    continue
            decoded.append((family,row,words,text,core,sync,synchronized))
    shared = {}
    for family,row,words,text,core,sync,synchronized in decoded:
        if core is not None and synchronized:
            shared.setdefault(sync,set()).add(core)
    cues = []
    for family,row,words,text,core,sync,synchronized in decoded:
        if core is None and synchronized and len(shared.get(sync,())) == 1:
            core = next(iter(shared[sync]))
        sample = family[0][1][0][0]
        if core is None or not sample.start_s < core[0] < core[1] < family[0][1][-1][0].end_s:
            continue
        # Internal cue evidence only; no inferred Comment is written to output.
        body = text if len(words) == 1 else ''.join(r'{\k0}'+word for word in words)
        # Keep measured spaces for the caption, while fragments identify paths.
        cues.append((replace_event(sample,kind='Comment',text=body,start=format_time(core[0]),
            start_s=core[0],end=format_time(core[1]),end_s=core[1]),text))
    return cues


def _index_authored_vector_text_cues(parsed: dict[int,Event]) -> tuple[dict,set,set]:
    """Index unique unformatted text/karaoke comments and styles with possible drawing cues."""
    cues = {}
    for e in parsed.values():
        if e.kind != 'Comment' or e.duration <= 0:
            continue
        text = simplify_text(e.text,visible_only=True)[1]
        if (not text.strip() or re.search(r'\\[Nn]|[\r\n]',text) or
                any(tag not in {'k','kf','ko','kt'} for tag,value in event_override_tokens(e))):
            continue
        cues.setdefault((e.style,e.start_s,e.end_s,text),e)
    authored_styles = {cue.style for cue in cues.values()}
    styles = authored_styles|{e.style for e in parsed.values() if e.kind == 'Dialogue' and
                             re.search(r'\\p1(?![\dA-Za-z])',e.text,re.I)}
    return cues,authored_styles,styles


def _profile_vector_text_drawing(e: Event, geometry: set, transform_paint: set) -> tuple | None:
    """Validate stationary cubic drawing geometry and build its font/layout/skeleton identity."""
    tokens = event_override_tokens(e)
    if (inline_layout_key(e) or any(tag in {'move','clip','iclip','org','r'} or
            tag == 't' and any(k not in transform_paint for k,v in
                tokenize_override(value.strip('()'))) for tag,value in tokens)):
        return None
    evaluated = evaluate_effective_state(e.text,e.defaults,e.styles)
    state = evaluated.formatting
    pos = get_pos(e.text)
    if (pos is None or state.get('p',0) != 1 or int(state.get('an',5)) != 5 or
            state.get('pbo',0) or state.get('borderstyle',1) != 1 or
            not unrotated_text_state(state) or any(abs(state.get(k,0)) > .001
                for k in ('fax','fay','u','s','i')) or
            any(state.get(k,100) != 100 for k in ('fscx','fscy')) or
            not all(math.isfinite(v) for v in (*pos,state.get('fs',20)))):
        return None
    path = geometry_key(e.text)
    skeleton = tuple(v if isinstance(v,str) else None for v in path)
    if not path or any(v not in {'m','l','b'} for v in path if isinstance(v,str)):
        return None
    key = (e.style,e.layer,e.name,e.margin_l,e.margin_r,e.margin_v,pos,
           tuple(state.get(k,DEFAULT_STATE.get(k)) for k in sorted(geometry)),skeleton)
    return key,path,evaluated


def _index_vector_text_sources(parsed: dict[int,Event], styles: set) -> tuple[dict,dict]:
    """Keep admissible drawing groups separate from same-style readable backing text."""
    groups, backing = {}, {}
    geometry = {'fn','fs','fsp','fscx','fscy','an','b','i','u','s','pbo','encoding'}
    transform_paint = {'alpha','1a','2a','3a','4a','c','1c','2c','3c','4c',
                       'bord','xbord','ybord','blur','be'}
    for e in parsed.values():
        if e.kind != 'Dialogue' or e.style not in styles or e.duration <= 0:
            continue
        if not re.search(r'\\p1(?![\dA-Za-z])',e.text,re.I):
            if simplify_text(e.text,visible_only=True)[1].strip():
                backing.setdefault(e.style,[]).append(e)
            continue
        profile = _profile_vector_text_drawing(e,geometry,transform_paint)
        if profile is not None:
            key,path,evaluated = profile
            sample = dataclass_replace(e,state=evaluated.formatting,continuation=evaluated.continuation)
            groups.setdefault(key,[]).append((sample,path,evaluated.formatting))
    return groups,backing


def _group_vector_text_runs(groups: dict) -> dict:
    """Form time-connected noncompeting drawing runs with the original gap/overlap tolerances."""
    runs = {}
    for key,items in groups.items():
        items.sort(key=lambda item:(item[0].start_s,item[0].end_s))
        components = []
        latest = float('-inf')
        for item in items:
            if not components or item[0].start_s > latest+.011:
                components.append([])
            components[-1].append(item)
            latest = max(latest,item[0].end_s)
        for component in components:
            if any(b[0].start_s < a[0].end_s-.001 for a,b in zip(component,component[1:])):
                continue
            runs.setdefault(key[0],[]).append((key,component))
    return runs


def _measure_vector_text_outline(run: tuple, text: str, context: VectorTextFitContext) -> list | None:
    """Prove exact command skeleton and sampled median control points at a plausible font size."""
    key,items = run
    state = items[0][2]
    face = context.metric.matching_face(str(state.get('fn','')),state.get('b',0),False)
    if face is None:
        if context.font_report is not None:
            context.font_report.missing_families.add(str(state.get('fn','')))
        return None
    outline = context.metric.cubic_outline(face,text)
    if outline is None or tuple(v if isinstance(v,str) else None for v in outline[0]) != key[-1]:
        return None
    sample = [items[i] for i in sorted({round(j*(len(items)-1)/4) for j in range(5)})]
    measured = tuple(v if isinstance(v,str) else statistics.median(item[1][i] for item in sample)
                     for i,v in enumerate(outline[0]))
    fitted = fit_cubic_points(outline[0],measured)
    if fitted is None:
        return None
    scale,_,_,error = fitted
    nominal = context.metric.ass_em_scale(face)
    if nominal is None:
        return None
    nominal *= state.get('fs',20)/outline[1]
    # Font drawing exporters and renderers use different line metrics.
    # Permit the same modest sizing variance, never arbitrary path fits.
    tolerance = max(items[0][0].unit,.05*state.get('fs',20))
    if nominal <= 0 or abs(scale-nominal) > .2*nominal or error > tolerance:
        return None
    return sample


def _select_vector_text_paint(sample: list, text: str, context: VectorTextFitContext) -> Event | None:
    """Freeze sampled drawings and choose the longest opaque sample for recovered caption paint."""
    visible = []
    for e,path,state in sample:
        body,_,_ = simplify_visual_text(e.text,context.max_blur,e.duration,e.defaults,e.styles,2)
        frozen = replace_event(e,text=body)
        if frozen.state.get('1a',0) < 16:
            visible.append(frozen)
    if not visible:
        return None
    chosen = max(visible,key=lambda e:e.duration)
    result = replace_event(chosen,text=render_simplified_caption(chosen.state,text,p=0,measurement=chosen.measurement))
    return result


def _fit_vector_text_outline(run: tuple, text: str, context: VectorTextFitContext) -> Event | None:
    """Cache both rejected and reconstructed outline fits by the original source/text identity."""
    key,items = run
    cache_key = (items[0][0].source_index,text)
    if cache_key in context.cache:
        return context.cache[cache_key]
    context.cache[cache_key] = None
    sample = _measure_vector_text_outline(run,text,context)
    if sample is None:
        return None
    result = _select_vector_text_paint(sample,text,context)
    if result is None:
        return None
    context.cache[cache_key] = result
    return result


def _select_vector_text_cue_runs(runs: dict, cue: Event, start: float, end: float) -> dict:
    """Admit drawing runs covering a cue within its original allowance and group horizontal lanes."""
    candidates = {}
    for run in runs.get(cue.style,()):
        key,items = run
        allowance = max(.25*cue.duration,2*statistics.median(e.duration for e,p,s in items))
        if (items[0][0].start_s > start+.011 or items[-1][0].end_s < end-.011 or
                items[0][0].start_s < start-allowance or items[-1][0].end_s > end+allowance):
            continue
        lane = key[:6]+(key[6][1],key[7])
        candidates.setdefault(lane,[]).append(run)
    return candidates


def _recover_vector_text_fragment_anchor(
    row: list[Event], words: list[str], text: str, metric: FontMetrics, *,
    font_report: FontProcessingReport | None=None,
) -> tuple | None:
    """Use the existing space-aware recovery, then only the original no-space anchor fallback."""
    x,y = get_pos(row[0].text)
    if len(row) > 1:
        measured = [dataclass_replace(e,state={**e.state,'fsp':0}) for e in row]
        recovered = recover_font_row(metric, measured,words,max_size_error=.2, font_report=font_report)
        if recovered is not None and recovered[0] == text:
            x = recovered[1]
        elif not any(c.isspace() for c in text):
            x = fit_fragment_anchor(metric, measured[0].state,
                [get_pos(e.text)[0] for e in row],words,text,row[0].unit,max_size_error=.2)
            if x is None:
                return None
        else:
            return None
    return x,y


def _reconstruct_vector_text_family(family: list, words: list[str], text: str, cue: Event, start: float, end: float, context: VectorTextFitContext) -> tuple | None:
    """Fit every fragment before rendering one authored caption and recording all consumed sources."""
    row = [_fit_vector_text_outline(run,word,context) for run,word in zip(family,words)]
    if any(e is None for e in row):
        return None
    anchor = _recover_vector_text_fragment_anchor(row,words,text,context.metric, font_report=context.font_report)
    if anchor is None:
        return None
    x,y = anchor
    body = render_merged_caption(row,words,text,animated=True,an=5,pos=(x,y),fscx=100,fscy=100)
    if body is None:
        return None
    members = {e.source_index for run in family for e,p,s in run[1]}
    first = min(members)
    caption = replace_event(row[0],source_index=first,text=body,start=cue.start,
        start_s=start,end=cue.end,end_s=end,effect='')
    return members,caption


def _propose_vector_text_cue(cue: Event, start: float, end: float, text: str, runs: dict, backing: dict, context: VectorTextFitContext) -> tuple | None:
    """Reject text-backed cues and require one fully reconstructed whole-line or fragment family."""
    if any(min(e.end_s,end)-max(e.start_s,start) >= .5*cue.duration
           for e in backing.get(cue.style,())):
        return None
    candidates = _select_vector_text_cue_runs(runs,cue,start,end)
    fragments = [part.strip() for part in re.split(
        r'\{[^}]*\\[kK](?:f|o|t)?\d+[^}]*\}',cue.text) if part.strip()]
    options = []
    for family in candidates.values():
        family.sort(key=lambda run:run[0][6][0])
        words = [text] if len(family) == 1 else fragments
        if (len(words) != len(family) or ''.join(''.join(w.split()) for w in words) !=
                ''.join(text.split())):
            continue
        option = _reconstruct_vector_text_family(family,words,text,cue,start,end,context)
        if option is not None:
            options.append(option)
    return options[0] if len(options) == 1 else None


def _apply_vector_text_ownership(parsed: dict[int,Event], proposals: list) -> tuple[dict[int,Event],int]:
    """Accept only uniquely owned drawing sources, preserving dictionary order and recovered-cue count."""
    claims = collections.Counter(index for members,caption in proposals for index in members)
    accepted = [(members,caption) for members,caption in proposals
                if all(claims[index] == 1 for index in members)]
    if not accepted:
        return parsed,0
    consumed = set().union(*(members for members,caption in accepted))
    result = {index:e for index,e in parsed.items() if index not in consumed}
    result.update((caption.source_index,caption) for members,caption in accepted)
    return result,len(accepted)


def recover_vector_text_cues(
    parsed: dict[int, Event], metric: FontMetrics | None, max_blur: float=0.0, *,
    font_report: FontProcessingReport | None=None, outline_matcher: FontOutlineMatcher | None=None,
) -> tuple[dict[int, Event], int]:
    """Recover authored captions proven by complete exact-font drawing rows.

    A comment is only a text candidate. Each whole line or karaoke fragment
    must match the font's contour commands and control points at a plausible
    common size, across a time-connected drawing run covering its cue. Existing
    font spacing checks prove fragment order and authored spaces. Clipped,
    moving, rotated, incomplete, competing and already text-backed cues reject.
    No effect names, source-line annotations or subtitle-specific values matter.
    """
    if metric is None or not metric.available:
        return parsed,0
    if outline_matcher is not None and outline_matcher.metrics is not metric:
        raise ValueError('Outline matcher must use the supplied FontMetrics owner.')
    if outline_matcher is None:
        outline_matcher = FontOutlineMatcher(metric)
    cues,authored_styles,styles = _index_authored_vector_text_cues(parsed)
    if not styles:
        return parsed,0
    groups,backing = _index_vector_text_sources(parsed,styles)
    runs = _group_vector_text_runs(groups)
    for cue,text in infer_vector_text_cues(runs,parsed,metric,authored_styles, font_report=font_report, outline_matcher=outline_matcher):
        cues.setdefault((cue.style,cue.start_s,cue.end_s,text),cue)
    context = VectorTextFitContext(metric,max_blur,{}, font_report=font_report)
    proposals = []
    for (_,start,end,text),cue in cues.items():
        proposal = _propose_vector_text_cue(cue,start,end,text,runs,backing,context)
        if proposal is not None:
            proposals.append(proposal)
    return _apply_vector_text_ownership(parsed,proposals)


def _prepare_text_document(document: SubtitleDocument, path: Path) -> SubtitleDocument:
    """Prepare the text engine's source conventions without reparsing records.

    Dialogue state is resolved after simplification by replace_event; unchanged
    comments are resolved immediately. WrapStyle remains measurement metadata
    at the later caption boundary, as in the established text engine.
    """
    lines = document.lines
    resolution_value = next((line.split(':',1)[1].strip() for line in lines
                             if line.strip().lower().startswith('playresy:')), '288')
    try:
        resolution_y = float(resolution_value)
        if not math.isfinite(resolution_y) or resolution_y <= 0:
            raise ValueError
    except ValueError:
        print(f"Warning: {path.name}: invalid PlayResY; using 288 for geometry.")
    events = {}
    for index,event in document.events.items():
        evaluated = (evaluate_effective_state(event.text,event.defaults,document.styles)
                     if event.kind != 'Dialogue' else OverrideEvaluation({},OverrideContinuation()))
        events[index] = dataclass_replace(event,state=evaluated.formatting,
                                          continuation=evaluated.continuation)
    return dataclass_replace(document,lines=lines,events=events)


def _prepare_source_text(
    source: SubtitleDocument, animated_sources: set[int], config: SimplifyConfig,
    font_metrics: FontMetrics | None, *, font_report: FontProcessingReport | None=None,
    outline_matcher: FontOutlineMatcher | None=None,
) -> PreparedSourceText:
    """Recover source rows and geometry before freezing their effects."""
    parsed_by_line = source.events
    source_rows = []
    paint_timelines=()
    source_effects = 0
    vector_text_recovered = 0
    working_by_line = parsed_by_line
    timing_sources = parsed_by_line
    if config.level == 1:
        working_by_line, vector_text_recovered = recover_vector_text_cues(
            working_by_line,font_metrics,config.max_blur, font_report=font_report, outline_matcher=outline_matcher)
        # Identify original cue geometry once. Existing stages consume that
        # evidence before transformations can extend a lyric through its tail.
        working_by_line = normalize_animated_rotations(working_by_line)
        timing_sources = working_by_line
        working_by_line, shrinking_effects = collapse_shrinking_glyph_rows(
            working_by_line,font_metrics,config.max_blur)
        lifecycles = reconstruct_glyph_lifecycles(working_by_line,font_metrics,
            max_piece_duration=config.short_duration,font_report=font_report)
        working_by_line = {e.source_index:e for e in lifecycles.events}
        source_data = collect_source_text_rows(working_by_line,animated_sources,font_metrics=font_metrics)
        # Retain the pre-collapse timing snapshot, adopting resolved formatting
        # only where it still refers to the same authored working event.
        timing_sources = {index:source_data.events[index]
                          if working_by_line.get(index) is event else event
                          for index,event in timing_sources.items()}
        working_by_line = source_data.events
        removal = remove_source_fragment_effects(
            list(working_by_line.values()),source_data.rows,source_data.words,source_data.positions,animated_sources,
            font_metrics=font_metrics, font_report=font_report)
        source_effects = removal.removed_effects
        paint_timelines=_collect_caption_paint_timelines(source_data,removal.paint_families,removal.events,font_metrics)
        reconstruction = reconstruct_text_rows(
            removal.events,source_data.words,{},None,animated_sources,
            source_rows=removal.rows,source_only=True, font_report=font_report)
        source_events,source_rows = reconstruction.events,reconstruction.rows+lifecycles.rows
        source_effects += shrinking_effects+lifecycles.removed_count
        working_by_line = {e.source_index:e for e in source_events}
    return PreparedSourceText(working_by_line,timing_sources,source_rows,source_effects,vector_text_recovered,paint_timelines)


def _freeze_event_effects(
    source: SubtitleDocument,
    prepared: PreparedSourceText,
    config: SimplifyConfig,
) -> FrozenTextEvents:
    """Freeze event effects and retain explicit blank positions for spacing."""
    lines = source.lines
    styles = source.styles
    parsed_by_line = source.events
    scaled_borders = source.scaled_borders
    working_by_line = prepared.events
    simplified_events: list[Event] = []
    vector_events: list[Event] = []
    backdrops: list[tuple[Event,list]] = []
    visible_map: dict[int, str] = {}
    space_map: dict[tuple, set[float]] = {}
    dropped_drawings = 0
    original_dialogues = 0
    blank_events: list[Event] = []

    for idx, line in enumerate(lines):
        e = parsed_by_line.get(idx)
        if e is None:
            continue
        if e.kind != "Dialogue":
            simplified_events.append(e)
            continue
        original_dialogues += 1
        if idx not in working_by_line:
            continue
        e = working_by_line[idx]
        if e.duration<=0:
            # ASS events with an empty/reversed interval cannot be displayed.
            dropped_drawings += 1
            continue
        if config.level == 1 and re.search(r"\\p[1-9]\d*(?![\dA-Za-z])",e.text,re.I):
            # A cheap opaque rectangle may hide text baked into the video.
            # Keep it as a candidate until we know a retained caption actually
            # sits above it. Other drawings are excluded from this text-stage
            # candidate pool; backdrop reconstruction evaluates source drawings later.
            drawing,words,chars = simplify_visual_text(
                e.text,config.max_blur,e.duration,e.defaults,styles,2)
            candidate = replace_event(e,text=drawing,effect="")
            geometry = coverage_geometry(candidate,scaled_borders)
            if chars and not words and geometry is not None and geometry[2]:
                points = geometry[0]
                xs,ys = {x for x,y in points},{y for x,y in points}
                corners = {(x,y) for x in xs for y in ys}
                if (len(xs)==len(ys)==2 and len(points) in (4,5) and
                        set(points)==corners and
                        all(a==c or b==d for (a,b),(c,d) in
                            zip(points,points[1:]+points[:1]))):
                    backdrops.append((candidate,points))
            if chars and not words and not simplify_text(e.text,visible_only=True)[1]:
                # Both the frozen drawing and the original drawing switches
                # prove there is no text. Its backdrop candidate is already
                # recorded; standard simplification would only freeze it again before dropping.
                visible_map[idx] = ''
                dropped_drawings += 1
                continue
        new_text, visible, drawing_chars = simplify_visual_text(
            e.text, config.max_blur, e.duration, resolve_event_style(styles,e.style), styles, config.level,
            upright_crossings=False)
        visible_map[idx] = visible
        if drawing_chars:
            if config.max_drawing_chars <= 0 or drawing_chars <= config.max_drawing_chars:
                vector_events.append(replace_event(e, text=new_text, effect=""))
            else:
                dropped_drawings += 1
            continue
        if not visible:
            # Position-only events in per-character FX mark word spaces in some
            # generated lyrics. Keep their locations for text reconstruction.
            pos = get_pos(new_text)
            if (pos is not None and
                    not re.search(r"\\p\d", e.text, re.I)):
                key = (e.start, e.end, e.style, e.name, e.row)
                space_map.setdefault(key, set()).add(round(pos[0] / e.unit, 1) * e.unit)
                blank_events.append(replace_event(e, text=new_text))
            # A dialogue event with no remaining text is generally a vector drawing/effect.
            dropped_drawings += 1
            continue
        caption = replace_event(e, text=new_text, effect="")
        if get_pos(caption.text) is not None and not inline_layout_key(caption):
            caption = dataclass_replace(caption,evidence=dataclass_replace(
                caption.evidence,frame_pose_intervals=_frame_pose_intervals(caption)))
        simplified_events.append(caption)

    assign_layout(simplified_events + blank_events, visible_map)
    space_map.clear()
    for e in blank_events:
        pos = get_pos(e.text)
        space_map.setdefault((e.start,e.end,e.style,e.name,e.row),set()).add(pos[0])
    return FrozenTextEvents(
        simplified_events,vector_events,backdrops,visible_map,space_map,blank_events,
        {'original':original_dialogues,'dropped':dropped_drawings})


def _consolidate_text_events(
    source: SubtitleDocument, prepared: PreparedSourceText, frozen: FrozenTextEvents,
    animated_sources: set[int], config: SimplifyConfig, font_metrics: FontMetrics | None, *,
    font_report: FontProcessingReport | None=None,
) -> tuple[list[Event], list[Event], dict[str, int]]:
    """Reduce text copies, reconstruct rows and settle source-proved cue timing."""
    styles = source.styles
    parsed_by_line = source.events
    scaled_borders = source.scaled_borders
    simplified_events = frozen.captions
    vector_events = frozen.vectors
    visible_map = frozen.visible
    space_map = frozen.spaces
    dropped_drawings = frozen.statistics['dropped']
    blank_events = frozen.blanks
    source_rows = prepared.rows
    source_effects = prepared.effects_removed
    timing_sources = prepared.timing_sources
    stacked_text_copies_flattened = masked_decorations = 0
    glow_phases = 0
    progressive_reveals = 0
    jitter_frames = jitter_stacks = word_echoes = 0
    if config.level == 1:
        jitter = flatten_complete_line_jitter(
            simplified_events,visible_map,styles,max_piece_duration=config.short_duration,
            source_events=parsed_by_line)
        simplified_events,jitter_frames,jitter_stacks = jitter.events,jitter.frames,jitter.stacks
        echoes = remove_owned_word_echoes(simplified_events,visible_map,jitter.captions,
            parsed_by_line,font_metrics,max_piece_duration=config.short_duration)
        simplified_events,word_echoes = echoes.events,echoes.removed_effects
        reveal = collapse_progressive_text_reveals(
            simplified_events,visible_map)
        simplified_events,progressive_reveals = reveal.events,reveal.removed_count
        visible_map.update(reveal.visibility_updates)
        simplified_events, font_decorations = remove_fragmented_font_decorations(
            simplified_events,visible_map,font_metrics,parsed_by_line)
        dropped_drawings += font_decorations
        simplified_events, masked_decorations = remove_masked_glyph_effects(
            simplified_events, visible_map, font_metrics, animated_sources)
        stacks = flatten_stacked_text_copies(
            simplified_events, visible_map, animated_sources,
            max_piece_duration=config.short_duration,source_events=parsed_by_line,
            font_metrics=font_metrics,collect_rows=True)
        simplified_events,stacked_text_copies_flattened = stacks.events,stacks.removed_count
        glow_phases = stacks.phase_merged
        source_rows = source_rows+stacks.rows

    stacked_text_copies_flattened += jitter_stacks
    sign_copies_removed = 0
    if config.level == 1:
        simplified_events, sign_copies_removed = reduce_static_sign_copies(
            simplified_events, visible_map)

    # Reconstruct each glyph's complete lifetime before trying to assemble rows.
    lyric_boundaries = _index_lyric_boundaries(simplified_events,visible_map)
    simplified_events, phase_merged = coalesce_lyric_phases(
        simplified_events, visible_map,lyric_boundaries=lyric_boundaries)
    phase_merged += glow_phases
    joined_blanks, _ = coalesce_lyric_phases(blank_events, visible_map)
    for e in joined_blanks:
        pos = get_pos(e.text)
        key = (e.start, e.end, e.style, e.name, e.row)
        space_map.setdefault(key, set()).add(round(pos[0] / e.unit, 1) * e.unit)

    tiles_joined = 0
    # Deprecated legacy simplification path; retain for reference and compatibility.
    if config.level == 2:
        simplified_events, tiles_joined = join_text_clip_tiles(simplified_events)

    # For visual signs, choose their visible fill before same-layer dedup can
    # discard a brighter effect copy merely because it appeared later.
    text_copies_removed = 0
    # Deprecated legacy simplification path; retain for reference and compatibility.
    if config.level == 2:
        simplified_events, text_copies_removed = reduce_text_layers(
            simplified_events, visible_map, vector_events)

    # Deduplicate proven positioned copies; matching does not require adjacency.
    simplified_events, deduped = deduplicate_layers(simplified_events, visible_map)
    lyric_merged = 0
    overlap_removed = full_copies_removed = 0
    if config.level == 1:
        simplified_events, overlap_removed = collapse_matching_lyric_layers(
            simplified_events, visible_map, font_metrics)
        copies = collapse_full_lyric_copies(
            simplified_events, visible_map)
        simplified_events,full_copies_removed = copies.events,copies.removed_count
        visible_map.update(copies.visibility_updates)
    simplified_events, merged = merge_frame_animation(
        simplified_events, visible_map,
        max_piece_duration=config.short_duration,
        max_gap=config.short_gap,
        merge_near_static=config.level == 1,
        lyric_boundaries=lyric_boundaries,
    )
    text_effect_sequences_frozen = jitter_frames
    # Counter names remain compatible with older batch reports.
    staggered_rows = fullwidth_merged = 0
    progressive_rows = progressive_reveals
    overlaid_letters = covered_fragments = cue_overlaps_trimmed = 0
    if config.level == 1:
        simplified_events, sequence_frames = flatten_text_effect_sequences(
            simplified_events, visible_map, styles, animated_sources,
            source_events=parsed_by_line,font_metrics=font_metrics, font_report=font_report,
            lyric_boundaries=lyric_boundaries)
        text_effect_sequences_frozen += sequence_frames
        full_lines = remove_letters_over_full_lines(
            simplified_events,visible_map,parsed_by_line,collect_rows=True,font_metrics=font_metrics)
        simplified_events,overlaid_letters = full_lines.events,full_lines.removed_count
        authored_rows = full_lines.row_additions
        current = {e.source_index:e for e in simplified_events}
        authored_rows = authored_rows+[dataclass_replace(row,base=current[row.base.source_index])
            for row in source_rows if row.phase_core is not None and
            row.base.source_index in current and
            visible_map.get(row.base.source_index) == OVERRIDE_RE.sub('',row.base.text)]
        if full_lines.source_updates:
            successors = {id(parsed_by_line[index]):event for index,event in full_lines.source_updates.items()}
            parsed_by_line.update(full_lines.source_updates)
            # Timing evidence can retain the same authored source objects in
            # another map. Adopt only exact aliases, never unrelated rewrites.
            for index,event in timing_sources.items():
                if id(event) in successors:
                    timing_sources[index] = successors[id(event)]
        reconstruction = reconstruct_text_rows(
            simplified_events, visible_map, space_map, font_metrics, animated_sources,
            source_rows=source_rows,source_events=parsed_by_line, font_report=font_report)
        simplified_events,row_evidence = reconstruction.events,reconstruction.rows
        lyric_merged = reconstruction.merged_count
        deduped += reconstruction.duplicate_count
        visible_map.update(reconstruction.visibility_updates)
        covered = remove_covered_fragment_effects(
            simplified_events, visible_map, row_evidence+authored_rows, animated_sources,parsed_by_line,font_metrics)
        simplified_events,row_evidence = covered.events,covered.rows
        covered_fragments = covered.removed_effects+source_effects+word_echoes
        row_evidence = derive_staggered_fade_cores(
            simplified_events,row_evidence,parsed_by_line)
        cue_families = collect_faded_cue_families(
            simplified_events,row_evidence,timing_sources)
        simplified_events, cue_overlaps_trimmed = trim_faded_cue_overlaps(
            simplified_events,row_evidence,parsed_by_line,cue_families=cue_families)
    covered_vectors = 0
    vector_copies_removed = vector_glows_removed = vector_frames_removed = excess_vectors = 0
    # Deprecated legacy simplification path; retain for reference and compatibility.
    if config.level == 2:
        simplified_events, remaining_copies = reduce_text_layers(simplified_events, visible_map, vector_events)
        text_copies_removed += remaining_copies
        vector_events, vector_copies_removed = reduce_vector_layers(vector_events)
        vector_events, vector_frames_removed = freeze_vector_sequences(vector_events, config.short_duration)
        vector_events, vector_glows_removed = remove_covered_vector_glows(vector_events)
        vector_events, covered_vectors = remove_fully_covered_vectors(vector_events, scaled_borders)
        vector_events, excess_vectors = cap_vector_cues(vector_events, config.max_vectors_per_cue)
        simplified_events = sorted(simplified_events + vector_events, key=lambda e: e.source_index)
    statistics = frozen.statistics.copy()
    statistics.update({
        'lyric_merged': lyric_merged,
        'overlap_removed': overlap_removed,
        'full_copies_removed': full_copies_removed,
        'merged': merged,
        'text_effect_sequences_frozen': text_effect_sequences_frozen,
        'staggered_rows': staggered_rows,
        'fullwidth_merged': fullwidth_merged,
        'progressive_rows': progressive_rows,
        'overlaid_letters': overlaid_letters,
        'covered_fragments': covered_fragments,
        'cue_overlaps_trimmed': cue_overlaps_trimmed,
        'covered_vectors': covered_vectors,
        'vector_copies_removed': vector_copies_removed,
        'vector_glows_removed': vector_glows_removed,
        'vector_frames_removed': vector_frames_removed,
        'excess_vectors': excess_vectors,
        'tiles_joined': tiles_joined,
        'text_copies_removed': text_copies_removed,
        'stacked_text_copies_flattened': stacked_text_copies_flattened,
        'masked_decorations': masked_decorations,
        'phase_merged': phase_merged,
        'deduped': deduped+sign_copies_removed,
        'dropped': dropped_drawings,
    })
    return simplified_events,vector_events,statistics


def _finalize_text_layout(
    source: SubtitleDocument, frozen: FrozenTextEvents, simplified_events: list[Event],
    vector_events: list[Event], statistics: dict[str, int], animated_sources: set[int],
    config: SimplifyConfig, font_metrics: FontMetrics | None, *,
    font_report: FontProcessingReport | None=None,
) -> tuple[list[Event], dict[str, int]]:
    """Finish geometry, then consolidate static rows and shared visibility."""
    styles = source.styles
    parsed_by_line = source.events
    visible_map = frozen.visible
    space_map = frozen.spaces
    backdrops = frozen.backdrops
    deduped = statistics['deduped']
    lyric_merged = statistics['lyric_merged']
    text_effect_sequences_frozen = statistics['text_effect_sequences_frozen']
    cue_overlaps_trimmed = statistics['cue_overlaps_trimmed']
    dropped_drawings = statistics['dropped']
    backdrops_retained = 0
    if config.level == 1:
        captions = [(e,get_pos(e.text)) for e in simplified_events
                    if e.kind=="Dialogue" and visible_map.get(e.source_index) and
                    not e.state.get("p",0) and get_pos(e.text) is not None and
                    e.layer.lstrip("-").isdigit()]
        raised_layers = {}
        for backdrop,points in backdrops:
            order = (int(backdrop.layer),backdrop.source_index)
            pad = .5*backdrop.unit
            covered_captions = []
            for caption,pos in captions:
                source = parsed_by_line.get(caption.source_index,caption)
                if (not source.layer.lstrip("-").isdigit() or
                        (int(source.layer),source.source_index)<=order or
                        backdrop.start_s > caption.start_s+.001 or
                        backdrop.end_s < caption.end_s-.001):
                    continue
                if polygon_covers_box(points,(pos[0]-pad,pos[1]-pad,pos[0]+pad,pos[1]+pad)):
                    covered_captions.append(caption)
            if covered_captions:
                vector_events.append(backdrop)
                backdrops_retained += 1
                dropped_drawings -= 1
                # Reconstructed lyrics may have been moved to layer zero.
                # Restore their order above any backdrop that now survives.
                for caption in covered_captions:
                    raised_layers[caption.source_index] = max(
                        raised_layers.get(caption.source_index,int(caption.layer)),int(backdrop.layer)+1)
        simplified_events = [replace_event(e,layer=str(raised_layers[e.source_index]))
                             if e.source_index in raised_layers else e for e in simplified_events]
        simplified_events = sorted(simplified_events+vector_events,key=lambda e:e.source_index)
        simplified_events = prefer_surviving_upright_poses(simplified_events,parsed_by_line)
        # Late generators emit full state headers. Compact them only after
        # source-dependent effect/timing proofs, then remove exact duplicates
        # whose formerly redundant tag spelling hid their identity.
        simplified_events = compact_static_overrides(simplified_events,config.max_blur)
        simplified_events, final_duplicates = deduplicate_layers(simplified_events,visible_map)
        deduped += final_duplicates
        # Finished geometry can connect differently divided animation phases.
        # Run after rotation/origin cleanup, without disturbing earlier source
        # effect proofs. The shared overlap pass owns the proven cue handoffs.
        translated = collapse_translated_phase_rows(
            simplified_events,visible_map,font_metrics, font_report=font_report)
        simplified_events,translated_merged = translated.events,translated.removed_count
        visible_map.update(translated.visibility_updates)
        fragments = collapse_fragment_phase_rows(
            simplified_events,visible_map,font_metrics, font_report=font_report)
        simplified_events,phase_rows_merged = fragments.events,fragments.removed_count
        visible_map.update(fragments.visibility_updates)
        phase_rows = translated.rows+fragments.rows
        text_effect_sequences_frozen += translated_merged+phase_rows_merged
        if phase_rows:
            simplified_events, phase_overlaps = trim_faded_cue_overlaps(
                simplified_events,phase_rows,{})
            cue_overlaps_trimmed += phase_overlaps
            simplified_events = compact_static_overrides(simplified_events,config.max_blur)
        # Effect removal and timing cleanup can uncover complete static rows.
        # Reuse the same source comments, spacing and neighbor checks without
        # extending lifetimes or selecting new animation/foreground paint.
        reconstruction = reconstruct_text_rows(
            simplified_events,visible_map,space_map,font_metrics,animated_sources,
            static_only=True, font_report=font_report)
        simplified_events,final_rows_merged = reconstruction.events,reconstruction.merged_count
        visible_map.update(reconstruction.visibility_updates)
        lyric_merged += final_rows_merged
        if final_rows_merged:
            simplified_events = compact_static_overrides(simplified_events,config.max_blur)

    # Canonicalize exact static phases before common-visibility reconstruction.
    # Preserve its row/eligibility boundaries rather than dropping source roles
    # or feeding the consumer unnecessary subdivisions of identical paint.
    static_merged = 0
    if config.level in (1,2):
        simplified_events, static_merged = merge_static_timed_copies(
            simplified_events, styles, font_metrics=font_metrics,
            row_sources=animated_sources if config.level == 1 else None)

    # Run after all source/effect/timing proofs. Core rows must never be
    # mistaken for complete source cues and trimmed through retained tails.
    shared_interval_rows = shared_interval_tails = 0
    if config.level == 1:
        shared = merge_shared_interval_rows(
            simplified_events,visible_map,font_metrics,animated_sources, font_report=font_report)
        simplified_events = shared.events
        shared_interval_rows,shared_interval_tails = shared.rows_joined,shared.tails_retained
        visible_map.update(shared.visibility_updates)
    statistics.update({
        'backdrops_retained': backdrops_retained,
        'deduped': deduped,
        'lyric_merged': lyric_merged,
        'text_effect_sequences_frozen': text_effect_sequences_frozen,
        'cue_overlaps_trimmed': cue_overlaps_trimmed,
        'static_merged': static_merged,
        'shared_interval_rows': shared_interval_rows,
        'shared_interval_tails': shared_interval_tails,
        'dropped': dropped_drawings,
    })
    return simplified_events,statistics


def _summarize_text_processing(
    source: SubtitleDocument,
    prepared: PreparedSourceText,
    simplified_events: list[Event],
    vector_events: list[Event],
    statistics: dict[str,int],
) -> dict[str,int]:
    """Return text-engine counters independently of document serialization."""
    max_concurrent_in = source.peak
    if not source.events:
        return {key: 0 for key in ("original", "output", "max_concurrent_in", "max_concurrent_out",
                "deduped", "lyric_merged",
                "merged", "dropped", "overlap_removed", "cue_overlaps_trimmed", "vector_text_recovered", "full_copies_removed", "phase_merged",
                "text_copies_removed", "vector_copies_removed", "vector_glows_removed",
                "vector_frames_removed", "vector_output", "excess_vectors", "static_merged", "covered_vectors", "tiles_joined", "stacked_text_copies_flattened", "text_effect_sequences_frozen", "staggered_rows", "overlaid_letters", "covered_fragments", "fullwidth_merged", "progressive_rows", "masked_decorations", "backdrops_retained")}

    vector_source_indices = {v.source_index for v in vector_events}
    output_dialogues = sum((1 for e in simplified_events if e.kind == 'Dialogue'))
    return {
        'original': statistics['original'],
        'max_concurrent_in': max_concurrent_in,
        'max_concurrent_out': peak_concurrent_events(simplified_events),
        'backdrops_retained': statistics['backdrops_retained'],
        'vector_text_recovered': prepared.vector_captions,
        'static_merged': statistics['static_merged'],
        'covered_vectors': statistics['covered_vectors'],
        'tiles_joined': statistics['tiles_joined'],
        'stacked_text_copies_flattened': statistics['stacked_text_copies_flattened'],
        'masked_decorations': statistics['masked_decorations'],
        'text_effect_sequences_frozen': statistics['text_effect_sequences_frozen'],
        'staggered_rows': statistics['staggered_rows'],
        'fullwidth_merged': statistics['fullwidth_merged'],
        'progressive_rows': statistics['progressive_rows'],
        'overlaid_letters': statistics['overlaid_letters'],
        'covered_fragments': statistics['covered_fragments'],
        'phase_merged': statistics['phase_merged'],
        'output': output_dialogues,
        'deduped': statistics['deduped'],
        'lyric_merged': statistics['lyric_merged'],
        'shared_interval_rows': statistics['shared_interval_rows'],
        'shared_interval_tails': statistics['shared_interval_tails'],
        'overlap_removed': statistics['overlap_removed'],
        'cue_overlaps_trimmed': statistics['cue_overlaps_trimmed'],
        'full_copies_removed': statistics['full_copies_removed'],
        'merged': statistics['merged'],
        'text_copies_removed': statistics['text_copies_removed'],
        'vector_copies_removed': statistics['vector_copies_removed'],
        'vector_glows_removed': statistics['vector_glows_removed'],
        'vector_frames_removed': statistics['vector_frames_removed'],
        'vector_output': sum((e.source_index in vector_source_indices for e in simplified_events)),
        'excess_vectors': statistics['excess_vectors'],
        'dropped': statistics['dropped'],
    }


def _process_text_and_vectors(
    source: SubtitleDocument, config: SimplifyConfig, font_metrics: FontMetrics | None, *,
    font_report: FontProcessingReport | None=None, outline_matcher: FontOutlineMatcher | None=None,
) -> TextProcessingResult:
    """Run text reduction and return events/counters without writing a file."""
    animated_sources = {idx for idx,e in source.events.items()
                        if re.search(r"\\(?:t\s*\(|[kK](?:f|o)?\d|fad(?:e)?\s*\(|move\s*\()", e.text)}
    prepared = _prepare_source_text(source,animated_sources,config,font_metrics, font_report=font_report, outline_matcher=outline_matcher)
    frozen = _freeze_event_effects(source,prepared,config)
    events,vectors,statistics = _consolidate_text_events(
        source,prepared,frozen,animated_sources,config,font_metrics, font_report=font_report)
    events,statistics = _finalize_text_layout(
        source,frozen,events,vectors,statistics,animated_sources,config,font_metrics, font_report=font_report)
    events,phase_counts=_emit_caption_paint_timelines(events,prepared.paint_timelines,config)
    counts=_summarize_text_processing(source,prepared,events,vectors,statistics)
    counts.update(phase_counts)
    return TextProcessingResult(events,counts)


def _simplify_text_and_vectors(
    path: Path, output: Path, config: SimplifyConfig, *, font_metrics: FontMetrics | None=None,
    font_report: FontProcessingReport | None=None, outline_matcher: FontOutlineMatcher | None=None,
) -> dict[str, object]:
    """Compatibility entry point for text output and deprecated legacy mode."""
    if outline_matcher is None and font_metrics is not None:
        outline_matcher = FontOutlineMatcher(font_metrics)
    if path.resolve() == output.resolve():
        raise ValueError("Subtitle output must differ from its input.")
    source = _prepare_text_document(read_subtitle_document(path,config.encoding),path)
    result = _process_text_and_vectors(source,config,font_metrics, font_report=font_report, outline_matcher=outline_matcher)
    write_subtitle_document(output,source,result.events)
    return result.statistics


def _normalize_text_result(
    source: SubtitleDocument,
    result: TextProcessingResult,
) -> SubtitleDocument:
    """Make the ASS normalization boundary explicit, entirely in memory.

    Rendering and reparsing preserve the former intermediate-file semantics:
    static formatting is resolved, source indices become document line indices,
    and row/lyric flags and private proof metadata cannot cross the boundary.
    The original source document remains separate for backdrop reconstruction.
    Strip leading BOM characters as the former UTF-8 intermediate reader did.
    """
    return _resolve_document_state(parse_subtitle_document(
        render_subtitle_document(source,result.events).lstrip('\ufeff')))


def has_generated_marker(path: Path, encoding: str | None = None) -> bool:
    """Stream the preamble and Script Info, without an arbitrary line limit.

    Stop at the following section, so event text cannot masquerade as a
    header marker. Probe Unicode output encoding before a legacy input
    override: converted files are always UTF-8. Discovery tolerates decoding
    errors; conversion still decodes strictly and reports malformed inputs.
    """
    with path.open("rb") as stream:
        prefix = stream.read(4)
    if prefix.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        detected_encoding = "utf-32"
    elif prefix.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        detected_encoding = "utf-16"
    else:
        detected_encoding = "utf-8-sig"
    encodings = [detected_encoding]
    if encoding is not None and encoding != detected_encoding:
        encodings.append(encoding)
    for candidate in encodings:
        in_script_info = False
        try:
            with path.open("r", encoding=candidate, errors="replace") as stream:
                for line in stream:
                    stripped = line.lstrip("\ufeff").strip()
                    if stripped == GENERATED_MARKER:
                        return True
                    if stripped.startswith("[") and stripped.endswith("]"):
                        if stripped.casefold() == "[script info]":
                            in_script_info = True
                        elif in_script_info:
                            break
        except UnicodeError:
            continue
    return False


def validate_stats_path(report: Path, subtitles: Iterable[Path]) -> None:
    """Reject report aliases of discovered inputs and planned outputs."""
    resolved_report = report.resolve()
    for subtitle in subtitles:
        collision = resolved_report == subtitle.resolve()
        if not collision:
            try:
                collision = report.samefile(subtitle)
            except OSError:
                pass  # A new report/output has no inode to compare yet.
        if collision:
            raise ValueError(f"--stats-json would overwrite a subtitle: {subtitle}; "
                             "choose a separate report path.")


def iter_inputs(targets: Iterable[str], recursive: bool, suffix: str = ".simple",
                *, encoding: str | None = None,
                subtitle_paths: list[Path] | None = None) -> list[Path]:
    found: list[Path] = []
    for target in targets:
        p = Path(target)
        if p.is_file():
            # An explicit file is intentional, including a suffix-like name.
            if p.suffix.lower() in {".ass", ".ssa"}:
                if subtitle_paths is not None:
                    subtitle_paths.append(p)
                found.append(p)
        elif p.is_dir():
            pattern = "**/*" if recursive else "*"
            for f in p.glob(pattern):
                if not f.is_file() or f.suffix.lower() not in {".ass", ".ssa"}:
                    continue
                if subtitle_paths is not None:
                    subtitle_paths.append(f)
                # Preserve the established default-output exclusion for older
                # files without a marker. Custom suffixes can be source names.
                if suffix.lower() == ".simple" and f.stem.lower().endswith(".simple"):
                    continue
                try:
                    if has_generated_marker(f, encoding):
                        continue
                except (OSError, UnicodeError):
                    pass  # Let the per-file batch handler report unreadable inputs.
                found.append(f)
        else:
            print(f"Warning: not found: {p}")
    return sorted(set(found))


def extract_mkv_fonts(mkv: Path, destination: Path) -> None:
    """Read attached fonts into a private temporary directory; never edit MKV."""
    import json
    import shutil
    import subprocess
    merge, extract = shutil.which('mkvmerge'), shutil.which('mkvextract')
    if not merge or not extract:
        raise ValueError('--font-mkv requires mkvmerge and mkvextract in PATH')
    if not mkv.is_file():
        raise ValueError(f'Font source MKV not found: {mkv}')
    result = subprocess.run([merge,'-J',str(mkv.resolve())], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=120)
    if result.returncode not in (0,1):
        raise ValueError('Could not inspect MKV fonts: '+result.stderr.strip())
    try:
        attachments = json.loads(result.stdout).get('attachments',[])
    except json.JSONDecodeError as exc:
        raise ValueError(f'Could not parse mkvmerge JSON output: {exc}') from exc
    targets = []
    for attachment in attachments:
        suffix = Path(attachment.get('file_name','')).suffix.lower()
        mime = attachment.get('content_type','').lower()
        if suffix not in {'.ttf','.otf','.ttc','.otc'}:
            if mime not in {'application/x-truetype-font','application/vnd.ms-opentype',
                            'application/x-font-ttf','application/x-font-opentype',
                            'font/ttf','font/otf','font/collection','application/font-sfnt'}:
                continue
            suffix = '.ttc' if mime == 'font/collection' else '.ttf'
        identifier = int(attachment['id'])
        # Attachment filenames are untrusted. Use only a numeric ID locally.
        path = destination / f'font_{identifier}{suffix}'
        targets.append((identifier,path))
    if targets:
        result = subprocess.run([extract,str(mkv.resolve()),'attachments'] +
                                [f'{identifier}:{path}' for identifier,path in targets],
                                capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=120)
        if result.returncode not in (0,1) or any(not path.is_file() for _,path in targets):
            raise ValueError('Could not extract attached fonts: '+result.stderr.strip())
    print(f'Loaded {len(targets)} attached font files from {mkv.name}')


# Compatibility readers for reports written before the purpose-based names.
# Conversion and new JSON output use only the current keys.
LEGACY_STAT_KEYS = {
    'aggressive_copies': 'stacked_text_copies_flattened',
    'aggressive_sequences': 'text_effect_sequences_frozen',
    'prototype_vector_candidates': 'drawing_candidates',
    'prototype_strips_collapsed': 'drawing_strips_collapsed',
    'prototype_vector_duplicates': 'drawing_duplicates_removed',
    'prototype_fade_frames': 'drawing_fade_frames_removed',
    'prototype_unsupported_drawings': 'unsupported_drawings_excluded',
    'prototype_polygons_simplified': 'drawing_contours_simplified',
    'prototype_held_scaling_exits': 'drawing_scale_exits_frozen',
    'prototype_held_move_entrances': 'drawing_move_entrances_frozen',
    'prototype_edge_slivers_detached': 'drawing_edge_slivers_detached',
    'prototype_composite_backdrops': 'composite_backdrops_built',
    'prototype_scrolling_events_removed': 'scrolling_events_dropped',
    'prototype_scrolling_blocks_detected': 'scrolling_blocks_detected',
    'prototype_scrolling_blocks_removed': 'scrolling_blocks_dropped',
    'prototype_scrolling_blocks_retained': 'scrolling_blocks_retained',
    'prototype_scrolling_peak_after_reduction': 'scrolling_peak_after_reduction',
    'prototype_scrolling_concurrency_limit': 'scrolling_concurrency_limit',
    'prototype_masked_foregrounds_restored': 'masked_foregrounds_restored',
    'prototype_shadow_offsets_repaired': 'shadow_offsets_repaired',
    'prototype_vectors_capped': 'drawing_events_capped',
    'prototype_unmeasured_backdrops': 'unmeasured_backdrops_retained',
    'prototype_supports_retained': 'supporting_shapes_retained',
    'prototype_textures_removed': 'font_textures_removed',
    'prototype_fullscreen_backgrounds': 'fullscreen_backgrounds_retained',
    'prototype_adjacent_shapes': 'adjacent_shapes_retained',
}


def canonicalize_statistics(stats: dict) -> dict:
    """Read older report keys once; current keys win without double counting."""
    current = {k:v for k,v in stats.items() if k not in LEGACY_STAT_KEYS}
    for old,new in LEGACY_STAT_KEYS.items():
        if old in stats and new not in current:
            current[new] = stats[old]
    return current


def text_drop_warnings(stats):
    """Stable per-track warning records; ordinary effect merging is not a loss."""
    stats = canonicalize_statistics(stats)
    warnings=[]
    count=stats.get('scrolling_events_dropped',0)
    if count:
        limit=stats['scrolling_concurrency_limit']
        warnings.append({'code':'scrolling_text_dropped','severity':'warning','events':count,
            'concurrency_limit':limit,'blocks':stats['scrolling_blocks_dropped'],
            'peak_concurrent':stats['scrolling_peak_after_reduction'],
            'message':f'Dropped {count} events due to exceeding concurrent event limit {limit} for scrolling text blocks.'})
    removed=stats.get('color_phase_changes_removed',0)
    if removed:
        warnings.append({'code':'caption_color_changes_removed','severity':'warning',
            'captions':stats['color_phase_captions_limited'],'changes':removed,
            'minimum_hold':stats['color_phase_min_hold'],'change_interval':stats['color_phase_change_interval'],
            'rate_limited':stats['color_phase_rate_limited'],'hold_limited':stats['color_phase_hold_limited'],
            'message':f"Removed {removed} whole-caption color changes in {stats['color_phase_captions_limited']} captions "
                      f"by color phase limits (minimum hold {stats['color_phase_min_hold']:g}s; "
                      f"seconds per change {stats['color_phase_change_interval']:g}; "
                      f"rate: {stats['color_phase_rate_limited']}, hold: {stats['color_phase_hold_limited']})."})
    return warnings


def print_text_drop_warning(warning, context, stream=None):
    """Readable redirected logs, and a bold red banner on supported consoles."""
    import os
    stream = sys.stderr if stream is None else stream
    color = bool(getattr(stream, 'isatty', lambda: False)())
    if color and os.name == 'nt':
        # Enable virtual-terminal colours on Windows consoles, restoring the
        # previous mode afterward. A redirected stream gets plain text.
        import ctypes
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        mode = ctypes.c_ulong()
        try:
            handle = msvcrt.get_osfhandle(stream.fileno())
            color = bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and
                         kernel.SetConsoleMode(handle, mode.value | 4))
        except (AttributeError, OSError, ValueError):
            color = False
    prefix, suffix = ('\033[1;31m', '\033[0m') if color else ('', '')
    try:
        print(f'{prefix}{"="*78}\nWARNING: {warning["message"]}\n{context}\n{"="*78}{suffix}',
              file=stream)
    finally:
        if color and os.name == 'nt':
            kernel.SetConsoleMode(handle, mode.value)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Simplify ASS/SSA subtitles for limited renderers. standard simplification reduces effects and retains supporting backdrops; legacy simplification is deprecated and retained for compatibility."
    )
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("inputs", nargs="+", help="ASS/SSA file(s) or folder(s)")
    ap.add_argument("-r", "--recursive", action="store_true", help="scan folders recursively")
    ap.add_argument("--level", type=int, choices=(1, 2), default=1,
                    help="compatibility selector: 1 standard (default); 2 deprecated legacy static-visual pipeline")
    ap.add_argument("--suffix", default=".simple", help="output suffix before extension (default: .simple); scans skip marked outputs")
    ap.add_argument("--encoding", help="input encoding override for legacy or BOM-less files; "
                    "default: UTF-8 or BOM-marked UTF-16/UTF-32, decoded strictly")
    ap.add_argument("--max-blur", type=float, default=0.0,
                    help="retain/clamp blur up to this amount; default 0 removes blur")
    ap.add_argument("--short-duration", type=float, default=0.16,
                    help="max duration of a frame-animation piece in seconds (default 0.16)")
    ap.add_argument("--short-gap", type=float, default=0.08,
                    help="max gap between frame-animation pieces in seconds (default 0.08)")
    ap.add_argument("--max-drawing-chars", type=int, default=0,
                    help="optional vector path character budget; 0 retains all paths (default)")
    ap.add_argument("--max-vectors-per-cue", type=int, default=0,
                    help="optional vector count budget per cue; 0 retains all paths (default)")
    ap.add_argument("--scroll-concurrency-limit", type=int, default=32,
                    help="standard simplification scrolling-text fallback: drop a proved block only when its "
                    "remaining peak exceeds this count after ordinary reduction "
                    "(default 32; 0 disables text dropping)")
    ap.add_argument("--color-phase-min-hold",type=float,default=1.,
                    help="minimum whole-caption color phase in seconds (default 1; 0 disables hold limit)")
    ap.add_argument("--color-phase-change-interval",type=float,default=0.,
                    help="seconds of caption duration per permitted color change (default 0: unlimited)")
    ap.add_argument("--fonts-dir", action="append", default=[], metavar="FOLDER",
                    help="extra font folder (repeatable); exact fonts enable measured word spacing")
    ap.add_argument("--font-mkv", type=Path, metavar="FILE",
                    help="read font attachments from this MKV using MKVToolNix; source stays untouched")
    ap.add_argument("--no-font-spacing", action="store_true",
                    help="disable measured spacing; preserve uncertain fragment positions")
    ap.add_argument("--stats-json", type=Path, metavar="FILE",
                    help="also write per-input event counts as JSON for batch reports; "
                    "must be separate from input and output subtitles")
    args = ap.parse_args()

    if args.scroll_concurrency_limit < 0:
        ap.error("--scroll-concurrency-limit must be nonnegative")

    if any(not math.isfinite(v) or v<0 for v in (args.color_phase_min_hold,args.color_phase_change_interval)):
        ap.error("Color phase settings must be finite and nonnegative")
    if not args.suffix.strip() or any(c in args.suffix for c in '/\\:*?"<>|'):
        ap.error("--suffix must be nonempty and contain no filename separators or reserved characters")
    if args.encoding:
        try:
            codecs.lookup(args.encoding)
        except LookupError:
            ap.error(f"Unknown input encoding: {args.encoding}")
    if args.level == 2:
        print("WARNING: legacy simplification is deprecated; use standard simplification for current simplification.",
              file=sys.stderr)
    subtitle_paths: list[Path] = []
    inputs = iter_inputs(args.inputs, args.recursive, args.suffix,
                         encoding=args.encoding, subtitle_paths=subtitle_paths)
    if not inputs:
        ap.error("No .ass/.ssa files found")
    if args.stats_json:
        outputs = [src.with_name(src.stem + args.suffix + src.suffix) for src in inputs]
        try:
            validate_stats_path(args.stats_json, subtitle_paths + outputs)
        except (ValueError, OSError) as exc:
            ap.error(str(exc))

    config = SimplifyConfig(level=args.level, max_blur=args.max_blur,
        short_duration=args.short_duration, short_gap=args.short_gap,
        max_drawing_chars=args.max_drawing_chars,
        max_vectors_per_cue=args.max_vectors_per_cue, encoding=args.encoding,
        scroll_concurrency_limit=args.scroll_concurrency_limit,
        color_phase_min_hold=args.color_phase_min_hold,color_phase_change_interval=args.color_phase_change_interval)
    font_temp = None
    try:
        metric = None
        outline_matcher = None
        font_report = FontProcessingReport()
        if args.level == 1 and not args.no_font_spacing:
            folders = args.fonts_dir + [p.parent / "fonts" for p in inputs]
            if args.font_mkv:
                import tempfile
                font_temp = tempfile.TemporaryDirectory(prefix="ass-fonts-")
                extract_mkv_fonts(args.font_mkv, Path(font_temp.name))
                folders.insert(0, font_temp.name)
            fonts = FontMetrics(folders)
            metric = fonts
            outline_matcher = FontOutlineMatcher(fonts)
            if not fonts.capabilities.available:
                print("Font spacing unavailable. Enable with: python -m pip install Pillow fonttools")
            else:
                if not fonts.capabilities.raqm and not fonts.capabilities.harfbuzz:
                    print("RAQM unavailable: install the portable measurement backend with: "
                          "python -m pip install uharfbuzz (unmerged rows keep original timing)")
        total_in = total_out = 0
        records = []
        failed = 0
        input_paths = {src.resolve() for src in inputs}
        for src in inputs:
            dst = src.with_name(src.stem + args.suffix + src.suffix)
            track_started = time.perf_counter()
            try:
                if dst.resolve() in input_paths:
                    raise ValueError(f"Output is another input file: {dst}; choose a different --suffix.")
                stats = simplify_ass(src, dst, config, font_metrics=metric, font_report=font_report, outline_matcher=outline_matcher)
            except (ValueError,OSError) as exc:
                failed += 1
                records.append({"input":str(src.resolve()),"output":str(dst.resolve()),
                                "error":str(exc),
                                "processing_seconds": time.perf_counter() - track_started})
                print(f"Error: {src.name}: {exc}",file=sys.stderr)
                continue
            total_in += stats["original"]
            total_out += stats["output"]
            warnings = text_drop_warnings(stats)
            records.append({"input": str(src.resolve()),
                            "output": str(dst.resolve()), "stats": stats,
                            "warnings": warnings,
                            "processing_seconds": time.perf_counter() - track_started})
            for warning in warnings:
                print_text_drop_warning(warning, src.name)
            print(f"{src.name} -> {dst.name} (level {args.level})")
            print(f"  Processing time: {records[-1]['processing_seconds']:.3f} seconds")
            print(f"  Peak simultaneous events: {stats['max_concurrent_in']} -> "
                  f"{stats['max_concurrent_out']}")
            print(
                f"  dialogue events: {stats['original']} -> {stats['output']} "
                f"(duplicate layers removed: {stats['deduped']}, "
                f"lyric fragments merged: {stats['lyric_merged']}, "
                f"shared-interval rows: {stats.get('shared_interval_rows',0)}, "
                f"glyph phases merged: {stats['phase_merged']}, "
                f"overlapping effects removed: {stats['overlap_removed']}, "
                f"cue overlaps trimmed: {stats['cue_overlaps_trimmed']}, "
                f"full lyric copies removed: {stats['full_copies_removed']}, "
                f"frame pieces merged: {stats['merged']}, "
                f"identical timed copies merged: {stats['static_merged']}, "
                f"duplicate sign text: {stats['text_copies_removed']}, "
                f"masked texture copies removed: {stats['masked_decorations']}, "
                f"identical text strips joined: {stats['tiles_joined']}, "
                f"stacked text copies flattened: {stats['stacked_text_copies_flattened']}, "
                f"text effect sequences frozen: {stats['text_effect_sequences_frozen']}, "
                f"covered fragment effects removed: {stats['covered_fragments']}, "
                f"vector copies: {stats['vector_copies_removed']}, "
                f"covered contours: {stats['vector_glows_removed']}, "
                f"fully covered drawings: {stats['covered_vectors']}, "
                f"drawing animation frames: {stats['vector_frames_removed']}, "
                f"vectors retained: {stats['vector_output']}, "
                f"caption backdrops retained: {stats['backdrops_retained']}, "
                f"vector captions recovered: {stats['vector_text_recovered']}, "
                f"excess vector details removed: {stats['excess_vectors']}, "
                f"drawings/effects dropped before reconstruction: {stats['dropped']})"
            )
    
        if metric is not None and metric.available:
            print(f"Rows joined using font measurements: {font_report.rows_joined}")
            if font_report.missing_families:
                print("Exact fonts unavailable (kept positions): " + ", ".join(sorted(font_report.missing_families)))
        if len(inputs) > 1:
            print(f"Total dialogue events: {total_in} -> {total_out}")
        if failed:
            print(f"Failed files: {failed}/{len(inputs)}",file=sys.stderr)
        if args.stats_json:
            import json
            args.stats_json.parent.mkdir(parents=True, exist_ok=True)
            args.stats_json.write_text(json.dumps({"level": args.level,
                                                   "tracks": records},
                                                  ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        return 1 if failed else 0
    except (ValueError,OSError) as exc:
        ap.error(str(exc))
    finally:
        if font_temp is not None:
            font_temp.cleanup()


# Caption backdrops, vector simplification and bounded scrolling fallback.
# Geometry and font-based decisions are local to this pass; no persistent
# foreground/background classification is added to Event or font resources.

def merge_tiled_clips(rectangles, unit):
    """Accept a gapless, non-overlapping strip partition of one rectangle.

    Preserve the union clip. Removing it would expose unseen parts of paths.
    General tiled artwork and overlapping clips are not approximated here.
    """
    if not rectangles:
        return None
    eps = 1e-5 * unit
    for axis in (0, 1):
        other = 1-axis
        reference = rectangles[0]
        if any(abs(r[other]-reference[other]) > eps or
               abs(r[other+2]-reference[other+2]) > eps for r in rectangles):
            continue
        ordered = sorted(rectangles, key=lambda r: r[axis])
        # Tiny overlaps from decimal rounding are harmless for the union;
        # actual holes and substantial overlapping layers stay unsupported.
        if any(b[axis]-a[axis+2] > eps or a[axis+2]-b[axis] >
               min(.25*unit, .05*min(a[axis+2]-a[axis], b[axis+2]-b[axis]))+eps
               for a, b in zip(ordered, ordered[1:])):
            continue
        box = list(reference)
        box[axis], box[axis+2] = ordered[0][axis], ordered[-1][axis+2]
        return tuple(box)
    return None


def drawing_paint(event):
    """Select visible paint; offset shadows/strokes need more geometry work."""
    st = event.state
    # A nearly coincident shadow can contain the actual background fill.
    if (st.get('4a', 0) < 254 and
            0 < max(abs(st.get(k, st.get('shad', 0))) for k in ('xshad', 'yshad'))
                <= .05 * event.unit and st.get('4a', 0) < st.get('1a', 0)):
        return st.get('4c', '000000'), st.get('4a', 0)
    if st.get('1a', 0) < 254:
        return st.get('1c', 'FFFFFF'), st.get('1a', 0)
    return None


def compose_drawing_paint(events):
    """Compose coextensive fills in their original same-layer source order."""
    opacity, premult = 0.0, [0.0, 0.0, 0.0]
    for event in sorted(events, key=lambda e: e.source_index):
        paint = drawing_paint(event)
        if paint is None:
            continue
        color, alpha = paint
        ink = (255-alpha)/255
        premult = [old*(1-ink)+((int(color, 16) >> shift) & 255)*ink
                   for old, shift in zip(premult, (16, 8, 0))]
        opacity = opacity*(1-ink)+ink
    if opacity <= 1/255:
        return None
    color = ''.join(f'{round(v/opacity):02X}' for v in premult)
    return color, round(255*(1-opacity))


def recover_held_drawing_scale(source, candidate, transforms, paint_tags):
    """Validate a short scale entrance, shrinking exit, or stable-pose pair."""
    if not transforms:
        return True, False
    if len(transforms) > 2:
        return False, False
    parsed, targets = [], []
    target = source.state.copy()
    target_continuation = source.continuation
    for value in transforms:
        item = parse_effect_transform(value, source.duration, paint_tags | {'fscx', 'fscy'})
        if item is None:
            return False, False
        for key, argument in item[2]:
            if key in ('fscx', 'fscy'):
                # libass accepts a trailing comma on these numeric targets.
                # Require a complete finite number rather than letting the
                # strict production parser silently skip a malformed target.
                if not re.fullmatch(r'\s*'+NUMBER+r'\s*,?\s*', argument):
                    return False, False
                argument = argument.strip().removesuffix(',').strip()
                if not math.isfinite(float(argument)):
                    return False, False
            target_continuation = apply_override(target,key,argument,source.styles,source.defaults,target_continuation)
        parsed.append(item)
        targets.append(target.copy())
    def matches(pose):
        return all(pose.get(k, 100) > 0 and
                   abs(pose.get(k, 100)-candidate.state.get(k, 100)) < .001
                   for k in ('fscx', 'fscy'))
    def shrinks(before, after):
        return (all(0 < after.get(k, 100) <= before.get(k, 100)
                    for k in ('fscx', 'fscy')) and
                any(after.get(k, 100) < before.get(k, 100) for k in ('fscx', 'fscy')))
    if len(parsed) == 1:
        begin, end, _ = parsed[0]
        entrance = begin == 0 and end <= 200*source.duration and matches(targets[0])
        exit_pose = (800*source.duration <= begin < 1000*source.duration and
                     end >= 1000*source.duration-50 and
                     matches(source.state) and shrinks(source.state, targets[0]))
        return entrance or exit_pose, exit_pose
    first, last = parsed
    exit_pose = (first[0] == 0 and first[1] <= 200*source.duration and
                 last[0]-first[1] >= 800*source.duration and
                 last[1] >= 1000*source.duration-50 and
                 matches(targets[0]) and shrinks(targets[0], targets[1]))
    return exit_pose, exit_pose


def _normalize_supporting_drawing_candidate(source: Event, context: SupportingDrawingContext) -> SupportingDrawingCandidate | None:
    """Freeze drawing paint, normalize alignment/stroke, detach edge slivers and simplify contours."""
    if (source.kind != 'Dialogue' or source.duration <= 0 or
            not re.search(r'\\p[1-9]\d*\b', source.text, re.I)):
        return None
    text, visible, chars = simplify_visual_text(
        source.text, 0, source.duration, source.defaults, source.styles, 2)
    if not chars:
        return None
    candidate = normalize_drawing_alignment(flatten_rectangular_border(
        replace_event(source, text=text, effect=''), scaled_borders=context.scaled_borders))
    candidate, detached = detach_drawing_edge_slivers(candidate)
    context.counts['drawing_edge_slivers_detached'] += detached
    original_points = None
    if drawing_polygon(candidate) is None:
        reduction = simplify_drawing_contour(candidate)
        if reduction is not None:
            raw, original_points = reduction
            candidate = replace_event(candidate, text=OVERRIDE_RE.match(candidate.text).group()+raw)
            context.counts['drawing_contours_simplified'] += 1
    return SupportingDrawingCandidate(candidate,text,visible,original_points)


def _profile_supporting_drawing_motion(source: Event, candidate: Event, text: str, paint_tags: set) -> tuple:
    """Retain the original held-scale proof and only a fully completed short entrance move."""
    transforms = [(k, v) for block in OVERRIDE_RE.findall(source.text)
                  for k, v in tokenize_override(block) if k == 't']
    geometry_transforms = [value for _, value in transforms if
                           any(k not in paint_tags for k, v in
                               tokenize_override(value[1:-1]))]
    held_scale, held_exit = recover_held_drawing_scale(
        source, candidate, geometry_transforms, paint_tags)
    animated_geometry = not held_scale
    moves = [v for block in OVERRIDE_RE.findall(source.text)
             for k, v in tokenize_override(block) if k == 'move']
    held_move = False
    if len(moves) == 1:
        motion = parse_effect_move(moves[0], source.duration)
        held_move = (motion is not None and len(motion) == 6 and
                     motion[5] <= 200*source.duration and
                     get_pos(text) is not None and
                     all(abs(a-b) < .001 for a, b in zip(get_pos(text), motion[2:4])))
    return animated_geometry,moves,held_exit,held_move


def _admit_supporting_drawing_candidate(source: Event, normalized: SupportingDrawingCandidate, context: SupportingDrawingContext) -> bool:
    """Reject mixed text, unsupported motion and static geometry before counting held exits/entrances."""
    candidate,visible = normalized.event,normalized.visible
    animated_geometry,moves,held_exit,held_move = _profile_supporting_drawing_motion(
        source,candidate,normalized.frozen_text,context.paint_tags)
    if (visible or inline_layout_key(source) or drawing_polygon(candidate) is None or
            (moves and not held_move) or animated_geometry or
            'iclip' in candidate.state or
            any(candidate.state.get(k, 0) for k in ('frx', 'fax', 'fay', 'pbo')) or
            candidate.state.get('fry', 0) % 360 not in (0, 180) or
            get_pos(candidate.text) is None):
        context.counts['unsupported_drawings_excluded'] += 1
        return False
    context.counts['drawing_scale_exits_frozen'] += held_exit
    context.counts['drawing_move_entrances_frozen'] += held_move
    return True


def _index_supporting_drawing_candidates(sources: Iterable[Event], context: SupportingDrawingContext) -> dict:
    """Group admitted candidates by original cue, drawing geometry, nonpaint state and contour evidence."""
    groups = {}
    for source in sources:
        normalized = _normalize_supporting_drawing_candidate(source,context)
        if normalized is None or not _admit_supporting_drawing_candidate(source,normalized,context):
            continue
        candidate,original_points = normalized.event,normalized.original_points
        raw_key = (source.start, source.end, source.layer, source.style, source.name,
                   source.margin_l, source.margin_r, source.margin_v,
                   geometry_key(candidate.text), state_key(candidate, context.paint_tags | {'clip'}),
                   tuple(original_points) if original_points is not None else None)
        if original_points is not None:
            context.original_contours[candidate.source_index] = tuple(original_points)
        groups.setdefault(raw_key, []).append(candidate)
    return groups


def _prove_supporting_drawing_strip_coverage(group: list[Event], context: SupportingDrawingContext) -> SupportingDrawingCoverage | None:
    """Intersect clips with actual rectangular fill and require a complete nondegenerate tiled union."""
    first = group[0]
    clipped = ['clip' in e.state for e in group]
    rects = [rectangle_clip(e) for e in group]
    # Clip coordinates outside a rectangle's actual fill do not create
    # gaps. Intersect first; gradient generators often round those unused
    # top/bottom limits differently in their final strip.
    path = drawing_polygon(first)
    if (path and len({x for x, y in path}) == 2 and
            len({y for x, y in path}) == 2 and coverage_geometry(first) is not None):
        points = coverage_geometry(first)[0]
        xs, ys = zip(*points)
        bounds = min(xs), min(ys), max(xs), max(ys)
        rects = [None if r is None else (max(r[0], bounds[0]), max(r[1], bounds[1]),
                                       min(r[2], bounds[2]), min(r[3], bounds[3]))
                 for r in rects]
    if any(clipped):
        if not all(clipped) or any(r is None or r[0] >= r[2] or r[1] >= r[3] for r in rects):
            context.counts['unsupported_drawings_excluded'] += len(group)
            return None
        clip_groups = {}
        for event, rect in zip(group, rects):
            clip_groups.setdefault(rect, []).append(event)
        rects = list(clip_groups)
        union = merge_tiled_clips(rects, first.unit)
        if union is None:
            context.counts['unsupported_drawings_excluded'] += len(group)
            return None
    else:
        union = None
        clip_groups = {}
    return SupportingDrawingCoverage(union,clip_groups,rects)


def _compose_supporting_drawing_group_paint(group: list[Event], coverage: SupportingDrawingCoverage) -> tuple[str,int] | None:
    """Compose coincident copies, then area-average distinct strips including transparent coverage."""
    union,clip_groups,rects = coverage.union,coverage.clip_groups,coverage.rectangles
    if union:
        paints = [compose_drawing_paint(clip_group) for clip_group in clip_groups.values()]
        weights = [(r[2]-r[0])*(r[3]-r[1]) for r in rects]
        active = [(paint, weight) for paint, weight in zip(paints, weights) if paint]
        # Average the composed paint of each distinct strip, including
        # transparent strips, rather than counting coincident copies as
        # overlapping partitions of the gradient.
        area = sum(weights)
        ink = sum(weight * (255-alpha) for (color, alpha), weight in active)
        alpha = round(255-ink/area)
        if alpha >= 254:
            return None
        channels = [round(sum(weight*(255-a)*((int(c, 16) >> shift) & 255)
                              for (c, a), weight in active)/ink)
                    for shift in (16, 8, 0)]
    else:
        paint = compose_drawing_paint(group)
        if paint is None:
            return None
        color, alpha = paint
        channels = [(int(color, 16) >> shift) & 255 for shift in (16, 8, 0)]
    color = ''.join(f'{v:02X}' for v in channels)
    return color,alpha


def _render_supporting_drawing_group(group: list[Event], union: tuple | None, color: str, alpha: int) -> Event:
    """Render composed fill at the normalized static pose with the original minimum source ID."""
    first = group[0]
    # Preserve the static pose and path after exact alignment normalization
    # and the simple same-colour rectangular-stroke expansion above.
    st = dict(first.state)
    st.update({'1c': color, '1a': alpha, '2a': alpha, '3a': 255, '4a': 255,
               'bord': 0, 'xbord': 0, 'ybord': 0, 'shad': 0,
               'xshad': 0, 'yshad': 0, 'blur': 0, 'be': 0})
    if union:
        st['clip'] = '('+','.join(f'{x:g}' for x in union)+')'
    else:
        st.pop('clip', None)
    keys = ('an', 'pos', 'org', 'p', 'fscx', 'fscy', 'frz', 'fry',
            'bord', 'shad', 'xbord', 'ybord', 'xshad', 'yshad',
            '1c', '1a', '2a', '3a', '4a', 'clip')
    tags = ''.join(render_tag(k, st[k]) for k in keys if k in st)
    event = replace_event(first, text='{'+tags+'}'+OVERRIDE_RE.sub('', first.text),
                          source_index=min(e.source_index for e in group))
    return event


def _reduce_supporting_drawing_groups(groups: dict, context: SupportingDrawingContext) -> list[Event]:
    """Reduce only coverage-proven visible groups and retain strip/duplicate count semantics."""
    output = []
    for group in groups.values():
        coverage = _prove_supporting_drawing_strip_coverage(group,context)
        if coverage is None:
            continue
        paint = _compose_supporting_drawing_group_paint(group,coverage)
        if paint is None:
            continue
        color,alpha = paint
        event = _render_supporting_drawing_group(group,coverage.union,color,alpha)
        output.append(event)
        context.counts['drawing_strips_collapsed' if coverage.union else 'drawing_duplicates_removed'] += len(group)-1
    return output


def _reduce_supporting_drawing_sequences(output: list[Event], context: SupportingDrawingContext) -> list[Event]:
    """Use existing layer/sequence reducers only within identical pose and original-contour families."""
    # Existing helper removes exact opaque layers. Restrict sequence merging
    # to identical poses: its general path can otherwise freeze moving signs.
    output, removed = reduce_vector_layers(output)
    context.counts['drawing_duplicates_removed'] += removed
    poses = {}
    for e in output:
        poses.setdefault((e.style, e.name, e.layer, geometry_key(e.text),
                          state_key(e, {'1a', '2a', '3a', '4a'}),
                          context.original_contours.get(e.source_index)), []).append(e)
    output = []
    for family in poses.values():
        family, removed = freeze_vector_sequences(family)
        output.extend(family)
        context.counts['drawing_fade_frames_removed'] += removed
    return output


def _finalize_supporting_drawings(output: list[Event], context: SupportingDrawingContext) -> tuple[list[Event],dict]:
    """Attach temporary original-contour evidence and return source-ordered candidates/counters."""
    context.counts['drawing_candidates'] = len(output)
    for e in output:
        if e.source_index in context.original_contours:
            # Retain source contours for subsequent caption-support coverage
            # checks. This evidence is separate from formatting and not serialized.
            e.evidence = EventEvidence(context.original_contours[e.source_index])
    return sorted(output, key=lambda e: e.source_index), context.counts


def reduce_supporting_drawings(sources, *, scaled_borders=True):
    """Reduce proved static primitives and clipped gradients, not moving UI."""
    counts = {'drawing_candidates': 0, 'drawing_strips_collapsed': 0,
              'drawing_duplicates_removed': 0, 'drawing_fade_frames_removed': 0,
              'unsupported_drawings_excluded': 0, 'drawing_contours_simplified': 0,
              'drawing_scale_exits_frozen': 0, 'drawing_move_entrances_frozen': 0,
              'drawing_edge_slivers_detached': 0}
    paint_tags = {'c', '1c', '2c', '3c', '4c', 'alpha', '1a', '2a', '3a', '4a',
                  'bord', 'xbord', 'ybord', 'shad', 'xshad', 'yshad', 'blur', 'be'}
    context = SupportingDrawingContext(scaled_borders,counts,paint_tags,{})
    groups = _index_supporting_drawing_candidates(sources,context)
    output = _reduce_supporting_drawing_groups(groups,context)
    output = _reduce_supporting_drawing_sequences(output,context)
    return _finalize_supporting_drawings(output,context)


def reconstruct_composite_backdrops(sources, captions, metric):
    """Approximate static shadow-painted erasure patches around literal text.

    This is a bounded reconstruction, not a claim that disjoint source masks
    covered every glyph. Require several matching opaque, similarly coloured
    patches intersecting a measured caption, and keep their combined bounds.
    Separate contours are measured separately so a distant separator cannot
    enlarge a title panel merely because both share one drawing event.
    """
    groups = {}
    for source in sources:
        st = source.state
        if (source.kind != 'Dialogue' or not st.get('p', 0) or
                st.get('an') != 7 or st.get('1a', 0) < 254 or
                st.get('3a', 0) < 254 or st.get('4a', 0) != 0 or
                st.get('borderstyle', 1) != 1 or get_pos(source.text) is None or
                not source.layer.lstrip('-').isdigit() or
                any(k in st for k in ('clip', 'iclip')) or
                any(st.get(k, 0) for k in ('frz', 'frx', 'fry', 'fax', 'fay', 'pbo')) or
                re.search(r'\\(?:t|move|fad|fade)\s*\(', source.text, re.I) or
                not 0 < max(abs(st.get(k, st.get('shad', 0)))
                            for k in ('xshad', 'yshad')) <= .05*source.unit or
                not 0 <= st.get('blur', 0) <= 8*source.unit):
            continue
        text, visible, chars = simplify_visual_text(source.text, 0, source.duration,
                                                   source.defaults, source.styles, 2)
        if visible or not chars or inline_layout_key(source):
            continue
        raw = OVERRIDE_RE.sub('', text).strip()
        # Reject unknown commands before splitting move/line/cubic contours.
        if re.sub(NUMBER+r'|[mlb\s]', '', raw, flags=re.I):
            continue
        key = (source.start, source.end, source.style, source.name, source.layer,
               get_pos(source.text), st.get('p'), st.get('fscx'), st.get('fscy'))
        for contour in re.split(r'(?=m\s)', raw, flags=re.I):
            if not re.search(r'\bb\s', contour, re.I):
                continue
            fragment = replace_event(source, text=OVERRIDE_RE.match(text).group()+contour)
            info = coverage_geometry(fragment)
            if info is None:
                continue
            pad = 2*st.get('blur', 0)
            x0, y0, x1, y1 = info[1]
            bounds = (x0-pad, y0-pad, x1+pad, y1+pad)
            color = str(st.get('4c', ''))
            if re.fullmatch(r'[0-9A-Fa-f]{6}', color):
                groups.setdefault(key, []).append((source, bounds, color))
    rebuilt, used = [], set()
    for caption in captions:
        if (caption.kind != 'Dialogue' or caption.state.get('p', 0) or caption.lyric or
                not caption.layer.lstrip('-').isdigit() or
                len(OVERRIDE_RE.sub('', caption.text).strip()) < 2 or
                re.search(r'\\[Nn]', OVERRIDE_RE.sub('', caption.text))):
            continue
        box = caption_bounds(caption, metric)
        if box is None:
            continue
        for key, fragments in groups.items():
            first = fragments[0][0]
            if (key in used or first.style != caption.style or first.name != caption.name or
                    int(first.layer) >= int(caption.layer) or
                    min(first.end_s, caption.end_s) <= max(first.start_s, caption.start_s)):
                continue
            nearby = []
            for e, b, c in fragments:
                # Blur clearance can approach a neighbouring separator, but
                # that alone does not make its contour a title patch.
                pad = 2*e.state.get('blur', 0)
                if (min(b[2]-pad, box[2]) > max(b[0]+pad, box[0]) and
                        min(b[3]-pad, box[3]) > max(b[1]+pad, box[1])):
                    nearby.append((e, b, c))
            if len({e.source_index for e, b, c in nearby}) < 3:
                continue
            bounds = (min(b[0] for e, b, c in nearby), min(b[1] for e, b, c in nearby),
                      max(b[2] for e, b, c in nearby), max(b[3] for e, b, c in nearby))
            x0, y0, x1, y1 = bounds
            if (not (x0 < box[0] < box[2] < x1 and y0 < box[1] < box[3] < y1) or
                    x1-x0 > 2*(box[2]-box[0]) or y1-y0 > 2*(box[3]-box[1])):
                continue
            colors = [tuple(int(c[i:i+2], 16) for i in (0, 2, 4)) for e, b, c in nearby]
            if any(max(c[i] for c in colors)-min(c[i] for c in colors) > 32 for i in range(3)):
                continue
            weights = [(b[2]-b[0])*(b[3]-b[1]) for e, b, c in nearby]
            color = ''.join(f'{round(sum(w*c[i] for w, c in zip(weights, colors))/sum(weights)):02X}'
                            for i in range(3))
            tags = (r'\an7\pos(0,0)\p1\fscx100\fscy100\bord0\shad0'
                    r'\xbord0\ybord0\xshad0\yshad0'+render_tag('1c', color)+
                    r'\1a&H00&\2a&H00&\3a&HFF&\4a&HFF&')
            raw = f'm {x0:g} {y0:g} l {x1:g} {y0:g} {x1:g} {y1:g} {x0:g} {y1:g}'
            event = replace_event(first, text='{'+tags+'}'+raw, effect='')
            rebuilt.append(event)
            used.add(key)
    return rebuilt


def is_font_texture(event, metric):
    """Prove a multiline stamp texture by its exact glyph contour structure."""
    if metric is None or not metric.available or event.state.get('p', 0):
        return False
    text = OVERRIDE_RE.sub('', event.text)
    lines = re.split(r'\\[Nn]', text)
    chars = [c for line in lines for c in line if not c.isspace()]
    if len(lines) < 3 or len(chars) < 24:
        return False
    face = metric.matching_face(str(event.state.get('fn', '')),
                                event.state.get('b', 0), bool(event.state.get('i', 0)))
    if face is None or any(ord(c) not in face.cmap for c in chars):
        return False
    # A font name or nonsensical-looking string alone authorizes nothing.
    return all(metric.fragmented_glyph(face, c) is True for c in set(chars))


def is_fullscreen_background(event):
    """Prove that a static fill covers the viewport, including its clip."""
    info = coverage_geometry(event)
    canvas = event.measurement.canvas
    if info is None or canvas is None:
        return False
    width, height = canvas
    if width <= 0 or height <= 0:
        return False
    eps = 1e-4*event.unit
    viewport = (eps, eps, width-eps, height-eps)
    clip = rectangle_clip(event)
    if 'clip' in event.state and (clip is None or not all((
            clip[0] <= viewport[0], clip[1] <= viewport[1],
            clip[2] >= viewport[2], clip[3] >= viewport[3]))):
        return False
    return polygon_covers_box(info[0], viewport)


def caption_clip_outline(event):
    """Return one static, straight-sided scene-coordinate clip contour.

    A shared authored contour can identify a panel without approximating the
    perspective of its text. Keep the clip on that text; do not expand its ink.
    """
    if (event.state.get('p', 0) or 'iclip' in event.state or
            inline_layout_key(event) or
            re.search(r'\\(?:t|move|fad|fade)\s*\(', event.text, re.I)):
        return None
    mask = re.fullmatch(r'\(\s*(?:(\d+)\s*,\s*)?(m\s+.*?)\s*\)',
                        str(event.state.get('clip', '')), re.I)
    if mask is None or not 1 <= int(mask[1] or 1) <= 16:
        return None
    points = drawing_polygon(replace_event(event, text='{\\p1}'+mask[2]))
    scale = 2**(int(mask[1] or 1)-1)
    return tuple((x/scale, y/scale) for x, y in points) if points else None


def repair_caption_shadow_offsets(sources, captions):
    """Recover a held shadow offset hidden by an extra numeric-tag comma.

    libass accepts a numeric prefix before the comma; strict float parsing
    skips it. Repair only these shadow tags, on the same faint-primary
    caption with an opaque shadow and no outline. Other text paint is retained.
    """
    def key(e):
        return (e.start, e.end, e.style, e.name, placement_key(e)[0],
                get_pos(e.text), text_layout_key(e), OVERRIDE_RE.sub('', e.text).strip())
    corrected = {}
    for source in sources:
        if (source.kind != 'Dialogue' or source.state.get('p', 0) or
                inline_layout_key(source) or source.state.get('1a', 0) < 254 or
                source.state.get('4a', 0) != 0 or
                source.state.get('borderstyle', 1) != 1 or
                max(abs(source.state.get(k, source.state.get('bord', 0)))
                    for k in ('xbord', 'ybord')) != 0):
            continue
        clean = re.sub(r'(\\(?:xshad|yshad|shad)'+NUMBER+r'),(?=\\)', r'\1', source.text)
        if clean == source.text:
            continue
        text, _, _ = simplify_visual_text(clean, 0, source.duration,
                                         source.defaults, source.styles, 1)
        repaired = replace_event(source, text=text)
        corrected.setdefault(key(repaired), []).append(repaired)
    output, count = [], 0
    for e in captions:
        choices = corrected.get(key(e), [])
        offsets = {(c.state.get('xshad', c.state.get('shad', 0)),
                    c.state.get('yshad', c.state.get('shad', 0))) for c in choices}
        if (e.kind == 'Dialogue' and not e.lyric and len(offsets) == 1 and
                e.state.get('1a', 0) >= 254 and e.state.get('4a', 0) == 0 and
                not inline_layout_key(e)):
            dx, dy = next(iter(offsets))
            if (dx, dy) != (e.state.get('xshad', e.state.get('shad', 0)),
                            e.state.get('yshad', e.state.get('shad', 0))):
                text = OVERRIDE_RE.sub(lambda m: '{'+re.sub(
                    r'\\(?:xshad|yshad|shad)[^\\}]*', '', m.group()[1:-1])+'}', e.text)
                text = '{'+render_tag('xshad', dx)+render_tag('yshad', dy)+'}'+text
                e = replace_event(e, text=text)
                count += 1
        output.append(e)
    return output, count


def restore_masked_caption_foregrounds(sources, captions):
    """Restore a solid clipped caption when text reduction kept only its faint clone.

    Require identical literal text, static layout, anchor, lifetime, actor and
    fill colour. An ambiguous set of solid masks authorizes no replacement.
    This source-backed correction follows text reduction.
    """
    def key(e):
        return (e.start, e.end, e.style, e.name, placement_key(e)[0],
                get_pos(e.text), text_layout_key(e),
                OVERRIDE_RE.sub('', e.text).strip(), e.state.get('1c'))
    solids = {}
    for source in sources:
        if (source.kind != 'Dialogue' or source.state.get('1a', 0) != 0 or
                caption_clip_outline(source) is None):
            continue
        text, _, _ = simplify_visual_text(source.text, 0, source.duration,
                                         source.defaults, source.styles, 1)
        solid = replace_event(source, text=text, effect='')
        solids.setdefault(key(solid), []).append(solid)
    restored, count = [], 0
    for caption in captions:
        choices = solids.get(key(caption), [])
        signatures = {(e.text, e.layer) for e in choices}
        if (caption.kind == 'Dialogue' and not caption.lyric and
                not caption.state.get('p', 0) and
                not inline_layout_key(caption) and
                'clip' not in caption.state and 'iclip' not in caption.state and
                0 < caption.state.get('1a', 0) < 255 and len(signatures) == 1):
            solid = choices[0]
            # Preserve the output index for insertion, but recover the source
            # layer as well as its paint, mask and exact static text pose.
            caption = replace_event(caption, text=solid.text, layer=solid.layer)
            count += 1
        restored.append(caption)
    return restored, count


def drawing_matches_caption_outline(panel, caption, points=None):
    """Match a text mask to its panel while rejecting a displaced reuse."""
    mask = caption_clip_outline(caption)
    raw_points = drawing_polygon(panel)
    if mask is None or raw_points is None or 'clip' in panel.state:
        return False
    scale = 2**(panel.state.get('p', 1)-1)
    outline = tuple((x/scale, y/scale) for x, y in raw_points)
    anchor = get_pos(caption.text)
    if points is None:
        info = coverage_geometry(panel)
        points = info[0] if info is not None else None
    return (mask == outline and points is not None and anchor is not None and
            polygon_covers_box(list(mask), (*anchor, *anchor)) and
            polygon_covers_box(points, (*anchor, *anchor)))


def caption_panel_contains(panel: Event, points: list | None, caption: Event, box: tuple | None) -> bool:
    """Prove measured ink inside current and original fill, respecting panel clips.

    This is spatial/family evidence, not a timing, ordering or opacity proof.
    Those obligations differ between support admission and final promotion.
    """
    original = panel.evidence.original_contour_points
    clip = rectangle_clip(panel)
    return (box is not None and points is not None and
            panel.style == caption.style and panel.name == caption.name and
            polygon_covers_box(points, box) and
            polygon_covers_box(list(original if original is not None else points), box) and
            (clip is None or clip[0] < box[0] and clip[1] < box[1] and
             clip[2] > box[2] and clip[3] > box[3]))


def _caption_panel_ownership(kept: list[Event], associated: dict,
                             metric: FontMetrics | None) -> list[CaptionPanelOwnership]:
    """Carry enclosing ownership; adjacency/fullscreen associations are not owners."""
    ownership = []
    boxes = {}
    for panel in kept:
        geometry = coverage_geometry(panel)
        if (geometry is None or not geometry[2] or is_fullscreen_background(panel) or
                static_object_key(panel, panel.styles) is None):
            continue
        for caption in associated.get(panel.source_index, ()):
            if (not any(c.isalnum() for c in OVERRIDE_RE.sub('', caption.text)) or
                    not caption.layer.lstrip('-').isdigit() or int(panel.layer) > int(caption.layer)):
                continue
            if id(caption) not in boxes:
                boxes[id(caption)] = caption_bounds(caption, metric)
            if caption_panel_contains(panel, geometry[0], caption, boxes[id(caption)]):
                ownership.append(CaptionPanelOwnership(panel, caption))
    return ownership


def _rectangle_polygon(points: list) -> bool:
    xs, ys = {x for x,y in points}, {y for x,y in points}
    return len(xs) == len(ys) == 2 and set(points) == {(x,y) for x in xs for y in ys}


def _same_caption_panel(panel: Event, points: list, owner: Event, owner_points: list) -> bool:
    """Match a panel footprint, allowing its existing stroke/rounding allowance."""
    if panel is owner or points == owner_points:
        return True
    if not _rectangle_polygon(points) or not _rectangle_polygon(owner_points):
        return False
    tolerance = max(2., 2*min(panel.unit, owner.unit))
    bounds = lambda ps: (min(x for x,y in ps), min(y for x,y in ps),
                         max(x for x,y in ps), max(y for x,y in ps))
    return all(abs(a-b) <= tolerance for a,b in zip(bounds(points), bounds(owner_points)))


def _covered_caption_panels(panels: list) -> set[tuple]:
    """Prove hidden rectangular fills separately from caption ownership/layering."""
    hidden = set()
    for lower, low_points in panels:
        if not _rectangle_polygon(low_points) or any(lower.state.get(k, lower.state.get(base, 0)) != 0
                for k,base in (('xbord','bord'),('ybord','bord'),('xshad','shad'),('yshad','shad'))):
            continue
        for upper, up_points in panels:
            if (int(upper.layer) <= int(lower.layer) or upper.style != lower.style or upper.name != lower.name or
                    upper.start_s > lower.start_s or upper.end_s < lower.end_s or not _rectangle_polygon(up_points)):
                continue
            if (min(x for x,y in up_points) <= min(x for x,y in low_points) and
                    max(x for x,y in up_points) >= max(x for x,y in low_points) and
                    min(y for x,y in up_points) <= min(y for x,y in low_points) and
                    max(y for x,y in up_points) >= max(y for x,y in low_points)):
                hidden.add(tuple(lower.fields()))
                break
    return hidden


def _select_enclosing_caption_panels(caption, box, candidates, geometry, fullscreen_ids):
    """Prove local coverage or shared masks and choose supports for every occupied interval."""
    mask = caption_clip_outline(caption)
    if box is None and mask is None:
        return []
    enclosing = []
    for e in candidates:
        if (e.source_index in fullscreen_ids or
                e.source_index not in geometry or e.style != caption.style or
                e.name != caption.name or not e.layer.lstrip('-').isdigit() or
                not caption.layer.lstrip('-').isdigit() or
                int(e.layer) > int(caption.layer)):
            continue
        overlap = min(e.end_s, caption.end_s)-max(e.start_s, caption.start_s)
        if overlap <= 0:
            continue
        # Backdrops need only support the text while both are visible.
        # Preserve source timing; no minimum percentage or maximum gap.
        points, bounds = geometry[e.source_index]
        contained = caption_panel_contains(e, points, caption, box)
        # Authored reuse of the same simple path is explicit panel/mask
        # evidence even for rotated, sheared or projective lettering.
        # Both must contain the text anchor in rendered scene space: a
        # reused shape parked elsewhere is not a supporting panel.
        shared_outline = mask is not None and drawing_matches_caption_outline(e, caption, points)
        if contained or shared_outline:
            enclosing.append((e, contained))
    if enclosing:
        # Choose the uppermost local support separately for each occupied
        # interval. A later panel cannot erase an earlier panel that is
        # the text's only support before or after their shared interval.
        times = sorted({caption.start_s, caption.end_s} |
                       {t for e, _ in enclosing for t in
                        (max(e.start_s, caption.start_s),
                         min(e.end_s, caption.end_s))})
        winners = {}
        for start, end in zip(times, times[1:]):
            top = max(((e, measured) for e, measured in enclosing
                       if e.start_s < end and e.end_s > start),
                      key=lambda item: (int(item[0].layer), item[0].source_index), default=None)
            if top is not None:
                winners[top[0].source_index] = top
        return list(winners.values())
    return []


def _match_adjacent_caption_shapes(candidates, nearby, geometry, fullscreen_ids, selected):
    """Associate unselected sparse decorative shapes without changing established panel choices."""
    # Adjacent arrows and small polygon patches are useful even when they are
    # not backgrounds enclosing text. Reject dense drawings and lyric regions.
    sparse = collections.Counter((e.start, e.end, e.style, e.name) for e in candidates
                                 if e.source_index not in fullscreen_ids)
    adjacent = {}
    for e in candidates:
        if (e.source_index in selected or e.source_index in adjacent or
                e.source_index not in geometry):
            continue
        points, bounds = geometry[e.source_index]
        primitive = drawing_polygon(e)
        if (e.duration < .12 or sparse[(e.start, e.end, e.style, e.name)] > 8 or
                e.evidence.original_contour_points is not None or
                primitive is None or len({x for x, y in primitive}) == 2 and
                len({y for x, y in primitive}) == 2):
            continue
        for caption, box in nearby:
            overlap = min(caption.end_s, e.end_s)-max(caption.start_s, e.start_s)
            if (caption.style != e.style or caption.name != e.name or
                    overlap < .8*min(caption.duration, e.duration)):
                continue
            height = text_height(caption)
            dx = max(box[0]-bounds[2], bounds[0]-box[2], 0)
            dy = max(box[1]-bounds[3], bounds[1]-box[3], 0)
            if (math.hypot(dx, dy) <= 1.5*height and
                    bounds[2]-bounds[0] <= 5*height and
                    bounds[3]-bounds[1] <= 5*height):
                adjacent[e.source_index] = [caption]
                break
    return adjacent


def select_caption_supports(candidates, captions, metric):
    """Preserve the established two-result support-selection API."""
    kept, associated, _ = _select_caption_supports(candidates, captions, metric)
    return kept, associated


def _select_caption_supports(candidates, captions, metric) -> tuple[list[Event], dict, list[CaptionPanelOwnership]]:
    """Keep fullscreen fills and the uppermost local support in each interval.

    Adjacency is only considered for small, straight, non-rectangular shapes
    in a sparse sign group. It does not imply video coverage or text recovery.
    """
    eligible = [e for e in captions
             if e.kind == 'Dialogue' and not e.state.get('p', 0) and
             bool(OVERRIDE_RE.sub('', e.text).strip()) and not e.lyric]
    boxes = {e.source_index: caption_bounds(e, metric) for e in eligible}
    nearby = [(e, caption_bounds(e, metric, adjacency=True)) for e in captions
              if e.kind == 'Dialogue' and not e.state.get('p', 0) and
              len(OVERRIDE_RE.sub('', e.text).strip()) >= 2 and not e.lyric]
    nearby = [(e, box) for e, box in nearby if box is not None]
    geometry = {}
    for e in candidates:
        info = coverage_geometry(e)
        if info is not None:
            points, bounds, _ = info
            xs, ys = zip(*points)
            box = (min(xs), min(ys), max(xs), max(ys))
            geometry[e.source_index] = points, box
        elif rectangle_clip(e) is not None:
            # Scene-coordinate clip bounds also bound rotated/aligned paths.
            # They are sufficient for adjacency, but cannot prove fill coverage.
            geometry[e.source_index] = None, rectangle_clip(e)
    fullscreen_ids = {e.source_index for e in candidates if is_fullscreen_background(e)}
    selected, associated, enclosing_ids = set(fullscreen_ids), {}, set()
    measured_claims = []
    # Fullscreen fills do not compete with local panels or require font
    # measurement. Preserve source layers so both can sit beneath their text.
    for e in candidates:
        if e.source_index in fullscreen_ids:
            associated[e.source_index] = [caption for caption in captions
                if caption.kind == 'Dialogue' and caption.style == e.style and
                caption.name == e.name and not caption.state.get('p', 0) and
                min(caption.end_s, e.end_s) > max(caption.start_s, e.start_s)]
    for caption in eligible:
        for top, measured in _select_enclosing_caption_panels(
                caption, boxes[caption.source_index], candidates, geometry, fullscreen_ids):
            selected.add(top.source_index)
            enclosing_ids.add(top.source_index)
            associated.setdefault(top.source_index, []).append(caption)
            if measured and any(c.isalnum() for c in OVERRIDE_RE.sub('', caption.text)):
                measured_claims.append((top.source_index, caption))
    adjacent = _match_adjacent_caption_shapes(
        candidates, nearby, geometry, fullscreen_ids, selected)
    selected.update(adjacent)
    associated.update(adjacent)
    kept = []
    for e in candidates:
        if e.source_index not in selected:
            continue
        if (e.source_index in enclosing_ids and
                e.evidence.original_contour_points is not None):
            # Reconstructed enclosing panels hide the picture behind a caption.
            # Their original translucent paint may have depended on discarded
            # scene artwork underneath. Keep the simplified contour, colour
            # and pose, but make these enclosing panels opaque. Gradient bands
            # and adjacent decorative shapes retain their original opacity.
            e = replace_event(e, text=re.sub(r'\\([12])a&H[0-9a-f]+&',
                                            r'\\\1a&H00&', e.text, flags=re.I),
                              evidence=e.evidence)
        kept.append(e)
    # Retain the already proved measured relationship. Alpha normalization
    # changes paint, not the contour; do not repeat font/polygon containment.
    qualified = {e.source_index: e for e in kept if
                 e.source_index in enclosing_ids and
                 (info := coverage_geometry(e)) is not None and info[2] and
                 static_object_key(e, e.styles) is not None}
    ownership = [CaptionPanelOwnership(qualified[index], caption)
                 for index, caption in measured_claims if index in qualified]
    return kept, associated, ownership


def retain_unmeasured_backdrops(events, captions, kept, metric, *, scaled_borders=True):
    """Preserve baseline supports for unknown text, without equivalent copies."""
    caption_groups = {}
    for caption in captions:
        if (caption.kind == 'Dialogue' and not caption.state.get('p', 0) and
                OVERRIDE_RE.sub('', caption.text).strip()):
            caption_groups.setdefault((caption.style, caption.name), []).append(
                (caption, caption_bounds(caption, metric)))
    def fill_key(event):
        # Compare rendered fill footprints, not header spelling or unused
        # shadow/outline alpha. Never equate extra visible stroke/shadow paint.
        event = normalize_drawing_alignment(flatten_rectangular_border(
            event, scaled_borders=scaled_borders))
        st = event.state
        if (drawing_polygon(event) is None or st.get('1a', 0) >= 254 or
                st.get('3a', 0) < 254 and any(st.get(k, st.get('bord', 0))
                                            for k in ('xbord', 'ybord')) or
                st.get('4a', 0) < 254 and any(st.get(k, st.get('shad', 0))
                                            for k in ('xshad', 'yshad')) or
                'iclip' in st or 'clip' in st and rectangle_clip(event) is None):
            return None
        info = coverage_geometry(event)
        if info is None:
            return None
        points = tuple((round(x, 6), round(y, 6)) for x, y in info[0])
        if points[-1] == points[0]:
            points = points[:-1]
        polygon = min(order[i:]+order[:i] for order in (points, points[::-1])
                      for i in range(len(points)))
        return (event.start, event.end, event.layer, event.style, event.name,
                st.get('1c'), st.get('1a', 0), polygon, rectangle_clip(event))
    equivalents = {key for event in kept if (key := fill_key(event)) is not None}
    fullscreen_paints = {(v.start, v.end, v.layer, v.style, v.name,
                          v.state.get('1c'), v.state.get('1a', 0))
                         for v in kept if is_fullscreen_background(v)}
    fallback = []
    for event in events:
        if event.kind != 'Dialogue' or not event.state.get('p', 0):
            continue
        overlapping = [(caption, box) for caption, box in
                       caption_groups.get((event.style, event.name), [])
                       if min(caption.end_s, event.end_s) > max(caption.start_s, event.start_s)]
        # A known caption elsewhere cannot disprove the support needed by an
        # unknown caption in the same group. Retain the existing fallback
        # whenever any overlapping caption remains unmeasurable.
        if overlapping and all(box is not None for caption, box in overlapping):
            continue
        key = fill_key(event)
        if key is not None and key in equivalents:
            continue
        if (is_fullscreen_background(event) and
                (event.start, event.end, event.layer, event.style, event.name,
                 event.state.get('1c'), event.state.get('1a', 0)) in fullscreen_paints):
            continue
        fallback.append(event)
    return fallback


def _restore_caption_paint(
    sources: list[Event],
    events: list[Event],
) -> tuple[list[Event],dict[str,int]]:
    """Restore held shadow placement and masked solid foregrounds."""
    events, repaired_shadows = repair_caption_shadow_offsets(sources, events)
    events, restored_foregrounds = restore_masked_caption_foregrounds(sources, events)
    return events,{'masked_foregrounds_restored':restored_foregrounds,'shadow_offsets_repaired':repaired_shadows}


def _limit_scrolling_text(
    events: list[Event],
    lines: list[str],
    config: SimplifyConfig,
    font_metrics: FontMetrics | None,
) -> tuple[list[Event],list[dict],dict[str,int]]:
    """Apply the destructive fallback only to overloaded residual scrolling blocks."""
    # Judge the residual moving block, after all ordinary text reduction.
    # A dense source or a large number of successive frames is not enough.
    before_scroll = len(events)
    events, scroll_report = drop_overloaded_scrolling_blocks(
        events, script_resolution(lines, 'x'), script_resolution(lines, 'y'),
        font_metrics, concurrency_limit=config.scroll_concurrency_limit)
    scrolling_removed = before_scroll-len(events)
    counts = {
        'scrolling_events_dropped':scrolling_removed,
        'scrolling_blocks_detected':len(scroll_report),
        'scrolling_blocks_dropped':sum(b['action']=='removed' for b in scroll_report),
        'scrolling_blocks_retained':sum(b['action']=='retained' for b in scroll_report),
        'scrolling_peak_after_reduction':max((b['peak_concurrent'] for b in scroll_report),default=0),
        'scrolling_concurrency_limit':config.scroll_concurrency_limit,
    }
    return events,scroll_report,counts


def _rebuild_caption_supports(
    sources: list[Event],
    source_lines: list[str],
    events: list[Event],
    lines: list[str],
    caption_counts: dict[str,int],
    config: SimplifyConfig,
    font_metrics: FontMetrics | None,
) -> CaptionSupportResult:
    """Reduce and associate supports, then insert them with preserved layering."""
    scaled_borders = any(line.strip().lower() == 'scaledborderandshadow: yes'
                         for line in source_lines)
    candidates, counts = reduce_supporting_drawings(sources, scaled_borders=scaled_borders)
    counts.update(caption_counts)
    # Texture removal is only for proved stamps in a replacement sign:
    # there must also be retained literal text and a supporting shape.
    textures = {e.source_index for e in events if e.kind == 'Dialogue' and
                is_font_texture(e, font_metrics)}
    captions = [e for e in events if e.source_index not in textures]
    composites = reconstruct_composite_backdrops(sources, captions, font_metrics)
    candidates += composites
    counts['composite_backdrops_built'] = len(composites)
    if config.max_drawing_chars > 0:
        candidates = [e for e in candidates if
                      len(OVERRIDE_RE.sub('', e.text)) <= config.max_drawing_chars]
    kept, associated, ownership = _select_caption_supports(candidates, captions, font_metrics)
    fallback_vectors = retain_unmeasured_backdrops(
        events, captions, kept, font_metrics, scaled_borders=scaled_borders)
    budgeted, capped = cap_vector_cues(kept+fallback_vectors, config.max_vectors_per_cue)
    budget_ids = {id(e) for e in budgeted}
    kept = [e for e in kept if id(e) in budget_ids]
    ownership = [relation for relation in ownership if id(relation.panel) in budget_ids]
    fallback_vectors = [e for e in fallback_vectors if id(e) in budget_ids]
    counts['drawing_events_capped'] = capped
    removed_textures = set()
    resx = script_resolution(lines, 'x')
    resy = script_resolution(lines, 'y')
    for e in events:
        if e.source_index not in textures:
            continue
        box = caption_bounds(e, font_metrics)
        if box is not None:
            # Only ink inside the rendered viewport can affect the video.
            # Inset a boundary-touching test box for the strict polygon
            # containment helper; no ink outside the viewport is exposed.
            eps = 1e-4*e.unit
            box = (max(eps, box[0]), max(eps, box[1]),
                   min(resx-eps, box[2]), min(resy-eps, box[3]))
        if box is not None and box[0] < box[2] and box[1] < box[3] and any(
                v.start_s <= e.start_s+.001 and v.end_s >= e.end_s-.001 and
                (geometry := coverage_geometry(v)) is not None and
                caption_panel_contains(v, geometry[0], e, box) for v in kept):
            removed_textures.add(e.source_index)
    counts['unmeasured_backdrops_retained'] = len(fallback_vectors)
    fallback_ids = {e.source_index for e in fallback_vectors}
    # Enclosing supports were proved to be below their captions. Nearby
    # arrows may intentionally have a higher layer; preserve their original
    # layering rather than raising the associated literal text.
    result = [e for e in events
              if (not (e.kind == 'Dialogue' and e.state.get('p', 0)) or
                  e.source_index in fallback_ids) and
              e.source_index not in removed_textures]
    # Insert supports before their associated retained captions. Do not
    # sort unrelated same-layer captions by start time or source indices
    # from the source document: normalization establishes a separate index space.
    insertion, standalone = {}, []
    for v in kept:
        if not associated[v.source_index]:
            standalone.append(v)
            continue
        index = min(e.source_index for e in associated[v.source_index])
        insertion.setdefault(index, []).append(v)
    combined = sorted(standalone, key=lambda v: (int(v.layer), v.source_index))
    for e in result:
        combined.extend(sorted(insertion.pop(e.source_index, []),
                               key=lambda v: (int(v.layer), v.source_index)))
        combined.append(e)
    # The text engine already ran its touching-copy pass. Preserve that
    # order after the targeted solid-mask correction and support insertion.
    combined = [dataclass_replace(e, source_index=i) for i, e in enumerate(combined)]
    return CaptionSupportResult(combined,kept,fallback_vectors,associated,removed_textures,counts,ownership)


def _reconstruct_caption_backdrops(
    source: SubtitleDocument,
    captions: SubtitleDocument,
    config: SimplifyConfig,
    font_metrics: FontMetrics | None,
) -> tuple[CaptionSupportResult,list[dict]]:
    """Consume original drawings and normalized text after text reduction ends.

    Text proof state belongs to the text engine. This stage uses only ASS
    formatting and fresh document indices, with the original source retained
    for paint repair and supporting-shape evidence.
    """
    sources = list(source.events.values())
    events,paint_counts = _restore_caption_paint(sources,list(captions.events.values()))
    events,scroll_report,caption_counts = _limit_scrolling_text(
        events,captions.lines,config,font_metrics)
    caption_counts.update(paint_counts)
    supports = _rebuild_caption_supports(
        sources,source.lines,events,captions.lines,caption_counts,config,font_metrics)
    return supports,scroll_report


def settle_caption_backdrop_layers(
    supports: CaptionSupportResult, events: list[Event], font_metrics: FontMetrics | None,
) -> CaptionSupportResult:
    """Settle final opaque captions above already proved local backgrounds.

    Late shadow normalization can make a caption readable after the text-stage
    layer proof. Only retained enclosing panels, full-lifetime exact-font
    coverage and identical style/actor authorize promotion. Adjacent decorations,
    fullscreen fills and unmeasured supports keep their source order.
    """
    if font_metrics is None or not font_metrics.available:
        return dataclass_replace(supports, events=events)

    # Production carries the proof from support selection. Older direct
    # constructors can establish it once; later reassociation never invents it.
    ownership = (supports.ownership if supports.ownership is not None else
                 _caption_panel_ownership(supports.kept, supports.associated, font_metrics))
    retained = {tuple(panel.fields()): panel for panel in supports.kept}
    panels, owners, normalized_ownership = {}, {}, []
    geometries, captions = {}, {}
    for relation in ownership:
        panel = relation.panel
        if id(panel) not in geometries:
            geometries[id(panel)] = coverage_geometry(panel)
        geometry = geometries[id(panel)]
        if geometry is None:
            continue
        points = geometry[0]
        if id(relation.caption) not in captions:
            normalized,_ = normalize_shadow_lettering([relation.caption])
            captions[id(relation.caption)] = normalized[0]
        caption = captions[id(relation.caption)]
        normalized_ownership.append(CaptionPanelOwnership(panel, caption))
        owners.setdefault(tuple(caption.fields()), []).append((panel, points))
        if tuple(panel.fields()) in retained:
            actual = retained[tuple(panel.fields())]
            panels[tuple(actual.fields())] = (actual, points)
    panels = list(panels.values())
    if not panels:
        return dataclass_replace(supports, events=events, ownership=list(ownership))
    families = {}
    for panel, points in panels:
        families.setdefault((panel.style, panel.name), []).append((panel, points))

    settled = []
    drawing_order = {tuple(event.fields()): index for index,event in enumerate(events) if event.state.get('p', 0)}
    for index,event in enumerate(events):
        if (event.kind != 'Dialogue' or event.state.get('p', 0) or
                not event.layer.lstrip('-').isdigit() or event.state.get('1a', 0) != 0 or
                (event.style, event.name) not in families or
                tuple(event.fields()) not in owners or
                not any(c.isalnum() for c in OVERRIDE_RE.sub('', event.text)) or
                get_pos(event.text) is None or static_object_key(event, event.styles) is None):
            settled.append(event)
            continue
        box = caption_bounds(event, font_metrics)
        layer = int(event.layer)
        # Preserve an independent card/mask already painted above this text.
        # Promoting merely to its layer can also expose a later text record.
        if box is not None and any(
            (int(panel.layer), drawing_order.get(tuple(panel.fields()), -1)) > (layer, index) and
            min(panel.end_s,event.end_s) > max(panel.start_s,event.start_s) and
            (not any(_same_caption_panel(panel,points,owner,owner_points)
                     for owner,owner_points in owners[tuple(event.fields())]) or
             panel.start_s > event.start_s+.001 or panel.end_s < event.end_s-.001) and
            min(x for x,y in points) < box[2] and max(x for x,y in points) > box[0] and
            min(y for x,y in points) < box[3] and max(y for x,y in points) > box[1]
            for panel,points in families[event.style,event.name]):
            settled.append(event)
            continue
        for panel, points in families[event.style, event.name]:
            if (panel.start_s <= event.start_s + .001 and panel.end_s >= event.end_s - .001 and
                    any(_same_caption_panel(panel, points, owner, owner_points)
                        for owner, owner_points in owners[tuple(event.fields())]) and
                    caption_panel_contains(panel, points, event, box)):
                layer = max(layer, int(panel.layer) + 1)
        settled.append(replace_event(event, layer=str(layer)) if layer != int(event.layer) else event)

    successors = {tuple(old.fields()): new for old,new in zip(events, settled)}
    ownership = [CaptionPanelOwnership(relation.panel, successors[tuple(relation.caption.fields())])
                 for relation in normalized_ownership if tuple(relation.caption.fields()) in successors]

    # Remove a lower rectangular support only when a retained opaque rectangle
    # covers all of its fill for its entire lifetime. Partial masks remain.
    hidden = _covered_caption_panels(panels)
    kept = [panel for panel in supports.kept if tuple(panel.fields()) not in hidden]
    settled = [event for event in settled if not (event.state.get('p', 0) and tuple(event.fields()) in hidden)]
    associated = {panel.source_index: [event for event in settled
        if event.kind == 'Dialogue' and not event.state.get('p', 0) and
        event.layer.lstrip('-').isdigit() and int(panel.layer) <= int(event.layer) and
        event.style == panel.style and event.name == panel.name and
        min(event.end_s, panel.end_s) > max(event.start_s, panel.start_s) and
        caption_panel_contains(panel, geometry[0], event, caption_bounds(event, font_metrics))]
        for panel in kept if (geometry := coverage_geometry(panel)) is not None}
    # Preserve associations for non-enclosing arrows/fullscreen/fallback shapes.
    for panel in kept:
        if not associated.get(panel.source_index):
            associated[panel.source_index] = list(supports.associated.get(panel.source_index, ()))
    counts = dict(supports.counts)
    counts['drawing_duplicates_removed'] += len(supports.kept) - len(kept)
    return dataclass_replace(supports, events=settled, kept=kept, associated=associated, counts=counts, ownership=ownership)


def _summarize_caption_supports(
    stats: dict[str,object],
    supports: CaptionSupportResult,
    font_metrics: FontMetrics | None,
) -> dict[str,object]:
    """Update output counts and distinguish enclosing, fullscreen and adjacent supports."""
    combined = supports.events
    kept = supports.kept
    fallback_vectors = supports.fallback
    associated = supports.associated
    removed_textures = supports.removed_textures
    counts = supports.counts
    capped = counts['drawing_events_capped']
    stats.update(counts)
    stats['excess_vectors'] += capped
    stats['supporting_shapes_retained'] = len(kept)
    stats['font_textures_removed'] = len(removed_textures)
    stats['fullscreen_backgrounds_retained'] = sum(is_fullscreen_background(v) for v in kept)
    stats['output'] = sum(e.kind == 'Dialogue' for e in combined)
    stats['max_concurrent_out'] = peak_concurrent_events(combined)
    stats['vector_output'] = sum(e.kind == 'Dialogue' and bool(e.state.get('p', 0))
                                 for e in combined)
    enclosed = 0
    for v in kept:
        if is_fullscreen_background(v):
            continue
        info = coverage_geometry(v)
        clip = rectangle_clip(v)
        if info is not None and any(drawing_matches_caption_outline(v, e, info[0]) or
                (box := caption_bounds(e, font_metrics)) is not None and
                polygon_covers_box(info[0], box) and (clip is None or
                clip[0] < box[0] and clip[1] < box[1] and
                clip[2] > box[2] and clip[3] > box[3]) for e in associated[v.source_index]):
            enclosed += 1
    stats['backdrops_retained'] = enclosed+len(fallback_vectors)+stats['fullscreen_backgrounds_retained']
    stats['adjacent_shapes_retained'] = len(kept)-enclosed-stats['fullscreen_backgrounds_retained']
    return stats


def _print_support_report(
    supports: CaptionSupportResult,
    scroll_report: list[dict],
    config: SimplifyConfig,
) -> None:
    """Print the existing support and scrolling diagnostics."""
    kept = supports.kept
    removed_textures = supports.removed_textures
    counts = supports.counts
    print(f"  Caption supports: {len(kept)} supporting shapes; "
          f"{counts['drawing_strips_collapsed']} strips collapsed; "
          f"{len(removed_textures)} font textures removed")
    if scroll_report:
        print(f"  Scrolling fallback: {counts['scrolling_blocks_dropped']} blocks removed; "
              f"{counts['scrolling_blocks_retained']} retained; "
              f"remaining block peak {counts['scrolling_peak_after_reduction']} "
              f"(limit {config.scroll_concurrency_limit}; 0 disables removal)")


def normalize_shadow_lettering(events: list[Event]) -> tuple[list[Event], int]:
    """Replace static nearly coincident shadow lettering with primary paint.

    Run only after caption support proofs have finished. A foreground at
    alpha FE/FF contributes at most 1/255 opacity; discard that faint copy
    using the existing faint-paint convention. Preserve the actual shadow
    colour, alpha and anchor. Ordinary shadows, strokes and multiple text
    spans are outside this normalization.
    """
    output, count = [], 0
    for event in events:
        state = event.state
        if (event.kind != 'Dialogue' or state.get('p', 0) or
                state.get('1a', 0) < 254 or state.get('4a', 0) >= 254 or
                inline_layout_key(event)):
            output.append(event)
            continue
        obj = static_object_key(event, event.styles)
        if obj is None or len(obj[-1]) != 1 or obj[-1][0][1]:
            output.append(event)
            continue
        state = dict(obj[-1][0][0].formatting)
        pos = state.get('pos')
        dx, dy = (state.get(k, state.get('shad', 0)) for k in ('xshad', 'yshad'))
        color = str(state.get('4c', '000000')).upper()
        if (state.get('p', 0) or state.get('1a', 0) < 254 or
                state.get('4a', 0) >= 254 or state.get('borderstyle', 1) != 1 or
                pos is None or 'clip' in state or 'iclip' in state or
                str(state.get('fn', '')).startswith('@') or
                any(state.get(k, 0) for k in ('frz', 'frx', 'fry', 'fax', 'fay', 'blur', 'be')) or
                any(state.get(k, state.get('bord', 0)) != 0 for k in ('xbord', 'ybord')) or
                not all(math.isfinite(v) for v in (*pos, dx, dy, event.unit)) or
                not 0 < max(abs(dx), abs(dy)) <= .05 * event.unit or
                not re.fullmatch(r'[0-9A-F]{6}', color)):
            output.append(event)
            continue
        paint = {'1c': color, '1a': state.get('4a', 0), '4a': 255,
                 'shad': 0, 'xshad': 0, 'yshad': 0}
        tags = ''.join(render_tag(k, v) for k, v in paint.items())
        # The proved single text span has no later formatting. Append the
        # replacement after all leading overrides so resets/global alpha
        # cannot override the transferred paint. Keep authored text verbatim.
        boundary = re.match(r'(?:\{[^}]*\})*', event.text).end()
        # ASS uses the first position tag, so replace that authored tag
        # instead of appending another one. Preserve subpixel precision.
        position = r'\pos('+','.join(format(v, '.15g') for v in (pos[0]+dx, pos[1]+dy))+')'
        prefix = re.sub(r'\\pos\([^)]*\)', lambda _: position,
                        event.text[:boundary], count=1, flags=re.I)
        text = prefix+'{'+tags+'}'+event.text[boundary:]
        output.append(replace_event(event, text=text))
        count += 1
    return output, count


def _bounded_text_color(votes: dict[str,float]) -> str | None:
    """Use one observed color only when the complete palette fits two RGB levels."""
    if len(votes)<2:return None
    rgb=[tuple(int(color[i:i+2],16) for i in (0,2,4)) for color in votes]
    if any(max(c[axis] for c in rgb)-min(c[axis] for c in rgb)>2 for axis in range(3)):
        return None
    return min(votes,key=lambda color:(-votes[color],color))


def normalize_near_text_colors(events: list[Event]) -> tuple[list[Event], int]:
    """Collapse bounded static text palettes, preserving wider gradients.

    A style/channel's complete palette must fit within two 8-bit RGB levels
    on every axis. Never form transitive clusters. Animated/mixed drawings
    and hidden paint veto that style/channel. Inline variation is permitted
    inside the same full-palette bound, including tiny ordered ramps.
    Styles and borrowed events remain unchanged; run after all source proofs.
    """
    palettes, blocked = {}, set()
    for event in events:
        if event.kind != 'Dialogue':
            continue
        obj = static_object_key(event, event.styles, allow_unpositioned=True)
        if obj is None or any(drawing for _, drawing, _ in obj[-1]):
            blocked.update((event.style, channel) for channel in (1, 3))
            continue
        spans = [(dict(signature.formatting), text) for signature, _, text in obj[-1]
                 if text.strip()]
        for channel in (1, 3):
            key = event.style, channel
            for state, text in spans:
                color = str(state.get(f'{channel}c', '')).upper()
                if (not re.fullmatch(r'[0-9A-F]{6}', color) or
                        state.get(f'{channel}a', 0) >= 254 or
                        channel == 3 and (state.get('borderstyle', 1) != 1 or
                            max(abs(state.get(k, state.get('bord', 0)))
                                for k in ('xbord', 'ybord')) <= 0)):
                    blocked.add(key)
                    continue
                votes = palettes.setdefault(key, {})
                votes[color] = votes.get(color, 0) + event.duration * len(text)
    representatives = {}
    for key, votes in palettes.items():
        if key in blocked:
            continue
        representative=_bounded_text_color(votes)
        if representative is not None:
            representatives[key]=representative
    output, count = [], 0
    color_tag = re.compile(r'\\(1c|3c|c)(?![A-Za-z])[^\\]*', re.I)
    for event in events:
        targets = {channel: representatives[event.style, channel] for channel in (1, 3)
                   if (event.style, channel) in representatives}
        if not targets or event.kind != 'Dialogue':
            output.append(event)
            continue
        state = event.defaults.copy()
        continuation = OverrideContinuation()
        parts = []
        for part in re.split(r'(\{[^}]*\})', event.text):
            if not part:
                continue
            if part.startswith('{') and part.endswith('}'):
                # Only admitted channels become constant. Preserve other raw
                # tags, their order and reset/alignment continuation.
                block = color_tag.sub(lambda m: '' if
                    (1 if m[1].lower() in ('c', '1c') else 3) in targets else m[0],
                    part[1:-1])
                if block:
                    parts.append('{'+block+'}')
                    for name, value in tokenize_override(block):
                        continuation = apply_override(state, name, value,
                                                      event.styles, event.defaults, continuation)
            else:
                tags = ''.join(render_tag(f'{channel}c', color)
                               for channel, color in targets.items()
                               if str(state.get(f'{channel}c', '')).upper() != color)
                if tags:
                    if parts and parts[-1].startswith('{') and parts[-1].endswith('}'):
                        parts[-1] = parts[-1][:-1]+tags+'}'
                    else:
                        parts.append('{'+tags+'}')
                    state.update({f'{channel}c': color for channel, color in targets.items()})
                parts.append(part)
        text = ''.join(parts)
        if text == event.text:
            output.append(event)
        else:
            output.append(replace_event(event, text=text))
            count += 1
    return output, count


def _near_containing_text_copy(event: Event, other: Event, height: float,
                               other_height: float) -> bool:
    """Whole-lifetime coverage at a near anchor; no timing or anchor extension."""
    x, y = get_pos(event.text)
    ox, oy = get_pos(other.text)
    radius = .06 * min(height, other_height)
    return (math.isfinite(radius) and other.start_s <= event.start_s
            and other.end_s >= event.end_s and abs(x - ox) <= radius
            and abs(y - oy) <= radius)


def remove_late_complete_copies(events: list[Event]) -> tuple[list[Event], int]:
    """Apply strict redundancy after reconstructed text and paint are final."""
    return remove_redundant_text_copies(events)


def remove_redundant_text_copies(events: list[Event], *, pending_lyrics: bool = False) -> tuple[list[Event], int]:
    """Remove static, wholly covered text records with identical literal spans.

    Compare every literal span, including paint, parser history and document
    context. Only the anchor may differ, within the existing six-percent text
    height bound. Require equal layers and preserve intervening compositing.
    Retained records alone provide coverage, so offset chains cannot drift.
    Borrow records, styles and formatting caches without modifying them.
    """
    groups: dict[tuple, list[tuple[int, Event]]] = {}
    layers: dict[int | None, list[int]] = {}
    heights: dict[int, float] = {}
    wrapping: set[int] = set()
    for index, event in enumerate(events):
        try:
            layer = int(event.layer)
        except ValueError:
            layer = None
        if event.kind == 'Dialogue':
            layers.setdefault(layer, []).append(index)
        if layer is None or (pending_lyrics and event.lyric):
            continue
        pos = get_pos(event.text)
        if (pos is None or not all(math.isfinite(v) for v in pos)
                or has_translucent_paint(event)):
            continue
        key = static_object_key(event, event.styles)
        if key is None:
            continue
        runs, span_heights = [], []
        for signature, drawing, payload in key[-1]:
            state = dict(signature.formatting)
            if (drawing or state.get('pos') != pos or state.get('clip') is not None
                    or state.get('iclip') is not None):
                break
            span_heights.append(max(event.unit, abs(state.get('fs', 20) * state.get('fscy', 100) / 100)))
            if state.get('q', event.measurement.script_wrap_mode) != 2:
                wrapping.add(index)
            runs.append((StaticSpanSignature(tuple((k, v) for k, v in signature.formatting
                                                  if k != 'pos'), signature.continuation), payload))
        else:
            # Match the whole record, however short it is. This proves one
            # redundant copy, not that a fragment has become a complete line.
            if runs:
                heights[index] = min(span_heights)
                groups.setdefault((layer,) + key[1:-1] + (tuple(runs),), []).append((index, event))

    unknown = layers.get(None, ())
    if unknown:
        for layer, peers in layers.items():
            if layer is not None:
                peers.extend(unknown)
                peers.sort()

    removed: set[int] = set()
    for group in groups.values():
        retained: list[tuple[int, Event]] = []
        for index, event in sorted(group, key=lambda item: (-item[1].duration, item[0])):
            x, y = get_pos(event.text)
            for other_index, other in retained:
                ox, oy = get_pos(other.text)
                if (not _near_containing_text_copy(event, other, heights[index], heights[other_index])
                        # Translating an automatically wrapped line can change
                        # its available width and actual rendered line breaks.
                        or ((x != ox or y != oy) and (index in wrapping or other_index in wrapping))):
                    continue
                low, high = sorted((index, other_index))
                peers = layers[int(event.layer)]
                if any(peer not in removed and events[peer].start_s < event.end_s
                       and events[peer].end_s > event.start_s
                       for peer in peers[bisect_right(peers, low):bisect_left(peers, high)]):
                    continue
                removed.add(index)
                break
            else:
                retained.append((index, event))
    return [event for index, event in enumerate(events) if index not in removed], len(removed)


def simplify_ass(
    path: Path, output: Path, config: SimplifyConfig, *, font_metrics: FontMetrics | None=None,
    font_report: FontProcessingReport | None=None, outline_matcher: FontOutlineMatcher | None=None,
) -> dict[str, object]:
    """Read once, reduce text, normalize its result, then reconstruct backdrops.

    Borrow font_metrics for reusable measurements. A supplied outline matcher
    must share that owner; otherwise one matcher is local to this conversion.
    Mutate only the explicitly supplied font_report for selective diagnostics
    and committed measured joins. The caller chooses its run or batch lifetime;
    omitted reporting is discarded without changing simplification decisions.
    """
    if outline_matcher is not None and outline_matcher.metrics is not font_metrics:
        raise ValueError('Outline matcher must use the supplied FontMetrics owner.')
    if outline_matcher is None and font_metrics is not None:
        outline_matcher = FontOutlineMatcher(font_metrics)
    if config.level != 1:
        return _simplify_text_and_vectors(path,output,config,font_metrics=font_metrics, font_report=font_report, outline_matcher=outline_matcher)
    if path.resolve() == output.resolve():
        raise ValueError('Subtitle output must differ from its input.')
    if config.scroll_concurrency_limit < 0:
        raise ValueError('Scrolling concurrency limit must be nonnegative.')
    document = read_subtitle_document(path,config.encoding)
    source = _resolve_document_state(document)
    text_source = _prepare_text_document(document,path)
    text_result = _process_text_and_vectors(text_source,config,font_metrics, font_report=font_report, outline_matcher=outline_matcher)
    captions = _normalize_text_result(text_source,text_result)
    supports,scroll_report = _reconstruct_caption_backdrops(source,captions,config,font_metrics)
    output_events, shadow_lettering = normalize_shadow_lettering(supports.events)
    supports = settle_caption_backdrop_layers(supports, output_events, font_metrics)
    output_events = supports.events
    output_events, normalized_colors = normalize_near_text_colors(output_events)
    output_events, late_copies = remove_late_complete_copies(output_events)
    output_events, late_phases = merge_static_timed_copies(
        output_events, captions.styles, font_metrics=font_metrics, text_only=True)
    # All source, ownership, paint, copy and phase proofs are complete.
    # Serialization changes spelling only; it does not rerun those policies.
    output_events = compact_static_overrides(output_events, config.max_blur, final=True)
    supports = dataclass_replace(supports, events=output_events)
    write_subtitle_document(output,captions,output_events,final_newline=True)
    stats = _summarize_caption_supports(text_result.statistics,supports,font_metrics)
    stats['shadow_lettering_normalized'] = shadow_lettering
    stats['deduped'] += late_copies
    stats['static_merged'] += late_phases
    if normalized_colors:
        stats['text_colors_normalized'] = normalized_colors
    _print_support_report(supports,scroll_report,config)
    return stats


if __name__ == '__main__':
    raise SystemExit(main())
