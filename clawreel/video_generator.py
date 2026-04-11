"""Phase 5: 视频生成 — I2V 优先，T2V fallback。

策略：
  1. 若有首帧图片 → 优先用 I2V（质量更高，与图片风格一致）
  2. I2V 失败（不支持/额度耗尽）→ 降级 T2V
  3. T2V 失败 → 换下一个模型重试
  4. 全失败 → 报错

Fallback 链: MiniMax-Hailuo-2.3 (I2V/T2V) → MiniMax-Hailuo-2.3-Fast (I2V)
            → MiniMax-Hailuo-02 (T2V) → T2V-01 (T2V)
"""
import aiohttp
import asyncio
import hashlib
import logging
from pathlib import Path

from .api_client import api_post, api_get, poll_async_task
from .config import ASSETS_DIR, MODEL_T2V, VIDEO_MODEL_FALLBACKS, VIDEO_FPS
from typing import Optional, List, Dict, Any, Union

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5
_MAX_WAIT_SEC = 300

# I2V-only 模型（不支持 T2V，收到 2013 时必须切换 I2V 模式）
_I2V_ONLY_MODELS = {"MiniMax-Hailuo-2.3-Fast"}

# 支持 T2V 的模型（可同时做 I2V）
_T2V_CAPABLE_MODELS = {"MiniMax-Hailuo-2.3", "MiniMax-Hailuo-02", "T2V-01"}


# ── 错误分类 ──────────────────────────────────────────────────────────────────

class VideoRetryableError(Exception):
    """可重试的视频生成错误（额度耗尽/套餐不支持等）。"""

    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"{code} — {msg}")


class VideoModeSwitchError(Exception):
    """T2V 不支持，需切换 I2V 模式（有首帧时）。"""

    pass


# ── 核心生成逻辑 ─────────────────────────────────────────────────────────────

async def generate_video(
    prompt: str,
    type: str = "t2v",
    duration: int = 6,
    input_image: Optional[str] = None,
    output_filename: Optional[str] = None,
) -> Path:
    """生成视频 — I2V 优先（用首帧），I2V 失败再降级 T2V。

    Args:
        prompt:         视频描述
        type:          "t2v" 或 "i2v"（hint，不影响实际 fallback 策略）
        duration:      视频时长（秒）
        input_image:   I2V 首帧图片（本地路径 / MiniMax OSS URL）
        output_filename: 输出文件名
    """
    models_to_try = list(dict.fromkeys([MODEL_T2V] + VIDEO_MODEL_FALLBACKS))

    if output_filename is None:
        output_filename = f"video_{hashlib.md5(prompt.encode()).hexdigest()[:8]}.mp4"
    output_path = ASSETS_DIR / output_filename

    # MiniMax OSS URL 直连，无需上传；本地路径暂不支持
    first_frame:Optional[str] = input_image if input_image else None

    last_error:Optional[Exception] = None

    for model in models_to_try:
        # ── 策略选择 ──────────────────────────────────────────────────────────
        if first_frame:
            # 有首帧 → 优先 I2V
            result = await _try_i2v_then_t2v(model, prompt, duration, first_frame, output_path)
            if result:
                return result
        else:
            # 无首帧 → 直接 T2V
            result = await _try_t2v(model, prompt, duration, output_path)
            if result:
                return result

    raise RuntimeError(f"所有视频模型尝试均告失败。最后一次错误: {last_error}")


async def _try_i2v_then_t2v(
    model: str,
    prompt: str,
    duration: int,
    first_frame: str,
    output_path: Path,
) ->Optional[Path]:
    """优先 I2V，失败后降级 T2V（有首帧时）。"""
    # ① 尝试 I2V（所有模型都支持）
    try:
        task_id = await _submit(model, prompt, duration, first_frame=first_frame)
        logger.info("📹 I2V 任务已提交 (model: %s, 首帧: %s), task_id: %s",
                    model, _short_url(first_frame), task_id)
        return await _poll(task_id, output_path)
    except VideoModeSwitchError:
        logger.info("🔄 模型 %s 不支持当前调用，切换模式重试...", model)
    except VideoRetryableError as e:
        logger.warning("⚠️ I2V %s 失败（%s），降级 T2V...", model, e)

    # ② I2V 失败 → 降级 T2V（仅 T2V 模型支持）
    if model not in _T2V_CAPABLE_MODELS:
        logger.info("  模型 %s 不支持 T2V，跳过", model)
        return None

    try:
        task_id = await _submit(model, prompt, duration, first_frame=None)
        logger.info("📹 T2V 任务已提交 (model: %s), task_id: %s", model, task_id)
        return await _poll(task_id, output_path)
    except VideoRetryableError as e:
        logger.warning("⚠️ T2V %s 也失败: %s", model, e)
    except VideoModeSwitchError:
        # T2V 模型收到 T2V 不支持？理论上不应该发生
        logger.warning("⚠️ T2V 模型 %s 不支持 T2V？跳过", model)

    return None


async def _try_t2v(
    model: str,
    prompt: str,
    duration: int,
    output_path: Path,
) ->Optional[Path]:
    """直接 T2V（无首帧时）。"""
    if model in _I2V_ONLY_MODELS:
        logger.info("  模型 %s 仅支持 I2V，无首帧，跳过", model)
        return None

    try:
        task_id = await _submit(model, prompt, duration, first_frame=None)
        logger.info("📹 T2V 任务已提交 (model: %s), task_id: %s", model, task_id)
        return await _poll(task_id, output_path)
    except VideoModeSwitchError:
        # T2V 模型收到 "不支持 T2V" → 理论上不可能，忽略
        logger.warning("⚠️ T2V 模型 %s 收到 T2V 不支持错误，跳过", model)
    except VideoRetryableError as e:
        logger.warning("⚠️ T2V %s 失败: %s", model, e)

    return None


def _short_url(url: str) -> str:
    """截断 URL 用于日志显示。"""
    if len(url) > 40:
        return url[:20] + "..." + url[-20:]
    return url


# ── 任务提交 ─────────────────────────────────────────────────────────────────

async def _submit(
    model: str,
    prompt: str,
    duration: int,
    first_frame: Optional[str],
) -> str:
    """提交视频生成任务，返回 task_id。"""
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "duration": duration,
        "fps": VIDEO_FPS,
        "resolution": "768P",
    }
    if first_frame:
        payload["first_frame_image"] = first_frame

    result = await api_post(endpoint="/video_generation", payload=payload)
    task_id = result.get("task_id")
    if task_id:
        return task_id

    base = result.get("base_resp", {})
    code = base.get("status_code", 0)
    msg = base.get("status_msg", "unknown")

    # I2V-only 模型收到 "does not support Text-to-Video" → 切换模式
    if code == 2013 and "does not support Text-to-Video" in msg:
        raise VideoModeSwitchError(f"{code} — {msg}")

    # 可重试错误
    retryable = {2013, 2056, 2061, 9013, 9014, 5001, 5002}
    if code in retryable:
        raise VideoRetryableError(code, msg)

    raise RuntimeError(f"视频提交失败（不可重试）: {result}")


# ── 轮询 ─────────────────────────────────────────────────────────────────────

async def _poll(task_id: str, output_path: Path) -> Path:
    """轮询并等待视频生成完成。"""

    async def extractor(res, session, out_path):
        status = res.get("status", "")
        logger.debug("视频任务状态: %s", status)

        if status == "Success":
            file_id = res.get("file_id")
            if not file_id:
                return False, None, f"视频完成但无 file_id: {res}"
            file_result = await api_get(
                endpoint="/files/retrieve",
                params={"file_id": file_id},
                session=session,
            )
            video_url = file_result.get("file", {}).get("download_url")
            if not video_url:
                return False, None, f"文件检索无 download_url: {file_result}"
            logger.info("✅ 视频生成完成: %s", out_path)
            return True, video_url, None

        if status == "Fail":
            base = res.get("base_resp", {})
            return False, None, f"{base.get('status_code')} — {base.get('status_msg')}"

        return False, None, None

    return await poll_async_task(
        task_id=task_id,
        query_endpoint="/query/video_generation",
        output_path=output_path,
        result_extractor=extractor,
        max_wait_sec=_MAX_WAIT_SEC,
        poll_interval=_POLL_INTERVAL,
    )
