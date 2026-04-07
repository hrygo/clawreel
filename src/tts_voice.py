"""阶段1：TTS配音 — 使用统一 api_client。

采样率使用 config.AUDIO_SAMPLE_RATE（44100 Hz）。
"""
import logging
from pathlib import Path

import edge_tts

from .api_client import api_post
from .config import ASSETS_DIR, AUDIO_SAMPLE_RATE, TTS_PROVIDER, TTS_CONFIG
from .utils import get_media_duration, save_hex_audio, check_base_resp

logger = logging.getLogger(__name__)


async def generate_voice(
    text: str,
    output_path: Path | None = None,
    voice_id: str | None = None,
    provider: str | None = None,
) -> Path:
    """生成 TTS 音频（支持 MiniMax 和 Edge）。"""
    if output_path is None:
        output_path = ASSETS_DIR / "tts_output.mp3"
    
    if provider is None:
        provider = TTS_PROVIDER

    provider_config = TTS_CONFIG.get("providers", {}).get(provider, {})
    default_voice = provider_config.get("voice_id")

    if provider == "edge":
        path = await _generate_edge_voice(text, output_path, voice_id or default_voice)
    else:
        path = await _generate_minimax_voice(text, output_path, voice_id or default_voice)
    
    duration = get_media_duration(path)
    logger.info("✅ TTS 生成完成: %s (%.1f 秒)", path, duration)
    return path


async def _generate_edge_voice(
    text: str,
    output_path: Path,
    voice_id: str,
) -> Path:
    """使用 Edge TTS 生成音频。"""
    logger.info("🎙️ 正在生成 Edge TTS，音色: %s, 文本长度: %d", voice_id, len(text))
    
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(output_path)
    return output_path


async def _generate_minimax_voice(
    text: str,
    output_path: Path,
    voice_id: str,
) -> Path:
    """使用 MiniMax 生成 TTS 音频。"""
    logger.info("🎙️ 正在生成 MiniMax TTS，音色: %s, 文本长度: %d", voice_id, len(text))
    
    provider_config = TTS_CONFIG.get("providers", {}).get("minimax", {})

    result = await api_post(
        endpoint="/t2a_v2",
        payload={
            "model": "speech-2.8-hd",
            "text": text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": provider_config.get("speed", 1.0),
                "vol": provider_config.get("vol", 1.0),
                "pitch": provider_config.get("pitch", 0),
                "emotion": provider_config.get("emotion", "happy"),
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

    return save_hex_audio(audio_hex, output_path)
