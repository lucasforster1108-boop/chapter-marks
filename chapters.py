#!/usr/bin/env python3
"""chapter-marks: auto-generate chapter markers for long videos that have none.

Two signal sources:
  1. Scene cuts, via ffmpeg's scene detection (select='gt(scene,T)').
  2. Long low-activity gaps in a companion .funscript file (optional).

Outputs an FFMETADATA chapter file, a chapters.json for tools like Stash,
and optionally a remuxed copy with the chapters embedded.

Only the Python standard library is used; ffmpeg/ffprobe do the heavy work.
"""

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------- ffprobe --

def get_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"ffprobe failed on {path}: {out.stderr.strip()}")
    return float(out.stdout.strip())


# --------------------------------------------------------- scene detection --

_PTS_TIME_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def detect_scenes(path: Path, threshold: float) -> list[float]:
    """Return timestamps (seconds) where ffmpeg's scene score passes T."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-an", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg scene detection failed: {proc.stderr.strip()[-500:]}")
    times = []
    for line in proc.stderr.splitlines():
        if "showinfo" in line:
            m = _PTS_TIME_RE.search(line)
            if m:
                times.append(float(m.group(1)))
    return sorted(times)


# ------------------------------------------------------------ funscript -----

def load_actions(path: Path) -> list[tuple[float, int]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    actions = [(a["at"] / 1000.0, int(a["pos"])) for a in data.get("actions", [])]
    actions.sort()
    return actions


def detect_gaps(actions: list[tuple[float, int]], duration: float,
                gap_seconds: float) -> list[float]:
    """Find chapter boundaries where script activity stays low for a while.

    Activity is bucketed per second (sum of |delta pos|). A bucket counts as
    "low" when it is under 20% of the median busy bucket. A run of low
    buckets at least `gap_seconds` long yields one boundary at its start.
    """
    if not actions or duration <= 0:
        return []
    n = int(math.ceil(duration))
    activity = [0.0] * n
    prev_pos = actions[0][1]
    for at, pos in actions:
        idx = min(int(at), n - 1)
        activity[idx] += abs(pos - prev_pos) + 1.0  # +1 so plain hits count too
        prev_pos = pos
    busy = sorted(a for a in activity if a > 0)
    if not busy:
        return []
    median_busy = busy[len(busy) // 2]
    low_cut = 0.2 * median_busy

    boundaries = []
    run_start = None
    for i, a in enumerate(activity):
        if a <= low_cut:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= gap_seconds:
                boundaries.append(float(run_start))
            run_start = None
    if run_start is not None and n - run_start >= gap_seconds:
        boundaries.append(float(run_start))
    # a boundary at 0 is meaningless (first chapter always starts at 0)
    return [b for b in boundaries if b > 0.5]


# -------------------------------------------------------------- chapters ----

def build_chapters(scene_times, gap_times, duration, min_length):
    """Merge both sources into [(start, source), ...] starting at 0."""
    points = [(0.0, "start")]
    for t in scene_times:
        points.append((t, "scene"))
    for t in gap_times:
        points.append((t, "gap"))
    points.sort(key=lambda p: p[0])

    # drop near-duplicates (within 1s), scene wins over gap
    merged: list[tuple[float, str]] = []
    for t, src in points:
        if merged and t - merged[-1][0] < 1.0:
            if merged[-1][1] == "gap" and src == "scene":
                merged[-1] = (merged[-1][0], "scene")
            continue
        merged.append((t, src))

    # enforce min chapter length: a too-short chapter is folded into the
    # previous one (its start point is dropped)
    kept = [merged[0]]
    for t, src in merged[1:]:
        if t - kept[-1][0] >= min_length:
            kept.append((t, src))
    # the trailing chapter must also satisfy min_length, unless it is the
    # only other chapter and dropping it would leave a single chapter:
    # keep the behaviour simple and predictable -- drop a too-short tail.
    if len(kept) > 1 and duration - kept[-1][0] < min_length:
        kept.pop()
    return kept


def fmt_timecode(sec: float) -> str:
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def write_ffmeta(chapters, duration, out_path: Path):
    lines = [";FFMETADATA1"]
    for i, (start, _src) in enumerate(chapters):
        end = chapters[i + 1][0] if i + 1 < len(chapters) else duration
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(round(start * 1000))}",
            f"END={int(round(end * 1000))}",
            f"title=Chapter {i + 1}",
        ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(chapters, out_path: Path):
    data = [
        {"title": f"Chapter {i + 1}", "start_time": round(start, 3)}
        for i, (start, _src) in enumerate(chapters)
    ]
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def embed_chapters(video: Path, ffmeta: Path, out_path: Path):
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-i", str(video), "-i", str(ffmeta),
        "-map", "0", "-map_metadata", "1", "-map_chapters", "1",
        "-codec", "copy", str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg embed failed: {proc.stderr.strip()[-500:]}")


# ------------------------------------------------------------------ main ----

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Auto-generate chapter markers for a long video.")
    ap.add_argument("video", type=Path)
    ap.add_argument("--script", type=Path, default=None,
                    help="funscript file for gap detection "
                         "(default: <video>.funscript next to the video)")
    ap.add_argument("--scene-threshold", type=float, default=0.4,
                    help="ffmpeg scene score threshold (default 0.4)")
    ap.add_argument("--min-length", type=float, default=60,
                    help="minimum chapter length in seconds (default 60)")
    ap.add_argument("--gap", type=float, default=45,
                    help="low-activity gap length in seconds that counts "
                         "as a chapter break (default 45)")
    ap.add_argument("-o", "--out-prefix", type=Path, default=None,
                    help="output prefix (default: video path without suffix)")
    ap.add_argument("--embed", action="store_true",
                    help="also remux a <name>_chapters.mkv with chapters "
                         "embedded (stream copy, original untouched)")
    args = ap.parse_args(argv)

    video = args.video
    if not video.is_file():
        sys.exit(f"no such file: {video}")
    prefix = args.out_prefix or video.with_suffix("")

    duration = get_duration(video)

    scene_times = detect_scenes(video, args.scene_threshold)

    script = args.script
    if script is None:
        candidate = video.with_suffix(".funscript")
        if candidate.is_file():
            script = candidate
    gap_times = []
    if script is not None:
        if not script.is_file():
            sys.exit(f"no such script file: {script}")
        gap_times = detect_gaps(load_actions(script), duration, args.gap)

    chapters = build_chapters(scene_times, gap_times, duration, args.min_length)

    ffmeta_path = prefix.with_suffix(".ffmeta")
    json_path = prefix.with_suffix(".chapters.json")
    write_ffmeta(chapters, duration, ffmeta_path)
    write_json(chapters, json_path)

    print(f"{video.name}: {len(chapters)} chapters "
          f"({len(scene_times)} scene cuts, {len(gap_times)} gap breaks)")
    for i, (start, src) in enumerate(chapters):
        print(f"  {i + 1:>2}. {fmt_timecode(start)}  Chapter {i + 1}  [{src}]")
    print(f"wrote {ffmeta_path}")
    print(f"wrote {json_path}")

    if args.embed:
        out_video = prefix.with_name(prefix.name + "_chapters.mkv")
        embed_chapters(video, ffmeta_path, out_video)
        print(f"wrote {out_video}")


if __name__ == "__main__":
    main()
