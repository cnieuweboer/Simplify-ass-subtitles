"""Static text-paint normalization with bounded palettes and shadow transfer.

Inputs stay borrowed; palette, parser and serialization buffers stay local.
Callers retain evidence requirements, stage order and aggregate reporting.
"""
from __future__ import annotations

import math
import re

from .ass_overrides import OverrideContinuation, tokenize_override, apply_override
from .event_model import Event
from .event_operations import replace_event
from .static_objects import static_object_key
from .caption_geometry import inline_layout_key
from .caption_rendering import render_tag


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

