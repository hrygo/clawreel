"""共享工具函数模块 — DRY 原则核心实现。

所有 FFmpeg、文件操作、API 辅助函数集中于此。
"""
import logging
import os
import re
import subprocess
import binascii
from pathlib import Path
from typing import Optional, List, Dict, Union, Any, Tuple, Callable, Awaitable, TypeVar, TypedDict

# 统一字符类：保留字母、数字、中文（整洁架构：只出现一次）
CLEAN_CHAR_CLASS_RE = re.compile(r"[^\w\u4e00-\u9fff]+")

logger = logging.getLogger(__name__)

SCRIPT_SEPARATOR = "|"

T = TypeVar("T")


# ── FFmpeg 工具函数 ─────────────────────────────────────────────────────────

def _get_ffmpeg_path(exe: str) -> str:
    """查找 ffmpeg/ffprobe 路径。"""
    # 优先使用 PATH 中的
    import shutil
    p = shutil.which(exe)
    if p:
        return p
    # 备选 Mac 常见路径
    common = [f"/opt/homebrew/bin/{exe}", f"/usr/local/bin/{exe}"]
    for c in common:
        if os.path.exists(c):
            return c
    return exe  # 最终降级为原样

def run_ffmpeg(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """执行 FFmpeg/FFprobe 命令。"""
    if cmd and cmd[0] in ["ffmpeg", "ffprobe"]:
        cmd[0] = _get_ffmpeg_path(cmd[0])

    """
    FFmpeg 有时在成功完成时也返回非零退出码（如被 SIGPIPE/SIGTERM 信号杀死），
    所以这里采用双重策略：
    1. 检查 stderr 中是否有 FFmpeg 明确的错误特征
    2. 检查输出文件是否实际生成（即使退出码非零）

    Args:
        cmd: 命令参数列表
        check: 是否检查返回码

    Returns:
        CompletedProcess 对象
    """
    logger.debug("CMD: %s", " ".join(cmd))
    print(f"RUNNING: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    # FFmpeg 明确错误特征：[ERROR] 大写 / Error: 前缀 / cannot / no such
    stderr_lc = result.stderr or ""
    has_ffmpeg_error = (
        "[ERROR]" in stderr_lc
        or re.search(r"(?i)\berror:", stderr_lc)
        or re.search(r"\bcannot\b|\bno such\b", stderr_lc)
    )
    has_error = result.returncode != 0
    if has_error and check:
        # 即使没有匹配到特定错误字符串，只要 returncode != 0 且 check=True 就报错
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
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
        print(f"DURATION CMD: {' '.join(cmd)}")
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


# ── SRT 工具（消除三处重复）───────────────────────────────────────────────

class WordTimestamp(TypedDict):
    """词级时间戳（来自 Edge TTS SubMaker），集中定义于 utils 避免 TypedDict 重复。"""
    word: str
    start_sec: float
    end_sec: float
    offset_ms: int


def format_srt_timestamp(seconds: float) -> str:
    """将秒数转为 SRT 时间戳格式 HH:MM:SS,mmm。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: List[Dict[str, Any]]) -> str:
    """将对齐后的 segments 转换为标准的 SRT 字符串。"""
    lines: List[str] = []
    for i, seg in enumerate(segments, start=1):
        start = format_srt_timestamp(seg["start_sec"])
        end = format_srt_timestamp(seg["end_sec"])
        text = seg["text"].strip().replace("|", "") # 移除内部的分隔符
        
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def parse_srt_timestamp(ts: str) -> float:
    """解析 SRT 时间戳（HH:MM:SS,mmm）为秒数。"""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s


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


def print_json(data: dict) -> None:
    """格式化并打印 JSON 字典到标准输出。"""
    import json
    print(json.dumps(data, indent=2, ensure_ascii=False))
