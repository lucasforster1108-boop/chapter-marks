[English](README.md) | [简体中文](README_zh.md) | [日本語](README_ja.md) | [한국어](README_ko.md)

# chapter-marks

长片没章节，拖进度条全靠蒙，找个片段来回拖半天。我烦了，写了这个：它替你把视频过一遍，在画面真正换场的地方自动打上章节标记。

## 它干什么

章节分界点来自两路信号：

1. **场景切换**——用 ffmpeg 的场景检测（`select='gt(scene,…)'`）。画面硬切到完全不同的内容，那就是一章的分界。任何视频都能用。
2. **funscript 里的长空档**（可选）——如果视频旁边有同名的 `.funscript`，脚本里长时间几乎没动作的段落（默认 45 秒以上）也算一个分界点。镜头看不出来的换段，靠这个能补上。

两路合并之后，比 `--min-length` 还短的章节会被并进前一章，第一个章节永远从 0 开始。

输出三样东西：

- `<name>.ffmeta`——FFMETADATA 格式的章节文件，可以直接 remux 进 mkv/mp4
- `<name>.chapters.json`——每章 `title` + `start_time`，是 Stash 这类工具能导入的格式
- 控制台打印一份章节清单，每行标着 `[scene]` 还是 `[gap]`，让你知道这个分界是哪来的

加 `--embed` 还会多出一个 `<name>_chapters.mkv`，章节已经嵌好了——流复制不重编码，原文件一个字节都不动。

## 安装

Python 3.10+，外加 PATH 里有 `ffmpeg` 和 `ffprobe`。就这些——脚本只用标准库，没有任何东西要 pip 装（`requirements.txt` 放在那基本就是为了说明这件事）。

## 用法

```bash
# 基础用法：只靠场景切换
python chapters.py movie.mp4

# 同名的 movie.funscript 会被自动带上；
# 也可以手动指定
python chapters.py movie.mp4 --script movie.funscript

# 场景检测调灵敏点，章节最短允许 30 秒，
# 再把章节嵌进一个新的 mkv
python chapters.py movie.mp4 --scene-threshold 0.3 --min-length 30 --embed
```

输出长这样：

```
movie.mp4: 4 chapters (2 scene cuts, 1 gap breaks)
   1. 00:00:00  Chapter 1  [start]
   2. 00:00:20  Chapter 2  [gap]
   3. 00:00:30  Chapter 3  [scene]
   4. 00:01:00  Chapter 4  [scene]
```

## 参数

| 参数 | 默认 | 作用 |
|---|---|---|
| `--script` | 同名 `.funscript`（有的话） | 用来做空档检测的 funscript |
| `--scene-threshold` | `0.4` | 场景切换分数的门槛，越低越灵敏 |
| `--min-length` | `60` | 章节最短长度（秒），比这短的并入前一章 |
| `--gap` | `45` | 脚本低活动持续多少秒算一个分界点 |
| `-o`, `--out-prefix` | 视频路径去后缀 | `.ffmeta` / `.chapters.json` 输出到哪 |
| `--embed` | 关 | 额外 remux 出带章节的 `<name>_chapters.mkv` |

## 丑话说前面（局限性）

- **渐变转场检不出来。** 场景检测认的是突变，慢慢淡入淡出的镜头会从门槛下面滑过去。说到底只认硬切。
- **阈值要按片调。** 快剪混剪的片子 0.4 会切个不停；一个机位拍到底的谈话片可能一次都触发不了。跑一遍、看清单、调参数、再跑一遍——好在跑得快。
- **gap 模式全看脚本质量。** 脚本本身稀疏、自然停顿多的，会凭空造分界；脚本全程密集、没安静段的，一个空档也给不了你。输出里标 `[gap]` 就是让你自己判断。
- 章节名就只有 `Chapter N`。起名字是你自己的事——这工具只找接缝，不负责理解内容。

## 测试

`tests/run_tests.py` 会造一段 90 秒的合成视频：三段画面差异极大的片段硬拼，切点精确在 30 秒和 60 秒；再配一份 funscript，20 秒起有一段 55 秒的完全空白。然后把整条流水线验一遍，包括用 ffprobe 把嵌好的章节读回来。在我机器上检出的章节是 0 / 20 / 30 / 60 秒，分毫不差。测试全程不使用任何真实素材。

## 许可

MIT，见 [LICENSE](LICENSE)。
