"""阶段2c：音乐生成 — 使用统一 api_client。

模型: music-2.5+，is_instrumental=true。
异步提交 + 轮询。
"""
import asyncio
import logging
from pathlib import Path

from .api_client import api_post, api_get
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
    result = await api_post(
        endpoint="/music_generation",
        payload={
            "model": MODEL_MUSIC,
            "prompt": prompt,
            "duration": duration,
            "is_instrumental": is_instrumental,
            "output_format": "url",
            "audio_setting": {
                "sample_rate": AUDIO_SAMPLE_RATE,
                "bitrate": AUDIO_BIT_RATE,
            },
        },
    )

    task_id = result.get("task_id")
    if not task_id:
        raise RuntimeError(f"Music 提交无 task_id: {result}")
    logger.info("🎵 音乐任务已提交，task_id: %s", task_id)

    return await _poll_music(task_id, output_path)


async def _poll_music(task_id: str, output_path: Path) -> Path:
    """轮询音乐任务直到完成，下载并返回本地路径。"""
    elapsed = 0
    while elapsed < _MAX_WAIT_SEC:
        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

        result = await api_get(
            endpoint="/music_generation/query",
            params={"task_id": task_id},
        )

        status = result.get("status", "")
        logger.debug("音乐任务状态: %s", status)

        if status == "Success":
            # 优先尝试 audio_url 下载
            music_url = (
                result.get("data", {}).get("audio_url")
                or result.get("audio_url")
            )
            if not music_url:
                # 降级：尝试 hex
                audio_hex = result.get("data", {}).get("audio") or result.get("audio")
                if audio_hex:
                    audio_bytes = bytes.fromhex(audio_hex)
                else:
                    raise RuntimeError(f"音乐完成但无 audio_url: {result}")
            else:
                from .api_client import download_file
                music_tmp = output_path.parent / f"_music_{task_id}.mp3"
                await download_file(music_url, music_tmp)
                audio_bytes = music_tmp.read_bytes()
                music_tmp.unlink(missing_ok=True)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            logger.info("✅ 音乐生成完成: %s", output_path)
            return output_path

        elif status == "Fail":
            raise RuntimeError(f"音乐生成失败: {result}")

    raise TimeoutError(f"音乐生成超时（{_MAX_WAIT_SEC}秒）: {task_id}")
