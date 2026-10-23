"""Literal matching at recorded fragment boundaries, without event ownership."""
from __future__ import annotations

from typing import Iterable


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
