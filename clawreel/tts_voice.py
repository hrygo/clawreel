"""Phase 4: TTS配音 — 使用统一 api_client。

采样率使用 config.AUDIO_SAMPLE_RATE（44100 Hz）。
字幕: 由 segment_aligner 基于逐词时间戳生成句级 SRT，每句一行。
时间戳: Edge TTS 逐词时间戳（~50ms 精度），驱动语义分段。

策略: Edge TTS 优先，指数回避重试 3 次；全部失败则降级 MiniMax TTS
（MiniMax 无逐词时间戳，SRT 使用估算时长近似分割）。
"""
import logging
import asyncio
from pathlib import Path
from typing import TypedDict, Optional, List, Dict, Any, Tuple, Union

import edge_tts

from .api_client import api_post
from .config import ASSETS_DIR, AUDIO_SAMPLE_RATE, TTS_PROVIDER, TTS_CONFIG
from .segment_aligner import align_segments
from .utils import (
    WordTimestamp,
    format_srt_timestamp,
    get_media_duration,
    save_hex_audio,
    check_base_resp,
    segments_to_srt,
)

logger = logging.getLogger(__name__)


# ── 类型定义 ────────────────────────────────────────────────────────────────

class TTSResult(TypedDict):
    """TTS 合成的完整结果（含词级时间轴）。"""
    audio_path: Path
    srt_path: Optional[Path]
    word_timestamps: List[WordTimestamp]
    duration_sec: float


# ── 公开 API ────────────────────────────────────────────────────────────────

async def generate_voice(
    text: str,
    output_path: Optional[Path] = None,
    voice_id: Optional[str] = None,
    provider: Optional[str] = None,
    srt_path: Optional[Path] = None,
) -> TTSResult:
    """生成 TTS 音频。

    策略：Edge TTS 优先（指数回避 3 次重试），失败后降级 MiniMax TTS。
    Edge TTS 提供逐词时间戳，可生成精准句级 SRT；
    MiniMax 无逐词时间戳，SRT 使用均匀时长估算（可能轻微不同步）。

    Args:
        text:        TTS 文本
        output_path: 音频输出路径，默认 assets/tts_output.mp3
        voice_id:    音色 ID，默认从 TTS_CONFIG 读取
        provider:    TTS 提供商，默认从 config 读取
        srt_path:    SRT 字幕输出路径，默认 assets/tts_output.srt

    Returns:
        TTSResult（含 audio_path、srt_path、word_timestamps）
    """
    if output_path is None:
        output_path = ASSETS_DIR / "tts_output.mp3"
    if srt_path is None:
        srt_path = output_path.with_suffix(".srt")

    if provider is None:
        provider = TTS_PROVIDER

    edge_config = TTS_CONFIG.get("providers", {}).get("edge", {})
    minimax_config = TTS_CONFIG.get("providers", {}).get("minimax", {})
    edge_voice = voice_id or edge_config.get("voice_id") or "zh-CN-XiaoxiaoNeural"
    minimax_voice = minimax_config.get("voice_id") or "female-shaonv"

    # ── Step 1: Edge TTS 始终优先尝试，指数回避重试 3 次 ─────────────────────
    # 注意：即使 TTS_PROVIDER = "minimax"，Edge 仍优先尝试（高质量 + 逐词时间戳）
    if provider == "edge" or provider not in ("minimax",):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await _generate_edge_voice(text, output_path, edge_voice, srt_path)
                duration = get_media_duration(result["audio_path"])
                logger.info("✅ Edge TTS 生成完成: %s (%.1f 秒)", result["audio_path"], duration)
                return result
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "⚠️ Edge TTS 第 %d 次失败 (%s)，%d 秒后重试…",
                        attempt + 1, type(e).__name__, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error("❌ Edge TTS 重试全部失败，降级 MiniMax TTS: %s", e)

    # ── Step 2: MiniMax TTS（无逐词时间戳）────────────────────────────────────
    result = await _generate_minimax_voice(
        text, output_path, minimax_voice, srt_path, minimax_config
    )
    duration = get_media_duration(result["audio_path"])
    logger.info("✅ MiniMax TTS 生成完成（降级模式）: %s (%.1f 秒)", result["audio_path"], duration)
    return result


# ── 内部实现 ────────────────────────────────────────────────────────────────

async def _generate_edge_voice(
    text: str,
    output_path: Path,
    voice_id: str,
    srt_path: Path,
) -> TTSResult:
    """使用 Edge TTS 生成音频，并从逐词时间戳生成句级 SRT。

    SRT 按句子分条目（每句一行），而非逐词，
    保证字幕烧录时屏幕显示的是完整短句。
    """
    logger.info("🎙️ 正在生成 Edge TTS，音色: %s, 文本长度: %d", voice_id, len(text))

    submaker = edge_tts.SubMaker()
    communicate = edge_tts.Communicate(text, voice_id, boundary="WordBoundary")
    word_chunks: List[dict] = []

    # 单次 stream() 循环同时收集音频 bytes 和 word boundary 元数据
    # 异常时主动关闭 connector，防止 aiohttp session/connector 泄漏
    try:
        with open(output_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)
                    word_chunks.append(chunk)
    except Exception:
        if communicate.connector is not None:
            await communicate.connector.close()
        raise

    # 逐词时间戳：从 WordBoundary chunk 直接提取
    # 注意：Edge TTS 返回的 offset 和 duration 单位是 100 纳秒 (ticks)，即 10^7/s
    word_timestamps: List[WordTimestamp] = []
    TICKS_PER_SEC = 10_000_000
    for w in word_chunks:
        offset_ticks = int(w.get("offset", 0))
        duration_ticks = int(w.get("duration", 0))
        word_timestamps.append(
            WordTimestamp(
                word=w.get("text", ""),
                start_sec=offset_ticks / TICKS_PER_SEC,
                end_sec=(offset_ticks + duration_ticks) / TICKS_PER_SEC,
                offset_ms=offset_ticks / 10_000,
            )
        )

    # 句级 SRT 生成交由调用者（cli.py）在对齐后统一处理，
    # 避免在此处进行不完整的二次分割/合并。
    logger.info("✅ Edge TTS 逐词数据收集完成: %d 个词", len(word_timestamps))

    return TTSResult(
        audio_path=output_path,
        srt_path=None,
        word_timestamps=word_timestamps,
    )


def _write_sentence_srt(segments: List[dict]) -> str:
    """将句级 segments 写入 SRT 文件。"""
    lines: List[str] = []
    for i, seg in enumerate(segments, start=1):
        start = format_srt_timestamp(seg["start_sec"])
        end = format_srt_timestamp(seg["end_sec"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


async def _generate_minimax_voice(
    text: str,
    output_path: Path,
    voice_id: str,
    srt_path: Path,
    config: dict,
) -> TTSResult:
    """使用 MiniMax 生成 TTS 音频（无逐词时间戳）。

    SRT 使用均匀时长估算：将总音频时长按句子数量均匀分配，
    精度略低于 Edge TTS，但足以支持字幕烧录。
    """
    logger.info("🎙️ 正在生成 MiniMax TTS（降级模式），音色: %s, 文本长度: %d", voice_id, len(text))

    result = await api_post(
        endpoint="/t2a_v2",
        payload={
            "model": "speech-2.8-hd",
            "text": text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": config.get("speed", 1.0),
                "vol": config.get("vol", 1.0),
                "pitch": config.get("pitch", 0),
                "emotion": config.get("emotion", "happy"),
            },
            "audio_setting": {
                "sample_rate": AUDIO_SAMPLE_RATE,
                "format": "mp3",
                "channel": 1,
            },
        },
    )

    check_base_resp(result, context="MiniMax TTS API")

    audio_hex = result.get("data", {}).get("audio")
    if not audio_hex:
        raise RuntimeError(f"MiniMax TTS API 返回无 audio_hex: {result}")

    audio_path = save_hex_audio(audio_hex, output_path)
    total_duration = get_media_duration(audio_path)

    # 均匀估算 SRT（按标点/换行切分句子）
    import re
    # 按句子结束符切分，保留分隔符以便还原
    parts = re.split(r'(?<=[。！？.!?])', text)
    sentences = [p.strip() for p in parts if p.strip()]
    if not sentences:
        sentences = [text]

    # 均匀分配总时长（首尾各留 0.2s 静音缓冲）
    gap = 0.2
    avail = total_duration - gap * (len(sentences) - 1) - 0.4
    per_sent = max(avail / len(sentences), 0.5)
    
    dummy_segments = []
    t = 0.2
    for i, sent in enumerate(sentences):
        start = t
        end = t + per_sent - gap
        t = end + gap
        dummy_segments.append({
            "start_sec": start,
            "end_sec": end,
            "text": sent
        })

    srt_content = segments_to_srt(dummy_segments)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    logger.info("✅ MiniMax SRT 估算完成（%d 句，均匀分配）: %s", len(sentences), srt_path)

    return TTSResult(
        audio_path=audio_path,
        srt_path=srt_path,
        word_timestamps=[],  # MiniMax 无逐词时间戳
    )
