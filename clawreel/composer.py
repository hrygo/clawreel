"""阶段3：音视频合成 — FFmpeg 多图转场合成。

流水线：按语义分段的精确时长合成。
每张图持续 segments[i].duration_sec 秒（来自 Edge TTS 逐词时间戳）。
转场: fade / slide_left / slide_right / zoom / none
"""
import asyncio
import logging
import math
from pathlib import Path
from typing import Literal

from .config import (
    ASSETS_DIR,
    AUDIO_BIT_RATE,
    AUDIO_SAMPLE_RATE,
    BG_MUSIC_VOLUME,
    FFMPEG_VIDEO_OPTS,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from .api_client import download_file
from .utils import run_ffmpeg, get_media_duration
from .image_generator import generate_image

logger = logging.getLogger(__name__)

TRANSITION_DURATION = 0.8  # 转场持续时间（秒）


async def compose_sequential(
    tts_path: Path,
    segments: list[dict],
    music_path: Path,
    output_path: Path | None = None,
    transition: Literal["fade", "slide_left", "slide_right", "zoom", "none"] = "fade",
) -> Path:
    """按语义分段精确合成视频。

    Args:
        tts_path:       TTS 音频文件路径
        segments:       ScriptSegment 列表（含精确 duration_sec，可能包含 hooks 段）
        music_path:     背景音乐路径
        output_path:    输出路径，默认 output/composed.mp4
        transition:     转场类型：fade / slide_left / slide_right / zoom / none

    Returns:
        合成视频路径

    Raises:
        ValueError: len(segments) < 2
    """
    if len(segments) < 2:
        raise ValueError(
            f"segments 数量不足：当前 {len(segments)}，至少需要 2 段才能合成转场视频。"
            "请确保脚本分句数量 >= 2。"
        )

    if output_path is None:
        output_path = Path("output/composed.mp4")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 计算总时长
    total_start = segments[0]["start_sec"]
    total_end = segments[-1]["end_sec"]
    tts_duration = total_end - total_start

    num_images = len(segments)
    logger.info(
        "🎞️ 开始语义合成，TTS=%.1fs，segments=%d张，转场=%s",
        tts_duration, num_images, transition
    )

    # ── Step 1: 并发生成图片（每段一张，prompt 来自 segment） ───────────────
    image_dir = ASSETS_DIR / "images"  # ✅ 使用统一的 images 目录
    image_dir.mkdir(parents=True, exist_ok=True)

    async def generate_one_segment(i: int, seg: dict) -> tuple[int, Path] | None:
        """优先复用已有图片，避免重复生成。

        优先级：
        1. seg_{i:03d}_0.jpg（Phase 3 assets 命令生成）
        2. body_{i:03d}_0.jpg（composer 旧版本兼容）
        3. 生成新图片
        """
        # 1️⃣ 优先使用 Phase 3 生成的 seg 图片
        seg_img = image_dir / f"seg_{i:03d}_0.jpg"
        if seg_img.exists():
            logger.info("✅ 复用 Phase 3 图片: %s", seg_img.name)
            return i, seg_img

        # 2️⃣ 降级到 body 图片（旧版本兼容）
        body_img = image_dir / f"body_{i:03d}_0.jpg"
        if body_img.exists():
            logger.info("✅ 复用已有图片: %s", body_img.name)
            return i, body_img

        # 3️⃣ 都没有才生成新图片
        try:
            logger.info("🖼️ 生成新图片 [%d]: %s", i, seg["image_prompt"][:50])
            img_path_out = await generate_image(
                prompt=seg["image_prompt"],
                output_filename=f"seg_{i:03d}",  # ✅ 统一使用 seg_ 命名
            )
            # generate_image 返回 list，取第一张
            if img_path_out:
                return i, img_path_out[0]
            return None
        except Exception as e:
            logger.error("❌ 图片生成失败 [%d]: %s", i, e)
            return None

    semaphore = asyncio.Semaphore(3)
    async def sem_gen(i, seg):
        async with semaphore:
            return await generate_one_segment(i, seg)

    tasks = [sem_gen(i, seg) for i, seg in enumerate(segments)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    local_paths: list[tuple[int, Path]] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("⚠️ 图片生成异常: %s", r)
        elif r is not None:
            local_paths.append(r)

    if len(local_paths) < 2:
        raise RuntimeError(
            f"有效图片不足 2 张（当前 {len(local_paths)} 张），无法合成转场视频"
        )

    # 按 index 排序（保持顺序）
    local_paths.sort(key=lambda x: x[0])
    image_paths = [p for _, p in local_paths]

    # ── Step 2: 扩展音乐 ─────────────────────────────────────────────────
    music_duration = get_media_duration(music_path)
    if music_duration < tts_duration:
        loop_count = math.ceil(tts_duration / music_duration)
        ext_music = ASSETS_DIR / "music_extended.mp3"
        run_ffmpeg([
            "ffmpeg", "-y",
            "-stream_loop", str(loop_count - 1),
            "-i", str(music_path),
            "-t", str(tts_duration),
            "-c", "copy",
            str(ext_music),
        ])
        music_path = ext_music

    # ── Step 3: 生成精确时长视频片段 ──────────────────────────────────────
    body_dir = ASSETS_DIR / "body_clips"
    body_dir.mkdir(parents=True, exist_ok=True)

    async def make_clip(i: int, img_path: Path, seg: dict):
        clip_path = body_dir / f"clip_{i:03d}.mp4"
        clip_duration = seg["duration_sec"]
        await asyncio.to_thread(run_ffmpeg, [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(img_path),
            "-t", str(clip_duration),
            "-vf", (
                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
                f":force_original_aspect_ratio=decrease"
                f",pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
                f":(ow-iw)/2:(oh-ih)/2:black,setsar=1"
            ),
            "-r", str(VIDEO_FPS),
            *FFMPEG_VIDEO_OPTS,
            "-an",
            str(clip_path),
        ])
        logger.debug("✅ 生成片段 %d/%d: %s (%.1fs)", i + 1, len(segments), clip_path.name, clip_duration)
        return clip_path

    clip_tasks = [make_clip(i, image_paths[i], seg) for i, seg in enumerate(segments)]
    clip_paths = await asyncio.gather(*clip_tasks)
    clip_paths = list(clip_paths)

    # ── Step 4: FFmpeg 转场合成 BODY ────────────────────────────────────────
    body_video = ASSETS_DIR / "body_xfade.mp4"

    if transition == "none":
        _concat_clips(clip_paths, body_video)
    else:
        clip_durations = [seg["duration_sec"] for seg in segments]
        _xfade_clips(clip_paths, clip_durations, body_video, transition)

    # ── Step 5: 混音（TTS + 背景音乐）─ 输出最终视频 ─────────────────────
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(body_video),
        "-i", str(tts_path),
        "-i", str(music_path),
        "-filter_complex",
        f"[2:a]volume={BG_MUSIC_VOLUME}[bg];"
        f"[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2,"
        f"aresample={AUDIO_SAMPLE_RATE},aformat=sample_fmts=fltp:sample_rates={AUDIO_SAMPLE_RATE}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-b:v", "6M",
        "-c:a", "aac",
        "-b:a", str(AUDIO_BIT_RATE),
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-t", str(tts_duration),
        str(output_path),
    ])

    logger.info("✅ 视频合成完成: %s", output_path)

    # ── Step 6: 清理中间文件 ──────────────────────────────────────────────
    # ⚠️ 只清理 compose 自身产生的临时文件（body_clips、body_xfade）
    # ⚠️ 绝不清理 assets/images/（Phase 3 生成的图片，应保留复用）
    for f in body_dir.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        body_dir.rmdir()
    except OSError:
        pass

    for pattern in [
        "body_xfade.mp4", "music_extended.mp3",
    ]:
        for f in ASSETS_DIR.glob(pattern):
            try:
                f.unlink()
            except OSError:
                pass

    return output_path


# ── 内部：转场滤镜 ─────────────────────────────────────────────────────────

def _xfade_clips(
    clip_paths: list[Path],
    clip_durations: list[float],
    output: Path,
    transition: Literal["fade", "slide_left", "slide_right", "zoom", "none"],
) -> None:
    """多 clip 转场合成。clip_durations 直接取自 segments，无 FFprobe 开销。"""
    n = len(clip_paths)
    per_image_duration = sum(clip_durations) / n

    xfade_dur = min(TRANSITION_DURATION, per_image_duration * 0.3)

    if transition == "fade":
        _xfade_fade(clip_paths, output, xfade_dur, per_image_duration)
    else:
        _xfade_overlay(clip_paths, output, transition, xfade_dur, per_image_duration)


def _xfade_fade(
    clip_paths: list[Path],
    output: Path,
    xfade_dur: float,
    per_image_duration: float,
) -> None:
    """fade 转场：每个 clip 首尾加 fade，用 concat 拼接。"""
    n = len(clip_paths)
    total_dur = n * per_image_duration - (n - 1) * xfade_dur

    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]

    filter_parts = []
    for i in range(n):
        if i == 0:
            filter_parts.append(
                f"[{i}:v]fade=t=out:st={per_image_duration - xfade_dur}"
                f":d={xfade_dur}[v{i}]"
            )
        elif i == n - 1:
            filter_parts.append(f"[{i}:v]fade=t=in:st=0:d={xfade_dur}[v{i}]")
        else:
            filter_parts.append(
                f"[{i}:v]"
                f"fade=t=in:st=0:d={xfade_dur},"
                f"fade=t=out:st={per_image_duration - xfade_dur}:d={xfade_dur}[v{i}]"
            )

    concat_labels = "+".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_labels}concat=n={n}:v=1:a=0[outv]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]",
        *FFMPEG_VIDEO_OPTS,
        "-t", str(total_dur),
        str(output),
    ]
    run_ffmpeg(cmd)


def _xfade_overlay(
    clip_paths: list[Path],
    output: Path,
    transition: Literal["slide_left", "slide_right", "zoom"],
    xfade_dur: float,
    per_image_duration: float,
) -> None:
    """slide_left / slide_right / zoom 转场：overlay 链式叠加。"""
    n = len(clip_paths)

    xfade_offset = [0.0] * n
    for i in range(1, n):
        xfade_offset[i] = (i - 1) * (per_image_duration - xfade_dur) + xfade_dur

    total_dur = xfade_offset[-1] + per_image_duration

    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]

    filter_parts: list[str] = []

    if transition == "slide_left":
        for i in range(1, n):
            offset = xfade_offset[i]
            end_t = offset + xfade_dur
            x_expr = f"W*(1-(t-{offset})/{xfade_dur})"
            filter_parts.append(
                f"[{i-1}:v][{i}:v]overlay=x={x_expr}:y=0:"
                f"enable='between(t\\,{offset}\\,{end_t})'[vo{i}]"
            )
        last = f"[vo{n-1}]"

    elif transition == "slide_right":
        for i in range(1, n):
            offset = xfade_offset[i]
            end_t = offset + xfade_dur
            x_expr = f"-W*(t-{offset})/{xfade_dur}"
            filter_parts.append(
                f"[{i-1}:v][{i}:v]overlay=x={x_expr}:y=0:"
                f"enable='between(t\\,{offset}\\,{end_t})'[vo{i}]"
            )
        last = f"[vo{n-1}]"

    elif transition == "zoom":
        for i in range(1, n):
            offset = xfade_offset[i]
            end_t = offset + xfade_dur
            zoom_filter = (
                f"zoompan=z='min(zoom+0.003,1.5)':x=iw/2-(iw/zoom/2):"
                f"y=ih/2-(ih/zoom/2):d=1:s={VIDEO_WIDTH}x{VIDEO_HEIGHT},"
                f"fade=t=out:st=0:d={xfade_dur}"
            )
            filter_parts.append(f"[{i-1}:v]{zoom_filter}[v{i-1}z]")
            filter_parts.append(f"[{i}:v]fade=t=in:st=0:d={xfade_dur}[v{i}f]")
            filter_parts.append(
                f"[v{i-1}z][v{i}f]overlay=0:0:"
                f"enable='between(t\\,{offset}\\,{end_t})'[vo{i}]"
            )
        last = f"[vo{n-1}]"

    else:
        _concat_clips(clip_paths, output)
        return

    filter_parts.append(f"{last}copy[outv]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]",
        *FFMPEG_VIDEO_OPTS,
        "-t", str(total_dur),
        str(output),
    ]
    run_ffmpeg(cmd)


def _concat_clips(clip_paths: list[Path], output: Path) -> None:
    """无转场，直接 concat 拼接。"""
    lst = ASSETS_DIR / "concat_list.txt"
    with open(lst, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.absolute()}'\n")
    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(lst),
        *FFMPEG_VIDEO_OPTS,
        str(output),
    ])
    try:
        lst.unlink()
    except OSError:
        pass
