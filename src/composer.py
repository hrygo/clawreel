"""阶段3：音视频合成 - 使用 FFmpeg 合成最终视频.

流程: HOOK(6s) + BODY(图片序列+TTS) + CTA(6s)
音频: AAC-LC / 44100 Hz / 128-192 kbps
输出: assets/composed.mp4
"""
import logging
import math
from pathlib import Path
from typing import Sequence

from .config import (
    ASSETS_DIR,
    AUDIO_BIT_RATE,
    AUDIO_SAMPLE_RATE,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from .utils import run_ffmpeg, get_media_duration

logger = logging.getLogger(__name__)


async def compose(
    tts_path: Path,
    image_paths: Sequence[Path],
    music_path: Path,
    hook_video_path: Path | None = None,
    cta_video_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """音视频合成.

    Args:
        tts_path: TTS 音频文件路径
        image_paths: 图片路径序列（按顺序展示）
        music_path: 背景音乐路径
        hook_video_path: HOOK 视频路径（可选）
        cta_video_path: CTA 视频路径（可选）
        output_path: 输出路径，默认 assets/composed.mp4

    Returns:
        合成后的视频路径
    """
    if output_path is None:
        output_path = ASSETS_DIR / "composed.mp4"

    # 获取各段时长
    tts_duration = get_media_duration(tts_path)
    music_duration = get_media_duration(music_path)

    logger.info(
        "🎞️ 开始合成视频，音频%.1fs，图片%d张，音乐%.1fs",
        tts_duration, len(image_paths), music_duration
    )

    # 如果音乐比 TTS 短，循环音乐
    if 0 < music_duration < tts_duration:
        loop_count = math.ceil(tts_duration / music_duration)
        extended_music = ASSETS_DIR / "music_extended.mp3"
        run_ffmpeg([
            "ffmpeg", "-y",
            "-stream_loop", str(loop_count - 1),
            "-i", str(music_path),
            "-t", str(tts_duration),
            "-c", "copy",
            str(extended_music),
        ])
        music_path = extended_music

    # 构建合成命令
    # 策略：用 tts 音频长度决定总时长，每张图片平均分配展示时间
    num_images = len(image_paths)
    if num_images == 0:
        raise ValueError("至少需要一张图片")

    img_duration = tts_duration / num_images

    # 创建图片序列（每张图片转为视频片段）
    concat_list = ASSETS_DIR / "concat_list.txt"
    with open(concat_list, "w") as f:
        for i, img_path in enumerate(image_paths):
            img_video = ASSETS_DIR / f"img_{i:03d}.mp4"
            run_ffmpeg([
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(img_path),
                "-t", str(img_duration),
                "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
                "-r", str(VIDEO_FPS),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-an",
                str(img_video),
            ])
            f.write(f"file '{img_video.name}'\n")

    # 合并图片视频片段
    body_video = ASSETS_DIR / "body_video.mp4"
    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(body_video),
    ])

    # 合并 HOOK + BODY + CTA
    segments: list[Path] = []
    if hook_video_path:
        segments.append(hook_video_path)
    segments.append(body_video)
    if cta_video_path:
        segments.append(cta_video_path)

    if len(segments) > 1:
        seg_list = ASSETS_DIR / "segments.txt"
        with open(seg_list, "w") as f:
            for seg in segments:
                f.write(f"file '{seg.absolute()}'\n")
        video_only = ASSETS_DIR / "video_no_audio.mp4"
        run_ffmpeg([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(seg_list),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(video_only),
        ])
    else:
        video_only = segments[0]

    # 混合 TTS + 背景音乐，输出最终视频
    # 音乐输入音量降至 0.35，避免与 TTS 混音后被压制到几乎听不见
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(video_only),
        "-i", str(tts_path),
        "-i", str(music_path),
        "-filter_complex",
        "[1:a][2:a]volume=0.35,amix=inputs=2:duration=first:dropout_transition=2,"
        "aresample={sample_rate},aformat=sample_fmts=fltp:sample_rates={sample_rate}".format(
            sample_rate=AUDIO_SAMPLE_RATE
        ),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-b:v", "6M",
        "-c:a", "aac",
        "-b:a", str(AUDIO_BIT_RATE),
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-pix_fmt", "yuv420p",
        "-t", str(tts_duration),
        str(output_path),
    ])

    logger.info("✅ 视频合成完成: %s", output_path)

    # 清理中间文件
    for pattern in [
        "img_*.mp4", "body_video.mp4", "video_no_audio.mp4",
        "music_extended.mp3", "concat_list.txt", "segments.txt",
    ]:
        for f in ASSETS_DIR.glob(pattern):
            try:
                f.unlink()
            except OSError:
                pass

    return output_path
