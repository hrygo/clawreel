"""阶段4：后期处理 - 字幕、封面、AIGC标识.

字幕: Whisper 提取 + FFmpeg burn-in
封面: image-01 生成 3 张，关键内容偏上
AIGC标识: 添加"内容由AI生成"声明
"""
import logging
import shutil
import subprocess
from pathlib import Path

from .config import COVER_FULL, COVER_VISIBLE, OUTPUT_DIR

logger = logging.getLogger(__name__)


def _run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """执行命令."""
    logger.debug("CMD: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result


def _extract_subtitles_whisper(video_path: Path) -> Path | None:
    """用 Whisper 提取字幕，保存为 SRT.

    Returns:
        SRT 字幕文件路径，失败返回 None
    """
    srt_path = video_path.with_suffix(".srt")

    # 尝试使用 whisper CLI
    try:
        _run_cmd([
            "whisper",
            str(video_path),
            "--model", "base",
            "--language", "zh",
            "--output_format", "srt",
            "--output_dir", str(video_path.parent),
        ])
        if srt_path.exists():
            logger.info("✅ Whisper 字幕提取成功: %s", srt_path)
            return srt_path
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.warning("Whisper CLI 不可用，跳过字幕提取")
        return None

    return None


def _extract_subtitles_ffprobe(video_path: Path) -> Path | None:
    """用 FFmpeg 内置字幕提取（如果有硬字幕流）."""
    srt_path = video_path.with_suffix(".srt")
    try:
        _run_cmd([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-map", "0:s:0?",
            str(srt_path),
        ])
        if srt_path.exists() and srt_path.stat().st_size > 0:
            logger.info("✅ FFmpeg 字幕提取成功: %s", srt_path)
            return srt_path
    except subprocess.SubprocessError:
        pass
    return None


def _burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> Path:
    """将 SRT 字幕烧录进视频（burn-in）."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf",
        f"subtitles='{srt_path}':force_style='FontSize=24,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2'",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        str(output_path),
    ])
    logger.info("✅ 字幕烧录完成: %s", output_path)
    return output_path


def _add_aigc_watermark(video_path: Path, output_path: Path) -> Path:
    """添加 AIGC 水印标识.

    位置: 右下角
    文本: 内容由AI生成
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 使用 drawtext 添加文字水印
    # 注意：抖音平台要求标注 AI 生成内容
    _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf",
        "drawtext=text='内容由AI生成':fontsize=20:fontcolor=white:borderw=1:bordercolor=black:x=(w-text_w-10):y=(h-text_h-10)",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        str(output_path),
    ])
    logger.info("✅ AIGC水印添加完成: %s", output_path)
    return output_path


async def post_process(
    video_path: Path,
    title: str | None = None,
    add_subtitles: bool = True,
    add_aigc: bool = True,
    output_path: Path | None = None,
) -> Path:
    """后期处理主流程.

    Args:
        video_path: 输入视频路径
        title: 视频标题（未使用，保留向后兼容）
        add_subtitles: 是否添加字幕
        add_aigc: 是否添加 AIGC 标识

    Returns:
        处理后的视频路径
    """
    if output_path is None:
        output_path = OUTPUT_DIR / f"final_{video_path.name}"

    logger.info("🎨 开始后期处理: %s", video_path)

    current = video_path

    # 1. 字幕处理
    if add_subtitles:
        srt_path = (
            _extract_subtitles_whisper(video_path)
            or _extract_subtitles_ffprobe(video_path)
        )
        if srt_path:
            current = _burn_subtitles(current, srt_path, current.with_suffix("_subtitled.mp4"))

    # 2. AIGC 标识
    if add_aigc:
        # 水印写入独立临时文件，再复制到 output_path（避免 input==output 覆盖）
        aigc_temp = OUTPUT_DIR / f"_aigc_tmp_{video_path.stem}.mp4"
        _add_aigc_watermark(current, aigc_temp)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(aigc_temp), str(output_path))
        current = output_path
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, output_path)
        current = output_path

    # 清理字幕中间文件（如果存在）
    subtitled = video_path.with_suffix("_subtitled.mp4")
    if subtitled.exists():
        try:
            subtitled.unlink()
        except OSError:
            pass

    logger.info("✅ 后期处理完成: %s", output_path)
    return output_path
