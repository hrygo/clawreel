"""阶段2a：视频生成 — 使用统一 api_client。

T2V: MiniMax-Hailuo-02
I2V: MiniMax-Hailuo-2.3-Fast

异步提交 + 轮询等待完成。
官方状态: Preparing / Queueing / Processing / Success / Fail
"""
import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Literal

from .api_client import api_post, api_get, download_file, get_session
from .config import ASSETS_DIR, MODEL_T2V, MODEL_I2V, VIDEO_FPS

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5
_MAX_WAIT_SEC = 300


async def generate_video(
    prompt: str,
    type: Literal["t2v", "i2v"] = "t2v",
    duration: int = 6,
    input_image: str | None = None,
    output_filename: str | None = None,
) -> Path:
    """生成视频（T2V 或 I2V）。"""
    if type == "i2v" and not input_image:
        raise ValueError("I2V 模式需要提供 input_image 参数（图片 URL 或本地路径）")

    model = MODEL_T2V if type == "t2v" else MODEL_I2V
    if output_filename is None:
        output_filename = f"video_{type}_{hashlib.md5(prompt.encode()).hexdigest()[:8]}.mp4"

    output_path = ASSETS_DIR / output_filename
    logger.info("🎬 正在生成 %s 视频，prompt: %s", type.upper(), prompt[:50])

    payload: dict = {
        "model": model,
        "prompt": prompt,
        "duration": duration,
        "fps": VIDEO_FPS,
        "resolution": "768P",
    }
    if input_image:
        payload["first_frame_image"] = input_image

    result = await api_post(endpoint="/video_generation", payload=payload)

    task_id = result.get("task_id")
    if not task_id:
        raise RuntimeError(f"视频提交无 task_id: {result}")
    logger.info("📹 视频任务已提交，task_id: %s", task_id)

    return await _poll_video(task_id, output_path)


async def _poll_video(task_id: str, output_path: Path) -> Path:
    """轮询视频任务直到完成，下载并返回本地路径。

    官方状态: Preparing → Queueing → Processing → Success
                                                    → Fail
    """
    async with get_session() as session:
        elapsed = 0
        while elapsed < _MAX_WAIT_SEC:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

            result = await api_get(
                endpoint="/query/video_generation",
                params={"task_id": task_id},
                session=session,
            )

            status = result.get("status", "")
            logger.debug("视频任务状态: %s", status)

            if status == "Success":
                file_id = result.get("file_id")
                if not file_id:
                    raise RuntimeError(f"视频完成但无 file_id: {result}")

                file_result = await api_get(
                    endpoint="/files/retrieve",
                    params={"file_id": file_id},
                    session=session,
                )

                video_url = file_result.get("file", {}).get("download_url")
                if not video_url:
                    raise RuntimeError(f"文件检索无 download_url: {file_result}")

                await download_file(video_url, output_path)
                logger.info("✅ 视频生成完成: %s", output_path)
                return output_path

            elif status == "Fail":
                base = result.get("base_resp", {})
                raise RuntimeError(
                    f"视频生成失败: {base.get('status_code')} — {base.get('status_msg')}"
                )

            # Preparing / Queueing / Processing: 继续等待，不报错

    raise TimeoutError(f"视频生成超时（{_MAX_WAIT_SEC}秒）: {task_id}")
