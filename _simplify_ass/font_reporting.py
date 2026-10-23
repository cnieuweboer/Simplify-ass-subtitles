"""Caller-owned diagnostics shared by font-backed processing stages.

The caller chooses report lifetime. Producers retain diagnostic writes and
accepted-join commit sites; measurement resources belong to FontMetrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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

