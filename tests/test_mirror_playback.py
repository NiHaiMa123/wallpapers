from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
MODULE_FILE = PROJECT / "scripts" / "loop_common.py"
spec = importlib.util.spec_from_file_location("loop_common", MODULE_FILE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

playback_indices = module.playback_indices
encoded_length = module.encoded_length


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: {actual!r} != {expected!r}")


assert_equal(playback_indices(2, "linear"), [0, 1], "linear n=2")
assert_equal(playback_indices(2, "mirror"), [0, 1], "mirror n=2")
assert_equal(playback_indices(3, "mirror"), [0, 1, 2, 1], "mirror n=3")
assert_equal(playback_indices(5, "mirror"), [0, 1, 2, 3, 4, 3, 2, 1], "mirror n=5")

mirror73 = playback_indices(73, "mirror")
assert_equal(len(mirror73), 144, "73-frame mirror period")
assert_equal(encoded_length(73, "mirror"), 144, "encoded_length 73")
assert_equal(mirror73[:4], [0, 1, 2, 3], "73 head")
assert_equal(mirror73[71:76], [71, 72, 71, 70, 69], "73 turning point")
assert_equal(mirror73[-3:], [3, 2, 1], "73 tail must not include frame 0")
assert_equal(mirror73[0], 0, "loop start is rest pose")
# Adjacent pairs at both turning points are the same source step, not a duplicated frame.
assert_equal(mirror73[71], 71, "pre-turn")
assert_equal(mirror73[72], 72, "turn")
assert_equal(mirror73[73], 71, "post-turn")
assert 0 not in mirror73[1:], "frame 0 appears only once, at the start"

try:
    playback_indices(1, "mirror")
except ValueError:
    pass
else:
    raise AssertionError("n=1 should be rejected")

try:
    playback_indices(5, "pingpong")
except ValueError:
    pass
else:
    raise AssertionError("unknown mode should be rejected")

print("PASS: mirror playback indices are 0..N-1 then N-2..1")
