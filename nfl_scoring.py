"""Shared NFL fantasy-scoring primitives used by every DFS format.

Keep base player scoring here. Lineup-slot multipliers such as DraftKings
Captain or FanDuel MVP belong in their format-specific lineup engines.
"""

from __future__ import annotations

from collections.abc import MutableMapping

TWO_POINT_CONVERSION_POINTS = 2.0


def apply_two_point_conversion(
    scores: MutableMapping[str, float],
    *,
    passer: str | None = None,
    receiver: str | None = None,
    rusher: str | None = None,
    successful: bool = True,
) -> MutableMapping[str, float]:
    """Credit a successful offensive NFL two-point conversion.

    A completed passing conversion awards two fantasy points to both the
    passer and receiver. A rushing conversion awards two points to the
    rusher. Failed conversions award nothing.

    This function intentionally has no platform or lineup-format argument:
    the base conversion scoring is shared by DraftKings and FanDuel in all
    supported NFL formats. Captain/MVP multipliers are applied later when a
    lineup is scored.
    """
    if not successful:
        return scores

    if passer and receiver:
        scores[passer] = float(scores.get(passer, 0.0)) + TWO_POINT_CONVERSION_POINTS
        scores[receiver] = float(scores.get(receiver, 0.0)) + TWO_POINT_CONVERSION_POINTS
        return scores

    if rusher:
        scores[rusher] = float(scores.get(rusher, 0.0)) + TWO_POINT_CONVERSION_POINTS

    return scores
