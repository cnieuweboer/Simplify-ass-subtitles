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
from _simplify_ass.word_echoes import (
    _word_echo_layout,
    _word_echo_families,
    _prove_word_echo_family,
    _owned_word_echo_anchors,
    remove_owned_word_echoes,
)
from _simplify_ass.covered_fragments import (
    CoveredFragmentContext,
    match_departing_glyph_effects,
    match_staggered_row_effects,
    _collect_covered_held_glyphs,
    _index_covered_row_times,
    _prepare_covered_fragments,
    _covered_fragment_spans,
    _covered_animated_shadow_source,
    _covered_held_glyph_copy,
    _timed_covered_rows,
    _prepare_covered_shadow_rows,
    _shared_covered_shadow_fade_core,
    _select_covered_shadow_timing,
    _covered_shadow_fragment_copy,
    _remove_covered_shadow_fragments,
    _covered_fragment_candidates,
    _covered_fragment_copy_matches,
    _remove_covered_fragment_copies,
    remove_covered_fragment_effects,
)
from _simplify_ass.row_evidence import CoveredFragmentRemoval
from _simplify_ass.effect_validation import animated_shadow_painted_source
from _simplify_ass.source_poses import (
    normalize_animated_rotations, adjacent_sustained_geometry, prefer_surviving_upright_poses,
)
from _simplify_ass.lyric_boundaries import (
    LyricBoundaryIndex,
    _index_lyric_boundaries,
    _crosses_lyric_boundary,
)
from _simplify_ass.text_effect_sequences import (
    TextEffectSequenceContext,
    TextEffectSequenceGeometry,
    TextEffectSequenceProfile,
    match_scale_trail,
    upright_text_holds,
    _prepare_text_effect_sequence_pass,
    _group_text_effect_sequences,
    _index_text_effect_sequence_geometry,
    _text_effect_sequence_neighbor,
    _cluster_text_effect_sequences,
    _prove_text_effect_sequence,
    _select_text_effect_sequence_geometry,
    _select_text_effect_sequence_paint,
    _construct_text_effect_sequence_caption,
    _flatten_text_effect_sequence_bucket,
    _finish_text_effect_sequences,
    flatten_text_effect_sequences,
)
from _simplify_ass.cue_fades import (
    FadedCueContext,
    FadedCueEvidence,
    shadow_lyric_fade_core,
    CueFadeFamily,
    text_cue_lane,
    derive_staggered_fade_cores,
    collect_faded_cue_families,
    _faded_cue_slot,
    _apply_faded_cue_families,
    _find_faded_cue_collisions,
    _parse_faded_source_evidence,
    _collect_faded_cue_evidence,
    _prove_faded_source_core,
    _prove_faded_cue_core,
    _select_readable_core_handoff,
    _select_faded_cue_handoff,
    synchronize_faded_cue_handoffs,
    _trim_owned_cue_backing,
    trim_faded_cue_overlaps,
)
from _simplify_ass.text_freezing import without_inert_spacing_tail
from _simplify_ass.event_operations import _faded_cue_is_scrolling
from _simplify_ass.glyph_lifecycles import (
    GlyphPhaseLife,
    _index_glyph_phase_slots,
    _profile_glyph_replacement,
    _prove_replacement_glyph_lives,
    _prove_glyph_phase_lives,
    reconstruct_glyph_lifecycles,
)
from _simplify_ass.row_evidence import TextRow, TextPhaseRowsResult
from _simplify_ass.fragment_spans import index_fragment_spans, matching_fragment_spans
from _simplify_ass.translated_phases import (
    TranslatedPhaseContext,
    TranslatedCueLayout,
    TranslatedCueModel,
    TranslatedCuePhases,
    _translated_layout_key,
    _match_touching_phase_fragments,
    _collect_translated_motion_profiles,
    _prepare_translated_phases,
    _select_translated_cue_layout,
    _fit_translated_cue_model,
    _translated_span_options,
    _translated_held_spans,
    _translated_entrance_spans,
    _covered_translated_pulses,
    _classify_translated_cue_phases,
    _prove_translated_cue_coverage,
    _render_translated_cue_proposal,
    _apply_translated_cue_proposals,
    collapse_translated_phase_rows,
)
from _simplify_ass.fragment_phases import (
    FragmentPhaseContext,
    FragmentPhaseProfile,
    _index_fragment_phase_rows,
    _previous_fragment_phases,
    _match_fragment_phase_join,
    _prove_fragment_phase_chain,
    _collect_fragment_phase_families,
    _group_fragment_phase_cues,
    _fit_fragment_phase_cue,
    _propose_fragment_phase_rows,
    _filter_incomplete_fragment_rows,
    _resolve_fragment_phase_ownership,
    _apply_fragment_phase_rows,
    collapse_fragment_phase_rows,
)
from _simplify_ass.shared_interval_rows import (
    SharedIntervalRowsResult,
    SharedIntervalContext,
    SharedIntervalProposal,
    SharedIntervalEdits,
    merge_shared_interval_rows,
    _shared_interval_bounds,
    _prepare_shared_interval_context,
    _group_shared_interval_candidates,
    _shared_interval_row_bands,
    _shared_interval_sweep_candidates,
    _shared_interval_candidate_windows,
    _shared_interval_slot_constraints,
    _fit_shared_interval_caption,
    _prove_shared_interval_candidate,
    _collect_shared_interval_proposals,
    _compatible_shared_interval_slots,
    _preserve_shared_interval_fragment_tails,
    _apply_shared_interval_proposal,
    _apply_shared_interval_proposals,
    _merge_shared_interval_rows_once,
)
from _simplify_ass.caption_geometry import (
    positioned_row_geometry, split_positioned_row_runs,
)
from _simplify_ass.font_metrics import (
    FontFace, FontCapabilities, FontLineInkMetrics, FontMetrics,
)
from _simplify_ass.font_outlines import FontOutlineMatcher, fit_cubic_points
from _simplify_ass.font_reporting import FontProcessingReport
from _simplify_ass.row_fitting import (
    recover_font_row, recover_tracked_font_row, fit_fullwidth_run,
)
from _simplify_ass.vector_text import (
    VectorTextFitContext,
    infer_vector_text_cues,
    _index_authored_vector_text_cues,
    _profile_vector_text_drawing,
    _index_vector_text_sources,
    _group_vector_text_runs,
    _measure_vector_text_outline,
    _select_vector_text_paint,
    _fit_vector_text_outline,
    _select_vector_text_cue_runs,
    _recover_vector_text_fragment_anchor,
    _reconstruct_vector_text_family,
    _propose_vector_text_cue,
    _apply_vector_text_ownership,
    recover_vector_text_cues,
)
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
from _simplify_ass.boundary_glyphs import (
    BoundaryGlyphPhase,
    BoundaryGlyphIndex,
    _boundary_glyph_geometry,
    _boundary_glyph_caption_key,
    _classify_boundary_glyph_phase,
    _profile_boundary_glyph_source,
    _boundary_glyph_protection,
    _index_boundary_glyph_events,
    _index_boundary_glyph_captions,
    _match_boundary_glyph_words,
    _fit_boundary_glyph_words,
    _collect_boundary_glyph_proposals,
    _resolve_boundary_glyph_ownership,
    match_boundary_glyph_effects,
)
from _simplify_ass.effect_validation import _parse_simple_source_fade
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
    text_height, placement_key, text_layout_key, compatible_text_layout, near_coincident_glyph_planes,
)
from _simplify_ass.text_freezing import (
    FrozenBlock, SAFE_SIMPLE_TAGS, _freeze_inputs, freeze_block, safe_override,
    simplify_text, simplify_visual_text,
)
from _simplify_ass.caption_clearance import (
    _caption_implicit_anchor, _glyph_replacement_row_is_clear, _caption_order_is_unchanged,
)
from _simplify_ass.caption_rendering import (
    MAX_PROVED_CAPTION_BORDER, CAPTION_PAINT_TAGS, SourceCaptionPaint, _source_caption_paint,
    render_simplified_caption, render_tag, render_caption_spans, render_merged_caption,
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

from _simplify_ass.caption_geometry import rectangle_clip

from _simplify_ass.sliced_text import (
    SlicedTextIndex, SlicedTextEvent, _eligible_sliced_text_families,
    _sliced_text_layout, _sliced_text_paint, _profile_sliced_text_event,
    _sliced_text_final_state, _index_sliced_text_pulse, _index_sliced_text_tile,
    _index_sliced_text_event, _prove_sliced_text_strip_phases, _propose_sliced_text_caption,
    _propose_sliced_text_replacements, _accept_sliced_text_ownership, _group_sliced_text_cues,
    _adjust_sliced_text_cue_timing, _adjust_authored_sliced_text_timing, collapse_sliced_text_sequences,
)

from _simplify_ass.text_visibility import TextVisibilityResult
from _simplify_ass.full_lyric_copies import collapse_full_lyric_copies
from _simplify_ass.progressive_reveals import (
    ProgressiveRevealPrefix,
    ProgressiveRevealBand,
    ProgressiveRevealCaption,
    _eligible_progressive_reveal_families,
    _parse_progressive_reveal_prefix,
    _profile_progressive_reveal_event,
    _index_progressive_reveal_families,
    _build_progressive_reveal_chains,
    _progressive_reveal_finishing_holds,
    _progressive_reveal_strip_band,
    _progressive_reveal_strips_cover_band,
    _progressive_reveal_strip_coverage,
    _select_progressive_reveal_caption,
    _progressive_reveal_intervals,
    _record_progressive_reveal_replacements,
    collapse_progressive_text_reveals,
)

from _simplify_ass.boundary_groups import nearby_boundary_groups
from _simplify_ass.shrinking_rows import (
    ShrinkingRowSource,
    ShrinkingRowIndex,
    ShrinkingRowProposal,
    _eligible_shrinking_row_families,
    _shrinking_row_geometry,
    _profile_shrinking_row_source,
    _index_shrinking_row_hold,
    _prove_shrinking_row_glyph,
    _index_shrinking_row_sources,
    _shrinking_row_owners,
    _adjust_shrinking_row_fade_handoffs,
    collapse_shrinking_glyph_rows,
)

__version__ = "2026.10.24.263"


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
    # Original planes plus accepted correspondence; never rewrite source layout.
    near_backing_planes: dict[frozenset[int],tuple[BackingFadePhase,str]] = field(default_factory=dict)


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
    _group_near_stacked_backings(context,events)
    _group_contained_stacked_paint(context,events)
    context.matched_backing_fades.update(_index_matched_backing_fades(context,events))
    context.glow_paint.update(_index_glow_pulse_paint(context))
    return context,echo_removed


def _stacked_backing_geometry(context: StackedTextContext, foreground: Event,
                              backing: Event) -> bool:
    profiles = [static_text_paint_geometry(e,context.paint) for e in (foreground,backing)]
    if any(p is None for p in profiles):
        return False
    if profiles[0][0] == profiles[1][0]:
        return True
    # A frozen pose cannot retrospectively prove original masked/moving geometry.
    # Retain uniform source layout and measure its working geometry handoff.
    sources = []
    tokens = []
    for e in (foreground,backing):
        source = (context.source_events or {}).get(e.source_index,e)
        evaluated = event_evaluation(source)
        source = dataclass_replace(source,state=evaluated.formatting,continuation=evaluated.continuation)
        source_tokens = event_override_tokens(source)
        if ((source.start,source.end) != (e.start,e.end) or
                OVERRIDE_RE.sub('',source.text) != OVERRIDE_RE.sub('',e.text) or
                inline_layout_key(source) or any(k in source.state for k in ('clip','iclip')) or
                any(tag == 'move' or tag == 't' and any(k not in context.paint
                    for k,v in tokenize_override(value[1:-1]))
                    for tag,value in source_tokens)):
            return False
        sources.append(source)
        tokens.append(source_tokens)
    if not (sources[0].state.get('1a',0) == sources[1].state.get('1a',0) == sources[1].state.get('3a',0)):
        return False
    if any(tag == 't' and any(k in {'alpha','1a','3a'} for k,v in tokenize_override(value[1:-1]))
           for stream in tokens for tag,value in stream):
        settled = [_settled_stacked_contour_source(source) for source in sources]
        if any(p is None for p in settled) or settled[0][1] != settled[1][1]:
            return False
    if any(tag in {'fad','fade'} for stream in tokens for tag,value in stream):
        fades = [_parse_simple_source_fade(stream) for stream in tokens]
        if any(f is None for f in fades) or fades[0] != fades[1]:
            return False
    # The freezer serializes positions with bounded decimal precision. Prove
    # both original correspondence and its working handoff instead of demanding
    # identical spelling or trusting a rounded replacement as new source proof.
    return (near_coincident_glyph_planes(foreground,backing,context.font_metrics) and
            near_coincident_glyph_planes(*sources,context.font_metrics) and
            all(near_coincident_glyph_planes(e,source,context.font_metrics)
                for e,source in zip((foreground,backing),sources)))


def _stacked_backing_output_layer(phase: BackingFadePhase, events: list[Event],
                                  context: StackedTextContext) -> str | None:
    """Keep original foreground order at the retained slot, or prove clearance."""
    family = [phase.foreground,phase.backing]
    members = {e.source_index for e in family}
    order = {e.source_index:(int(e.layer),i) if e.layer.lstrip('-').isdigit() else None
             for i,e in enumerate(events)}
    slot = min(order[e.source_index][1] for e in family)
    core = phase.foreground.start_s,phase.foreground.end_s
    peers = [e for e in events if e.kind == 'Dialogue' and e.source_index not in members and
             e.start_s < core[1] and e.end_s > core[0]]
    for layer in dict.fromkeys(('0',phase.foreground.layer)):
        rank = int(layer),slot
        probe = dataclass_replace(phase.foreground,layer=layer)
        if all(_caption_order_is_unchanged(family,e,order,rank) or
               context.font_metrics is not None and _glyph_replacement_row_is_clear(
                   dataclass_replace(probe,layer=e.layer),core,members,
                   int(e.layer) if e.layer.lstrip('-').isdigit() else int(layer),
                   {e.source_index:e},context.font_metrics,family)
               for e in peers):
            return layer
    return None


def _group_near_stacked_backings(context: StackedTextContext, events: list[Event]) -> None:
    """Join uniquely corresponding same-interval planes before frame reduction."""
    if context.font_metrics is None:
        return
    buckets = {}
    for key,group in context.groups.items():
        buckets.setdefault(key[:7]+key[8:],[]).append((key,group))
    for entries in buckets.values():
        peers = [e for _,group in entries for e in group]
        if len(peers) != 2 or (get_pos(peers[0].text) == get_pos(peers[1].text) and
                             text_layout_key(peers[0]) == text_layout_key(peers[1])):
            continue
        phase = _matched_backing_fade_phase(context,peers)
        if phase is None:
            continue
        layer = _stacked_backing_output_layer(phase,events,context)
        if layer is None:
            continue
        for key,_ in entries:
            del context.groups[key]
        key = entries[0][0]
        context.groups[key] = peers
        context.near_backing_planes[frozenset(e.source_index for e in peers)] = phase,layer


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
    if not _stacked_backing_geometry(context,foreground,backing):
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
        # Geometry correspondence is already proved. This is a paint-only view
        # for the canonical contour policy, not a replacement source/event pose.
        proof=_source_caption_paint(front,[front,{**back,'frz':front.get('frz',0)}])
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
    near = context.near_backing_planes.get(frozenset(e.source_index for e in group))
    if near is not None:
        phase,layer = near
        if phase.alpha != 0:
            return group,0,None  # Only the shared fade-family proof can remove these.
        chosen = phase.foreground
        text = render_simplified_caption(chosen.state,OVERRIDE_RE.sub('',chosen.text),
            measurement=chosen.measurement,source_paint=phase.paint[0])
        caption = replace_event(chosen,text=text,layer=layer,effect='',
            source_index=min(e.source_index for e in group))
        return [_preserve_frame_pose_support(chosen,caption)],1,None
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
            simplified_events, visible_map, font_metrics=font_metrics)
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
