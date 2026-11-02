[English](README.md) | [简体中文](README_zh.md) | [日本語](README_ja.md) | [한국어](README_ko.md)

# chapter-marks

## In plain words first

Long adult videos almost never come with chapters. If you want to jump
to a specific part in the middle, all you can do is drag the progress
bar and guess — too far, not far enough, back and forth.

This tool watches the video for you, finds the natural break points on
its own, and stamps chapter markers there. It writes chapter files that
players and Stash (a library app made for exactly this kind of video)
can read. After that, your player shows a list of chapters — click one
and you jump straight to that part. No more scrubbing blind.

It finds the breaks by looking at two things:

1. **Where the picture changes scene.** One second it's this shot, the
   next it hard-cuts to something completely different — that's usually
   where one part ends and the next begins. Works on any video.
2. **Where the companion funscript goes quiet for a long stretch.**
   Some videos come with a same-named `.funscript` file — think of it
   as an instruction sheet for a remote-controlled electric toy: as the
   video plays, the toy moves along with it. If that instruction sheet
   has a long run (45+ seconds by default) with almost nothing
   happening, the action clearly paused there, so that counts as a
   break too. It catches segment changes the camera alone can't show.

## What it does

Both lists get merged, anything shorter than `--min-length` gets folded
into the previous chapter, and the first chapter always starts at 0.

You get three things out of it:

- `<name>.ffmeta` — a chapter file for players (FFMETADATA format),
  ready to tuck into an mkv/mp4
- `<name>.chapters.json` — a simple chapter list, just a `title` and a
  `start_time` per chapter, in the shape library tools like Stash import
- a printed list on the console, each line tagged `[scene]` or `[gap]`
  so you know where the break came from

With `--embed` it also writes `<name>_chapters.mkv` with the chapters
already inside — video and audio are copied as-is, no re-encoding, and
your original file is never touched.

## Install

Python 3.10+, plus `ffmpeg` and `ffprobe` on your PATH. That's it — the
script is standard library only, there's nothing to pip install
(`requirements.txt` exists mostly to say exactly that).

## Usage

```bash
# basic: scene cuts only
python chapters.py movie.mp4

# a same-named movie.funscript is picked up automatically;
# or point at one explicitly
python chapters.py movie.mp4 --script movie.funscript

# touchier scene detection, chapters may be as short as 30s,
# and embed the result into a new mkv
python chapters.py movie.mp4 --scene-threshold 0.3 --min-length 30 --embed
```

Example output:

```
movie.mp4: 4 chapters (2 scene cuts, 1 gap breaks)
   1. 00:00:00  Chapter 1  [start]
   2. 00:00:20  Chapter 2  [gap]
   3. 00:00:30  Chapter 3  [scene]
   4. 00:01:00  Chapter 4  [scene]
```

## Parameters

| Flag | Default | What it does |
|---|---|---|
| `--script` | `<video>.funscript` if present | funscript used for gap detection |
| `--scene-threshold` | `0.4` | scene score a cut must beat; lower = more sensitive |
| `--min-length` | `60` | minimum chapter length in seconds; shorter ones merge into the previous chapter |
| `--gap` | `45` | seconds of low script activity that count as a break |
| `-o`, `--out-prefix` | video path w/o suffix | where the `.ffmeta` / `.chapters.json` go |
| `--embed` | off | also remux `<name>_chapters.mkv` with chapters embedded |

## Honest limitations

- **Fades and dissolves don't register.** Scene detection keys on abrupt
  change; a slow crossfade slides right under the threshold. Hard cuts
  only, really.
- **The threshold needs tuning per video.** A flashy montage trips 0.4
  constantly; a static talking-head video may never trip it. Run, look
  at the list, adjust, re-run — it's fast.
- **Gap mode is only as good as the script.** A sparse script with long
  natural pauses will invent breaks; a dense script with no quiet
  stretch gives you nothing. The `[gap]` tag in the output exists so you
  can judge for yourself.
- Chapter titles are just `Chapter N`. Naming them is your job — this
  tool finds the seams, it doesn't watch the video for meaning.

## Tests

`tests/run_tests.py` builds a synthetic 90-second video from three
visually distinct segments with hard cuts at exactly 30s and 60s, plus a
funscript with a 55-second dead stretch starting at 20s, and checks the
whole pipeline, including reading embedded chapters back with ffprobe.
On my machine the detected chapters land on 0 / 20 / 30 / 60 seconds —
dead on. No real footage is used anywhere in the tests.

## License

MIT — see [LICENSE](LICENSE).
