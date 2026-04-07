"""共享工具函数模块 — DRY 原则核心实现。

所有 FFmpeg、文件操作、API 辅助函数集中于此。
"""
import logging
import subprocess
import binascii
from pathlib import Path
from typing import Callable, Awaitable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ── FFmpeg 工具函数 ─────────────────────────────────────────────────────────

def run_ffmpeg(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """执行 FFmpeg/FFprobe 命令。

    Args:
        cmd: 命令参数列表
        check: 是否检查返回码

    Returns:
        CompletedProcess 对象
    """
    logger.debug("CMD: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    if result.stderr:
        logger.debug("CMD stderr: %s", result.stderr[:500])
    return result


def get_media_duration(path: Path) -> float:
    """获取音/视频文件时长（秒）。

    Args:
        path: 媒体文件路径

    Returns:
        时长（秒），失败返回 0.0
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = run_ffmpeg(cmd)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        logger.warning("获取媒体时长失败: %s — %s", path, e)
        return 0.0


# ── 文件操作工具 ─────────────────────────────────────────────────────────────

def ensure_parent_dir(path: Path) -> Path:
    """确保父目录存在。

    Args:
        path: 文件路径

    Returns:
        原路径（方便链式调用）
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_bytes(data: bytes, path: Path) -> Path:
    """保存字节数据到文件。

    Args:
        data: 字节数据
        path: 目标路径

    Returns:
        保存的文件路径
    """
    ensure_parent_dir(path)
    with open(path, "wb") as f:
        f.write(data)
    return path


def save_hex_audio(hex_str: str, path: Path) -> Path:
    """将 hex 编码的音频数据保存到文件。

    Args:
        hex_str: hex 编码的字符串
        path: 目标路径

    Returns:
        保存的文件路径
    """
    audio_bytes = binascii.unhexlify(hex_str)
    return save_bytes(audio_bytes, path)


# ── API 辅助函数 ─────────────────────────────────────────────────────────────

def check_base_resp(result: dict, context: str = "API") -> None:
    """检查 MiniMax API 的 base_resp 字段。

    Args:
        result: API 返回结果
        context: 上下文描述（用于错误消息）

    Raises:
        RuntimeError: 如果 status_code 非 0
    """
    base_resp = result.get("base_resp", {})
    status_code = base_resp.get("status_code", 0)
    if status_code != 0:
        status_msg = base_resp.get("status_msg", "Unknown error")
        raise RuntimeError(f"{context} 错误 {status_code}: {status_msg}")


def extract_task_id(result: dict, context: str = "Task") -> str:
    """从 API 结果中提取 task_id。

    Args:
        result: API 返回结果
        context: 上下文描述（用于错误消息）

    Returns:
        task_id 字符串

    Raises:
        RuntimeError: 如果 task_id 不存在
    """
    task_id = result.get("task_id")
    if not task_id:
        raise RuntimeError(f"{context} 提交无 task_id: {result}")
    return task_id
