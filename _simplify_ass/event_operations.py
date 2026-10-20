"""Resolved event reads and successor edits with their existing evidence contract."""
from __future__ import annotations

from dataclasses import replace as dataclass_replace

from .ass_overrides import (
    DEFAULT_STATE, OVERRIDE_RE, OverrideContinuation, OverrideEvaluation,
    evaluate_effective_state, resolve_event_style, tokenize_override,
)
from .caption_geometry import inline_layout_key
from .event_model import Event, EventEvidence

def event_evaluation(event: Event) -> OverrideEvaluation:
    """Borrow a resolved event cache, or evaluate source text without caching it.

    Cache owners install formatting and continuation together. An empty state
    is unresolved; its continuation cannot seed a fresh complete parse.
    """
    if event.state:
        return OverrideEvaluation(event.state,event.continuation)
    return evaluate_effective_state(event.text,event.defaults,event.styles)


def replace_event(event: Event, **changes) -> Event:
    """Synchronize formatting and explicitly preserve evidence only for a proven edit.

    Formatting/layout replacements clear historical source evidence unless
    the caller supplies it explicitly. Timing/layer edits may share immutable
    history; they do not establish new coverage, opacity or timing proof.
    Text/style edits recompute continuation from the complete replacement.
    Resolved paint/geometry edits retain continuation unless explicitly supplied;
    an empty state invalidates it. Measurement context is independently retained.
    """
    if "text" in changes or "style" in changes:
        style = changes.get("style", event.style)
        default = resolve_event_style(event.styles, style, event.defaults or DEFAULT_STATE)
        changes["defaults"] = default
        evaluated = evaluate_effective_state(changes.get("text", event.text),default,event.styles)
        changes["state"] = evaluated.formatting
        changes["continuation"] = evaluated.continuation
    elif "state" in changes and not changes["state"]:
        # Clearing the cache also clears its parsing history. Nonempty resolved
        # paint/geometry edits retain history unless a branch supplies its own.
        changes["continuation"] = OverrideContinuation()
    if ('evidence' not in changes and any(key in changes for key in
            ('text', 'style', 'state', 'defaults', 'styles',
             'margin_l', 'margin_r', 'margin_v', 'unit'))):
        changes['evidence'] = EventEvidence()
        if event.evidence.frame_pose_intervals is not None:
            successor = dataclass_replace(event,**changes)
            # Paint-only edits keep actual pose dwell. Other historical proofs
            # still expire, and changed layout/literal cannot inherit this one.
            if _frame_pose_key(event) == _frame_pose_key(successor):
                changes['evidence'] = EventEvidence(
                    frame_pose_intervals=event.evidence.frame_pose_intervals)
    successor = dataclass_replace(event, **changes)
    if ('evidence' not in changes and event.evidence.frame_pose_intervals is not None and
            _frame_pose_key(event) != _frame_pose_key(successor)):
        successor = dataclass_replace(successor,evidence=dataclass_replace(
            successor.evidence,frame_pose_intervals=None))
    return successor


def _frame_pose_key(e: Event) -> tuple:
    """Geometry/literal identity in the renderer's existing numeric precision."""
    tags = ('pos','org','fn','fs','an','b','i','u','s','fsp','fscx','fscy',
            'frz','frx','fry','fax','fay','p','pbo','q','clip','iclip','borderstyle','encoding')
    def numeric(value):
        if isinstance(value,(tuple,list)):
            return tuple(numeric(v) for v in value)
        return float(f'{value:g}') if isinstance(value,(int,float)) else value
    return (OVERRIDE_RE.sub('',e.text),e.measurement,e.unit,e.margin_l,e.margin_r,e.margin_v,
            inline_layout_key(e),
            tuple((k,numeric(e.state.get(k,DEFAULT_STATE.get(k)))) for k in tags))


def state_key(e: Event, omit: set[str] | None = None) -> tuple:
    """Compare resolved state; vector clip tuples also contain command strings."""
    omit = omit or set()
    return tuple(sorted((k,tuple(round(x,6) if isinstance(x,(int,float)) else x for x in v) if isinstance(v,tuple)
                         else round(v,6) if isinstance(v,(int,float)) else v)
                        for k,v in e.state.items() if k not in omit and not k.startswith("_")))


def event_override_tokens(e: Event) -> list[tuple[str,str]]:
    return [token for block in OVERRIDE_RE.findall(e.text)
            for token in tokenize_override(block)]
