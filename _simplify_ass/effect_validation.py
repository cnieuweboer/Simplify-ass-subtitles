"""Strict source-effect timing validation; callers own effect-family admission."""
from __future__ import annotations

import math
from .ass_overrides import tokenize_override

# Subtracting cue timestamps can lose sub-nanosecond precision. This absolute
# allowance only absorbs arithmetic rounding; authored timing stays unchanged.
_ENDPOINT_ROUNDING_MS = 1e-6


def parse_effect_transform(value: str, duration: float,
                           allowed: set[str], *, allow_instant: bool = False,
                           allow_after_end: bool = False,
                           parsed_changes: list[tuple[str,str]] | None = None
                           ) -> tuple[float,float,list[tuple[str,str]]] | None:
    """Validate one transform used as evidence for an effect family.

    Resolve all four ASS timing forms, requiring forward finite timing and
    positive acceleration. Instant alpha handoffs can opt into equal endpoints.
    These proofs allow at most 50 ms of endpoint
    rounding; the general static freezer retains its more permissive parsing.
    Geometry-only paint proofs may allow transforms ending after the cue.
    Each matcher supplies the tags that its own effect can safely change.
    A caller that has already parsed this exact payload may lend its changes;
    all timing and allowed-tag checks still run, without modifying that list.
    """
    prefix,sep,tail = value[1:-1].partition('\\')
    try:
        args = [float(v.strip()) for v in prefix.rstrip(', ').split(',') if v.strip()]
    except ValueError:
        return None
    changes = tokenize_override('\\'+tail) if parsed_changes is None else parsed_changes
    begin,end = args[:2] if len(args) >= 2 else (0,1000*duration)
    if (not sep or len(args) > 3 or not all(math.isfinite(v) for v in args) or
            not 0 <= begin <= end or not allow_after_end and end > 1000*duration+50+_ENDPOINT_ROUNDING_MS or
            not allow_instant and begin == end or
            len(args) in (1,3) and args[-1] <= 0 or
            any(tag not in allowed for tag,value in changes)):
        return None
    return begin,end,changes


def parse_effect_move(value: str, duration: float, *,
                      endpoint_slack: float = 0) -> list[float] | None:
    """Validate an effect's original move, retaining its source coordinates."""
    try:
        nums = [float(v) for v in value.strip('()').split(',')]
    except ValueError:
        return None
    if (len(nums) not in (4,6) or not all(math.isfinite(v) for v in nums) or
            len(nums) == 6 and not 0 <= nums[4] < nums[5] <= 1000*duration+endpoint_slack+_ENDPOINT_ROUNDING_MS):
        return None
    return nums
