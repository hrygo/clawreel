"""阶段 4.5：Whisper 字幕提取模块 — 将视频语音转为 SRT 字幕。

使用 OpenAI Whisper（medium/large 模型）进行语音识别，
输出标准 SRT 格式，支持时间戳和中文优化。
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, List, Dict, Union, Any, Tuple, Any

from .utils import format_srt_timestamp

logger = logging.getLogger(__name__)

# Whisper 模型大小 → 中文推荐用途
WHISPER_MODEL_RECOMMEND = {
    "tiny": "快速预览/测试",
    "base": "一般精度",
    "small": "良好精度（推荐非正式作品）",
    "medium": "高准确率（烧录字幕推荐）",
    "large": "最高准确率（专业作品）",
}

# 支持的语言（Whisper 支持的 ISO 代码）
WHISPER_LANGUAGES = {
    "auto": "自动检测",
    "zh": "中文",
    "en": "英文",
    "ja": "日文",
    "ko": "韩文",
    "yue": "粤语",
    "fr": "法文",
    "de": "德文",
    "es": "西班牙文",
    "ru": "俄文",
}


# Whisper 模型缓存（进程级，避免每次调用重新加载 1.5GB 模型）
_wmodel_cache: Dict[str, Any] = {}

# ThreadPoolExecutor 缓存（避免每次异步调用重建线程池）
_executor:Optional[ThreadPoolExecutor] = None


def extract_subtitles(
    video_path: Path,
    output_srt:Optional[Path] = None,
    model: str = "medium",
    language: str = "auto",
    word_timestamps: bool = False,
) ->Optional[Path]:
    """用 Whisper 从视频中提取字幕，保存为 SRT 文件。

    Args:
        video_path: 视频文件路径（支持 mp4/avi/mov 等 FFmpeg 支持的格式）
        output_srt: 输出 SRT 路径（默认与视频同目录，stem + .srt）
        model: Whisper 模型大小（default/medium/large/small/tiny）
        language: 语言代码（auto 自动检测，zh 中文，en 英文等）
        word_timestamps: 是否启用词级时间戳（精度更高但 SRT 较大）

    Returns:
        SRT 文件路径，失败返回 None
    """
    import whisper

    if output_srt is None:
        output_srt = video_path.with_suffix(".srt")

    model_name = model if model else "medium"

    # 模块级缓存：已加载模型直接复用，避免每次 5-15 秒重新加载
    if model_name not in _wmodel_cache:
        logger.info("🔊 Whisper 加载模型: %s", model_name)
        _wmodel_cache[model_name] = whisper.load_model(model_name)
    else:
        logger.debug("🔁 复用已缓存的 Whisper 模型: %s", model_name)

    try:
        wmodel = _wmodel_cache[model_name]
        logger.info("🎙️ 开始转写: %s", video_path)
        lang_arg = language if language and language != "auto" else None

        options = {}
        if lang_arg:
            options["language"] = lang_arg
        if word_timestamps:
            options["word_timestamps"] = True

        result = wmodel.transcribe(str(video_path), **options)

        # 生成 SRT
        from .utils import ensure_parent_dir
        ensure_parent_dir(output_srt)
        _write_srt(result["segments"], output_srt)

        logger.info("✅ Whisper 字幕提取成功: %s", output_srt)
        return output_srt

    except ImportError:
        logger.error("❌ Whisper 未安装，运行: pip install openai-whisper")
        return None
    except FileNotFoundError:
        logger.error("❌ Whisper CLI 未找到，运行: pip install openai-whisper")
        return None
    except Exception as e:
        logger.error("❌ Whisper 字幕提取失败: %s", e)
        return None


def _write_srt(segments: List[dict], output_path: Path) -> None:
    """将 Whisper 结果写入 SRT 文件。"""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            start = format_srt_timestamp(seg.get("start", 0))
            end = format_srt_timestamp(seg.get("end", 0))
            text = seg.get("text", "").strip()
            # SRT 索引
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n")
            f.write("\n")


async def extract_subtitles_async(
    video_path: Path,
    output_srt:Optional[Path] = None,
    model: str = "medium",
    language: str = "auto",
) ->Optional[Path]:
    """异步版字幕提取（不阻塞事件循环）。

    Whisper inference 本身是 CPU/GPU bound，在独立线程执行以避免阻塞。
    """
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor,
        lambda: extract_subtitles(video_path, output_srt, model, language),
    )
