from typing import Optional, List, Dict, Union, Any, Tuple
"""阶段2c：音乐生成 — 使用统一 api_client。

模型: music-2.5+，is_instrumental=true。
异步提交 + 轮询。
"""
import asyncio
import logging
from pathlib import Path

from .api_client import api_post, download_file, poll_async_task
from .config import ASSETS_DIR, AUDIO_BIT_RATE, AUDIO_SAMPLE_RATE, MODEL_MUSIC

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5
_MAX_WAIT_SEC = 300


async def generate_music(
    prompt: str = "轻快的背景音乐，适合短视频",
    duration: int = 60,
    is_instrumental: bool = True,
    output_filename: str = "music.mp3",
) -> Path:
    """生成背景音乐。"""
    output_path = ASSETS_DIR / output_filename
    logger.info("🎶 正在生成音乐，prompt: %s，时长: %ds", prompt, duration)

    # 提交任务
    payload = {
        "model": MODEL_MUSIC,
        "prompt": prompt,
        "duration": duration,
        "output_format": "url",
        "audio_setting": {
            "sample_rate": AUDIO_SAMPLE_RATE,
            "bitrate": AUDIO_BIT_RATE,
        },
    }
    
    # 仅 music-2.5+ 支持 is_instrumental 参数，其他需带 lyrics
    if "music-2.5+" in MODEL_MUSIC:
        payload["is_instrumental"] = is_instrumental
    else:
        # music-2.5 强制要求 lyrics
        payload["lyrics"] = "[Instrumental]"
        
    result = await api_post(
        endpoint="/music_generation",
        payload=payload,
    )

    # music-2.5 同步完成状态码（无需轮询）
    _SYNC_COMPLETE = 2
    data = result.get("data")
    if data and data.get("audio") and data.get("status") == _SYNC_COMPLETE:
        # 立即返回结果 (music-2.5 常见)
        audio_url = data["audio"]
        logger.info("✅ 音乐已即时生成: %s", audio_url)
        
        # 下载并保存
        await download_file(audio_url, output_path)
        logger.info("✅ 音乐已保存到: %s", output_path)
        return output_path

    task_id = result.get("task_id")
    if not task_id:
        raise RuntimeError(f"Music 提交无 task_id 或立即结果: {result}")
    
    logger.info("🎵 音乐任务已提交，task_id: %s", task_id)

    async def _extractor(res, session, out_path):
        status = res.get("status", "")
        logger.debug("音乐任务状态: %s", status)

        if status == "Success":
            # 优先尝试 audio_url 下载
            music_url = (
                res.get("data", {}).get("audio_url")
                or res.get("audio_url")
            )
            if music_url:
                logger.info("✅ 音乐生成完成: %s", out_path)
                return True, music_url, None

            # 降级：尝试 hex
            audio_hex = res.get("data", {}).get("audio") or res.get("audio")
            if audio_hex:
                audio_bytes = bytes.fromhex(audio_hex)
                logger.info("✅ 音乐生成完成: %s", out_path)
                return True, audio_bytes, None
                
            return False, None, f"音乐完成但无 audio_url: {res}"

        elif status == "Fail":
            return False, None, f"音乐生成失败: {res}"

        return False, None, None

    return await poll_async_task(
        task_id=task_id,
        query_endpoint="/music_generation/query",
        output_path=output_path,
        result_extractor=_extractor,
        max_wait_sec=_MAX_WAIT_SEC,
        poll_interval=_POLL_INTERVAL
    )
