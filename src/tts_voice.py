"""阶段1：TTS配音 — 使用统一 api_client。

采样率使用 config.AUDIO_SAMPLE_RATE（44100 Hz）。
"""
import logging
import binascii
import subprocess
from pathlib import Path

import edge_tts

from .api_client import api_post
from .config import ASSETS_DIR, AUDIO_SAMPLE_RATE, TTS_PROVIDER, TTS_VOICE

logger = logging.getLogger(__name__)

DEFAULT_MINIMAX_VOICE = "female-shaonv"


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

    if provider == "edge":
        return await _generate_edge_voice(text, output_path, voice_id or TTS_VOICE)
    else:
        return await _generate_minimax_voice(text, output_path, voice_id or DEFAULT_MINIMAX_VOICE)


async def _generate_edge_voice(
    text: str,
    output_path: Path,
    voice_id: str,
) -> Path:
    """使用 Edge TTS 生成音频。"""
    logger.info("🎙️ 正在生成 Edge TTS，音色: %s, 文本长度: %d", voice_id, len(text))
    
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(output_path)
    
    return _finalize_audio(output_path)


async def _generate_minimax_voice(
    text: str,
    output_path: Path,
    voice_id: str,
) -> Path:
    """使用 MiniMax 生成 TTS 音频。"""
    logger.info("🎙️ 正在生成 MiniMax TTS，音色: %s, 文本长度: %d", voice_id, len(text))

    result = await api_post(
        endpoint="/t2a_v2",
        payload={
            "model": "speech-2.8-hd",
            "text": text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
                "emotion": "happy",
            },
            "audio_setting": {
                "sample_rate": AUDIO_SAMPLE_RATE,
                "format": "mp3",
                "channel": 1,
            },
        },
    )

    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise RuntimeError(
            f"MiniMax TTS API 错误 {base_resp.get('status_code')}: {base_resp.get('status_msg')}"
        )

    audio_hex = result.get("data", {}).get("audio")
    if not audio_hex:
        raise RuntimeError(f"MiniMax TTS API 返回无 audio_hex: {result}")

    audio_bytes = binascii.unhexlify(audio_hex)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    return _finalize_audio(output_path)


def _finalize_audio(output_path: Path) -> Path:
    """测量时长并记录日志。"""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(output_path)],
            capture_output=True, text=True, check=True,
        )
        duration_sec = float(probe.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        duration_sec = 0

    logger.info("✅ TTS 生成完成: %s (%.1f 秒)", output_path, duration_sec)
    return output_path
