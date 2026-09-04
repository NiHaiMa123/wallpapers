"""Shared ping-pong / mirror-playback arithmetic for H3 wallpaper loops.

Frame order is 0..N-1 then N-2..1, period 2N-2. That construction meets at
the loop boundary without duplicating the two turning frames. Writing
0..N-1 then N-1..0 would stall two frames at each turn.
"""

from __future__ import annotations


def playback_indices(frame_count: int, mode: str) -> list[int]:
    if frame_count < 2:
        raise ValueError("playback needs at least 2 frames")
    if mode == "linear":
        return list(range(frame_count))
    if mode == "mirror":
        return list(range(frame_count)) + list(range(frame_count - 2, 0, -1))
    raise ValueError(f"unknown loop mode: {mode!r}")


def encoded_length(frame_count: int, mode: str) -> int:
    return len(playback_indices(frame_count, mode))
