"""Borrowed fixed-boundary queries over authored phase groups."""
from bisect import bisect_left, bisect_right


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
