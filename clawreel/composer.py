"""Phase 6: 音视频合成 — FFmpeg 多图转场合成。

流水线：按语义分段的精确时长合成。
每张图持续 segments[i].duration_sec 秒（来自 Edge TTS 逐词时间戳）。
转场: fade / slide_left / slide_right / zoom / none
"""
import asyncio
import logging
import math
from pathlib import Path
from typing import Optional, List, Dict, Union, Any, Tuple, Literal

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

logger = logging.getLogger(__name__)

TRANSITION_DURATION = 0.8  # 转场持续时间（秒）


async def compose_sequential(
    tts_path: Path,
    segments: List[dict],
    music_path: Path,
    output_path:Optional[Path] = None,
    transition: Literal["fade", "slide_left", "slide_right", "zoom", "none"] = "fade",
    hook_video_path: Optional[Path] = None,
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

    # 计算总时长：优先从物理音频文件读取，确保音画完全对齐（防止 segments JSON 时长不足）
    actual_audio_dur = get_media_duration(tts_path)
    total_start = segments[0]["start_sec"]
    total_end = segments[-1]["end_sec"]
    # 逻辑总时长取两者最大值，兜底防止片段被截断
    tts_duration = max(actual_audio_dur, total_end - total_start)
    
    # 如果音频明显长于 segments 总和，自动给最后一个段落延时
    seg_sum = sum(s["duration_sec"] for s in segments)
    if actual_audio_dur > seg_sum + 0.1:
        gap = actual_audio_dur - seg_sum
        logger.info("🕒 音频长于片段总和 (%.2fs)，补足最后一段时长", gap)
        segments[-1]["duration_sec"] += gap
        # 更新对齐算表
        segments[-1]["end_sec"] = actual_audio_dur

    num_images = len(segments)
    logger.info(
        "🎞️ 开始语义合成，TTS=%.1fs，segments=%d张，转场=%s",
        tts_duration, num_images, transition
    )

    # ── Step 1: 并发生成图片（每段一张，prompt 来自 segment） ───────────────
    image_dir = ASSETS_DIR / "images"  # ✅ 使用统一的 images 目录
    image_dir.mkdir(parents=True, exist_ok=True)

    async def generate_one_segment(i: int, seg: dict) ->Optional[Tuple[int, Path]]:
        """优先复用已有图片，避免重复生成。

        优先级：
        1. seg_{i:03d}_0.jpg（Phase 5 assets 命令生成）
        2. body_{i:03d}_0.jpg（composer 旧版本兼容）
        3. 生成新图片
        """
        # 1️⃣ 优先使用 Phase 5 生成的 seg 图片
        seg_img = image_dir / f"seg_{i:03d}_0.jpg"
        if seg_img.exists():
            logger.info("✅ 复用 Phase 5 图片: %s", seg_img.name)
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

    local_paths: List[tuple[int, Path]] = []
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
    if music_duration <= 0:
        logger.warning("⚠️ 背景音乐时长检测失败或为 0，将不进行循环拼接: %s", music_path)
        loop_count = 1
    else:
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

    clip_durations = [seg["duration_sec"] for seg in segments]
    xfade_durs = []
    
    if transition != "none":
        for i, dur in enumerate(clip_durations):
            if i < len(clip_durations) - 1:
                # Max transition is 0.5 * clip duration to avoid overlapping overlaps
                xfade_durs.append(min(TRANSITION_DURATION, dur * 0.45))
            else:
                xfade_durs.append(0.0)
    else:
        xfade_durs = [0.0] * len(clip_durations)

    async def make_clip(i: int, img_path: Path, seg: dict):
        clip_path = body_dir / f"clip_{i:03d}.mp4"
        
        # ── 特殊处理: Hook Video (片头视频) ──
        if i == 0 and hook_video_path and hook_video_path.exists():
            logger.info("🎬 使用外部片头视频覆盖第 1 段素材: %s", hook_video_path.name)
            # 缩放并转换片头视频以匹配全局参数
            await asyncio.to_thread(run_ffmpeg, [
                "ffmpeg", "-y",
                "-i", str(hook_video_path),
                "-t", str(seg["duration_sec"] + xfade_durs[i]),
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
            return clip_path

        # 延长片段时长，提前抵消之后 xfade 拼接带来的时间损耗！
        clip_duration = seg["duration_sec"] + xfade_durs[i]
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
        logger.debug("✅ 生成片段 %d/%d: %s (实际合成时长: %.3fs)", i + 1, len(segments), clip_path.name, clip_duration)
        return clip_path

    clip_tasks = [make_clip(i, image_paths[i], seg) for i, seg in enumerate(segments)]
    clip_paths = await asyncio.gather(*clip_tasks)
    clip_paths = list(clip_paths)

    # ── Step 4: FFmpeg 转场合成 BODY ────────────────────────────────────────
    body_video = ASSETS_DIR / "body_xfade.mp4"

    if transition == "none":
        _concat_clips(clip_paths, body_video)
    else:
        _xfade_clips(clip_paths, clip_durations, xfade_durs, body_video, transition)

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
    # ⚠️ 绝不清理 assets/images/（Phase 5 生成的图片，应保留复用）
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


def _xfade_clips(
    clip_paths: List[Path],
    clip_durations: List[float],
    xfade_durs: List[float],
    output: Path,
    transition: Literal["fade", "slide_left", "slide_right", "zoom", "none"],
) -> None:
    """多 clip 转场合成（使用内建 xfade）。通过 xfade_durs 补偿补偿叠加时间以防总长度缩减。"""
    n = len(clip_paths)
    if n <= 1:
        _concat_clips(clip_paths, output)
        return

    trans_map = {
        "fade": "fade",
        "slide_left": "slideleft",
        "slide_right": "slideright",
        "zoom": "fade",  # built-in xfade zoom doesn't exact match, map to fade or circlecrop/smoothleft. Using fade.
    }
    tf = trans_map.get(transition, "fade")

    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]

    filter_parts: List[str] = []
    
    # Cascade built-in xfade
    # v0 = clip 0
    # v1 = xfade(v0, clip 1, offset=d0)
    # v2 = xfade(v1, clip 2, offset=d0+d1)
    
    cumulative_durs = 0.0
    last_v = "0:v"
    
    for i in range(1, n):
        # The offset is the sum of pure conceptual durations of all preceding clips
        # Because we mathematical extended each clip by xfade_dur!
        cumulative_durs += clip_durations[i-1]
        xfade_overlap = xfade_durs[i-1]
        
        # built-in xfade
        current_out = f"v{i}"
        
        # When bridging, FFmpeg xfade filter is:
        # [last_v][i:v]xfade=transition=fade:duration=X:offset=Y[v{i}]
        filter_parts.append(
            f"[{last_v}][{i}:v]xfade=transition={tf}:duration={xfade_overlap:.3f}:offset={cumulative_durs:.3f}[{current_out}]"
        )
        last_v = current_out

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{last_v}]",
        *FFMPEG_VIDEO_OPTS,
        str(output),
    ]
    run_ffmpeg(cmd)


def _concat_clips(clip_paths: List[Path], output: Path) -> None:
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
