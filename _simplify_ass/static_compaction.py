"""Event-level override compaction before and after final source proofs.

Callers retain stage order, configuration and evidence-lifetime boundaries.
Both modes borrow event/document inputs and keep serialization buffers local;
final mode preserves source evidence only after complete-span equivalence proof.
"""
from __future__ import annotations

import math
import re

from .ass_overrides import (
    DEFAULT_STATE, TAG_RE, OverrideContinuation, apply_override,
    resolve_event_style, tokenize_override,
)
from .event_model import Event
from .event_operations import replace_event
from .static_objects import StaticSpanSignature, static_object_key
from .static_selection import unrotated_text_state
from .text_freezing import simplify_visual_text


def _finished_static_key(event: Event) -> tuple | None:
    """Literal formatting/history proof for final serialization, without effects.

    Zero blur and axes equal to their uniform value have the same renderer
    meaning as implicit defaults. Preserve all other values and continuation.
    """
    key = static_object_key(event, event.styles, allow_unpositioned=True)
    if key is None:
        return None
    runs = []
    for signature, drawing, payload in key[-1]:
        state = dict(signature.formatting)
        for tag in ('blur', 'be'):
            if state.get(tag) == 0:
                state.pop(tag)
        for uniform in ('bord', 'shad'):
            for axis in 'xy':
                tag = axis + uniform
                if tag in state and state[tag] == state.get(uniform, 0):
                    state.pop(tag)
        span = StaticSpanSignature(tuple(sorted(state.items())), signature.continuation)
        if runs and runs[-1][:2] == (span, drawing):
            runs[-1] = (span, drawing, runs[-1][2] + payload)
        else:
            runs.append((span, drawing, payload))
    return key[:-1] + (tuple(runs),)


def _join_finished_static_headers(text: str) -> str | None:
    """Combine adjacent recognized headers, keeping unknown syntax/comments intact."""
    parts = []
    for part in re.split(r'(\{[^}]*\})', text):
        if not part:
            continue
        if part.startswith('{') and part.endswith('}'):
            block = part[1:-1]
            tokens, matches = tokenize_override(block), list(TAG_RE.finditer(block))
            # Account for every byte of tag syntax. The resolver cannot prove
            # renderer semantics for unsupported tags or inline annotations.
            if (len(tokens) != len(matches) or (not matches and block.strip()) or
                    (matches and block[:matches[0].start()].strip())):
                return None
            for index, (name, value) in enumerate(tokens):
                end = matches[index+1].start() if index+1 < len(matches) else len(block)
                if (matches[index].group(1).lower() != name or
                        block[matches[index].end():end].strip() != value):
                    return None
            if parts and parts[-1].startswith('{') and parts[-1].endswith('}'):
                parts[-1] = parts[-1][:-1] + part[1:]
            else:
                parts.append(part)
        else:
            parts.append(part)
    return ''.join(parts)


def compact_static_overrides(events: list[Event], max_blur: float, *, final: bool = False) -> list[Event]:
    """Serialize finished captions relative to their style and preceding spans.

    Reuse the normal override resolver after effect recognition has finished.
    Blur/edge blur default to zero even though ASS styles have no such fields.
    Keep drawing payloads, inline formatting, resets and comments intact.
    """
    output = []
    for e in events:
        if e.kind == "Dialogue":
            source_text = e.text
            if final:
                proof = _finished_static_key(e)
                source_text = _join_finished_static_headers(e.text) if proof is not None else None
                if source_text is None:
                    output.append(e)
                    continue
            defaults = {**resolve_event_style(e.styles, e.style, e.defaults or DEFAULT_STATE),
                        "blur":0.0, "be":0.0}
            text, _, _ = simplify_visual_text(
                source_text,math.inf if final else max_blur,e.duration,defaults,e.styles,2)
            if not final and re.search(r'\\org\(',text):
                # Keep origins through source-effect proofs: they distinguish
                # independently generated copies. At this late stage an origin
                # has no rendered effect when every span is unrotated.
                state = defaults.copy()
                continuation = OverrideContinuation()
                upright = True
                for part in re.split(r'(\{[^}]*\})',text):
                    if part.startswith('{'):
                        for tag,value in tokenize_override(part[1:-1]):
                            continuation = apply_override(state,tag,value,e.styles,defaults,continuation)
                    elif part and not unrotated_text_state(state):
                        upright = False
                        break
                if upright:
                    text = re.sub(r'\\org\([^)]*\)','',text)
            if text != e.text and (not final or len(text) < len(e.text)):
                candidate = replace_event(e, text=text, **({'evidence': e.evidence} if final else {}))
                if not final or _finished_static_key(candidate) == proof:
                    e = candidate
        output.append(e)
    return output
