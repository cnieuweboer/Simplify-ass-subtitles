"""ASS transform evaluation with call-local sampling state.

Formatting, styles and transform descriptions are borrowed. Evaluation buffers
and ordered-sampler caches belong to the call; selection and event edits belong
to engine consumers. Interpreter records and tag semantics retain their owner.
"""
from __future__ import annotations

import math
import re
from typing import Iterable

from .ass_overrides import (
    OverrideContinuation, OverrideEvaluation, apply_font_size, apply_override,
)


def font_size_transform_needs_replay(changes: list) -> bool:
    """Relative, reset and repeated size tags depend on sampled state/order."""
    sizes = [value.strip() for name, value in changes if name == 'fs']
    if len(sizes) > 1:
        return True
    for value in sizes:
        if not value or value.startswith(('+', '-')):
            return True
        try:
            if float(value) <= 0:
                return True
        except ValueError:
            pass
    return False


def transform_weight(begin: float, end: float, accel: float, at: float) -> float:
    """Use the same timing and acceleration for every transform evaluator."""
    return 1.0 if end <= begin else min(1.0,max(0.0,(at-begin)/(end-begin))) ** accel


def interpolate_transform_value(key: str, start, finish, weight: float,
                                color_channels: dict | None = None):
    """Blend one field, preserving metadata, rounding and discrete-tag rules.

    The ordered sampler supplies a block-local colour decoding cache. The
    arithmetic and validation behavior are shared with single-time sampling.
    """
    if finish == start:
        return start
    if key.startswith('_'):
        return finish
    if isinstance(start,(int,float)) and isinstance(finish,(int,float)):
        return start+(finish-start)*weight
    if isinstance(start,tuple) and isinstance(finish,tuple):
        return tuple(a+(b-a)*weight for a,b in zip(start,finish))
    if key in {'1c','2c','3c','4c'}:
        if weight == 1 and color_channels is not None:
            # The ordered caller validates both colour strings before using
            # a cache. A completed blend is the target in canonical casing.
            return finish.upper()
        channels = []
        for color in (start,finish):
            decoded = color_channels.get(color) if color_channels is not None else None
            if decoded is None:
                decoded = tuple(int(color[i:i+2],16) for i in (0,2,4))
                if color_channels is not None:
                    color_channels[color] = decoded
            channels.append(decoded)
        return ''.join(f'{round(a+(b-a)*weight):02X}'
                       for a,b in zip(*channels))
    return finish if weight >= 1 else start


def _commit_transform_continuation(initial: OverrideContinuation,
                                   target: OverrideContinuation) -> OverrideContinuation:
    """Commit only the history fields the existing sampler already carried.

    A new target field did not enter an absent base dictionary slot. Existing
    history fields switched to their target as soon as a transform started,
    independently of its formatting interpolation weight. Preserve that
    policy outside rendered state.
    """
    reset = target.reset_style if initial.reset_style is not None else None
    alignment = target.alignment_set if initial.alignment_set is not None else None
    if reset == initial.reset_style and alignment == initial.alignment_set:
        return initial
    return OverrideContinuation(reset,alignment)


def sample_transform_state(base: dict, transforms: list, at: float,
                           styles: dict, default: dict, *,
                           continuation: OverrideContinuation = OverrideContinuation()
                           ) -> OverrideEvaluation:
    """Sample owned formatting and explicit history without modifying either seed."""
    state = base.copy()
    for begin, end, accel, changes in transforms:
        if at < begin or not changes:
            continue
        weight = transform_weight(begin,end,accel,at)
        if len(changes) == 1 and changes[0][0] in {'fr','frz','frx','fry'} and changes[0][1]:
            name,value = changes[0]
            key = 'frz' if name == 'fr' else name
            try: finish = float(value)
            except ValueError: continue
            start = state.get(key,finish)
            if finish != start:
                state[key] = interpolate_transform_value(key,start,finish,weight)
            continue
        target = state.copy()
        target_continuation = continuation
        replay_size = font_size_transform_needs_replay(changes)
        for name, value in changes:
            if name == 'fs' and replay_size:
                size_default = styles.get(target_continuation.reset_style or '',default)
                apply_font_size(target, value, size_default, weight)
            else:
                target_continuation = apply_override(target,name,value,styles,default,
                                                     target_continuation,event_tags=False)
        for key, finish in target.items():
            start = state.get(key, finish)
            if finish == start:
                continue
            state[key] = (finish if key == 'fs' and replay_size else
                          interpolate_transform_value(key,start,finish,weight))
        continuation = _commit_transform_continuation(continuation,target_continuation)
    return OverrideEvaluation(state,continuation)


def sample_transform_states(base: dict, transforms: list, times: Iterable[float],
                            styles: dict, default: dict, *,
                            continuation: OverrideContinuation = OverrideContinuation()
                            ) -> Iterable[OverrideEvaluation]:
    """Sample an ordered timeline, retaining completed independent updates.

    Constant paint/geometry tags affect independent state fields. Parse their
    targets once and advance each field's completed prefix as time increases.
    Overlapping or unsorted updates still replay in source order after that
    prefix. Resets, clipping and other context-dependent tags use the original
    evaluator, as do nonfinite inputs and unordered sample times.
    """
    times = list(times)
    simple = {'c','1c','2c','3c','4c','alpha','1a','2a','3a','4a',
              'fn','fs','fscx','fscy','fsp','b','i','u','s','fr','frz','frx','fry',
              'fax','fay','bord','xbord','ybord','shad','xshad','yshad',
              'blur','be','pos','org','p','pbo','q','fe'}
    if (any(not math.isfinite(t) for t in times) or
            any(b < a for a,b in zip(times,times[1:])) or
            any(not all(math.isfinite(v) for v in (a,b,accel)) or accel <= 0 or
                (any(name not in simple for name,_ in changes) or
                 font_size_transform_needs_replay(changes))
                for a,b,accel,changes in transforms)):
        for at in times:
            yield sample_transform_state(base,transforms,at,styles,default,continuation=continuation)
        return
    fields = {}
    targets = []
    for begin,end,accel,changes in transforms:
        target = {}
        target_continuation = OverrideContinuation(continuation.reset_style or '')
        for name,value in changes:
            target_continuation = apply_override(target,name,value,styles,default,
                                                 target_continuation,event_tags=False)
        for key,finish in target.items():
            targets.append((key,finish))
            # The original sampler leaves absent fields absent: their implicit
            # starting value equals the target, so no update is assigned.
            if key in base:
                fields.setdefault(key,[]).append((begin,end,accel,finish))
    colors = {'1c','2c','3c','4c'}
    values = [(key,base[key]) for key in fields]+targets
    if (any(isinstance(value,(int,float)) and not math.isfinite(value)
            for value in (*base.values(),continuation.alignment_set)) or any(
           (isinstance(value,(int,float)) and not math.isfinite(value)) or
           (isinstance(value,tuple) and any(not math.isfinite(v) for v in value)) or
           (key in colors and not re.fullmatch(r'[0-9A-Fa-f]{6}',str(value)))
           for key,value in values)):
        for at in times:
            yield sample_transform_state(base,transforms,at,styles,default,continuation=continuation)
        return
    color_channels = {}
    prefixes = {key:0 for key in fields}
    completed = {key:base[key] for key in fields}
    ordered = {key:all(a[0] <= b[0] for a,b in zip(updates,updates[1:]))
               for key,updates in fields.items()}
    for at in times:
        state = base.copy()
        for key,updates in fields.items():
            index = prefixes[key]
            value = completed[key]
            while index < len(updates):
                begin,end,accel,finish = updates[index]
                if at < max(begin,end):
                    break
                value = interpolate_transform_value(key,value,finish,1.0,color_channels)
                index += 1
            prefixes[key],completed[key] = index,value
            for offset in range(index,len(updates)):
                begin,end,accel,finish = updates[offset]
                if at < begin:
                    if ordered[key]:
                        break
                    continue
                weight = transform_weight(begin,end,accel,at)
                value = interpolate_transform_value(key,value,finish,weight,color_channels)
            state[key] = value
        yield OverrideEvaluation(state,continuation)
