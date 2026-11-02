#!/usr/bin/env python3
"""End-to-end tests for chapters.py using fully synthetic media.

Builds a 90s video out of three visually distinct 30s segments (hard cuts
at exactly 30s and 60s) and a funscript with a 55s dead stretch, then
checks that chapter-marks finds the cuts, finds the gap, and embeds
chapters that ffprobe can read back. No real footage is used.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA = Path(__file__).resolve().parent / "media"
MEDIA.mkdir(exist_ok=True)
VIDEO = MEDIA / "scene_test.mp4"
SCRIPT = MEDIA / "gap.funscript"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def make_video():
    if VIDEO.exists():
        return
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc2=duration=30:size=320x240:rate=10",
        "-f", "lavfi", "-i", "color=c=crimson:size=320x240:rate=10:duration=30",
        "-f", "lavfi", "-i", "smptebars=size=320x240:rate=10:duration=30",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0",
        "-pix_fmt", "yuv420p", str(VIDEO),
    ]
    p = run(cmd)
    assert p.returncode == 0, p.stderr[-800:]


def make_script():
    actions = []
    # busy 0-20s: an action every 250ms swinging the full range
    t = 0
    while t < 20_000:
        actions.append({"at": t, "pos": 0 if (t // 250) % 2 == 0 else 100})
        t += 250
    # dead stretch 20-75s: no actions at all (55s gap > 45s threshold)
    # busy again 75-90s
    t = 75_000
    while t < 90_000:
        actions.append({"at": t, "pos": 0 if (t // 250) % 2 == 0 else 100})
        t += 250
    SCRIPT.write_text(json.dumps(
        {"version": "1.0", "inverted": False, "range": 100,
         "actions": actions}), encoding="utf-8")


def chapters_json():
    return json.loads((MEDIA / "scene_test.chapters.json").read_text())


def test_scenes():
    p = run([sys.executable, str(ROOT / "chapters.py"), str(VIDEO),
             "--min-length", "10"])
    print(p.stdout)
    assert p.returncode == 0, p.stderr[-800:]
    starts = [c["start_time"] for c in chapters_json()]
    assert len(starts) == 3, f"expected 3 chapters, got {starts}"
    assert starts[0] == 0.0
    assert abs(starts[1] - 30) <= 2, f"cut 1 off: {starts[1]}"
    assert abs(starts[2] - 60) <= 2, f"cut 2 off: {starts[2]}"
    print("PASS scene cuts: chapters at", starts)


def test_gap_and_embed():
    p = run([sys.executable, str(ROOT / "chapters.py"), str(VIDEO),
             "--script", str(SCRIPT), "--min-length", "10", "--embed"])
    print(p.stdout)
    assert p.returncode == 0, p.stderr[-800:]
    assert "[gap]" in p.stdout, "no gap chapter reported"
    starts = [c["start_time"] for c in chapters_json()]
    assert any(abs(s - 20) <= 2 for s in starts), \
        f"no chapter near the 20s gap start: {starts}"

    embedded = MEDIA / "scene_test_chapters.mkv"
    assert embedded.exists(), "embedded mkv missing"
    p = run(["ffprobe", "-v", "error", "-show_chapters",
             "-of", "json", str(embedded)])
    assert p.returncode == 0, p.stderr[-800:]
    got = json.loads(p.stdout)["chapters"]
    assert len(got) == len(starts), \
        f"ffprobe read {len(got)} chapters, expected {len(starts)}"
    print(f"PASS gap break near 20s; ffprobe reads back {len(got)} "
          f"embedded chapters from {embedded.name}")


if __name__ == "__main__":
    make_video()
    make_script()
    test_scenes()
    test_gap_and_embed()
    print("ALL TESTS PASSED")
