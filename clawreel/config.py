from typing import Optional, List, Dict, Union, Any, Tuple
"""配置加载模块 — 单一职责：只负责配置加载和常量定义。

API 调用逻辑已迁移到 api_client.py。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 优先从当前执行目录加载环境变量
load_dotenv(Path.cwd() / ".env")

# ── MiniMax API ─────────────────────────────────────────────────────────────
# Token Plan 统一使用 /v1 路径（TTS 已验证）
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_API_HOST = os.getenv("MINIMAX_API_HOST", "https://api.minimaxi.com").rstrip("/")
BASE_URL = f"{MINIMAX_API_HOST}/v1"
BASE_DOWNLOAD_URL = f"{MINIMAX_API_HOST}/v1"  # 文件下载也用 /v1

# ── 音频参数 ────────────────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 44100
AUDIO_BIT_RATE = 128000
AUDIO_FORMAT = "mp3"

# ── 视频参数 ────────────────────────────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 25
VIDEO_BITRATE = "6M"
VIDEO_DURATION_DEFAULT = 6        # 默认视频时长（秒）
VIDEO_DURATION_MIN = 3            # 最小视频时长
VIDEO_DURATION_MAX = 30           # 最大视频时长（取决于分辨率）

# ── FFmpeg 编码参数（统一常量）────────────────────────────────────────────────
FFMPEG_VIDEO_OPTS = ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p"]

# ── 音乐参数 ────────────────────────────────────────────────────────────────
MUSIC_DURATION_DEFAULT = 60      # 默认音乐时长（秒）
MUSIC_DURATION_MIN = 15          # 最小音乐时长
MUSIC_DURATION_MAX = 300         # 最大音乐时长（API 限制）
BG_MUSIC_VOLUME = 0.15           # 背景音乐音量（相对 TTS，0.0-1.0）

# ── 封面参数 ────────────────────────────────────────────────────────────────
COVER_FULL = (720, 1280)
COVER_VISIBLE = (1080, 1464)

# ── 输出路径（基于命令执行所在的目录）────────────────────────────────────────────────
ASSETS_DIR = Path.cwd() / "assets"
OUTPUT_DIR = Path.cwd() / "output"

# 确保目录存在
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── API 模型名称（默认值） ─────────────────────────────────────────────────────
MODEL_T2V = "MiniMax-Hailuo-2.3"
MODEL_I2V = "MiniMax-Hailuo-2.3-Fast"
# T2V/I2V 统一 fallback 链：T2V 优先，额度耗尽时降级为 I2V（需 input_image），I2V 失败再切回其他 T2V
VIDEO_MODEL_FALLBACKS = [
    "MiniMax-Hailuo-2.3",       # T2V 首选
    "MiniMax-Hailuo-2.3-Fast", # I2V（需 input_image）
    "MiniMax-Hailuo-02",        # T2V 备选
    "T2V-01",                   # T2V 最后备选
]
MODEL_IMAGE = "image-01"
MODEL_TTS = "speech-2.8-hd"
MODEL_MUSIC = "music-2.5"

# ── 配置文件加载 ─────────────────────────────────────────────────────────────
import yaml

# 从当前终端执行目录寻找 config.yaml
config_file = Path.cwd() / "config.yaml"

# TTS Defaults
TTS_CONFIG = {
    "active_provider": "minimax",
    "providers": {
        "minimax": {
            "voice_id": "female-shaonv",
            "speed": 1.0,
            "vol": 1.0,
            "emotion": "happy"
        },
        "edge": {
            "voice_id": "zh-CN-XiaoxiaoNeural"
        }
    }
}

# ── 配置文件加载（统一读取一次）──────────────────────────────────────────────
_yaml_config = {}
if config_file.exists():
    with open(config_file, "r", encoding="utf-8") as f:
        _yaml_config = yaml.safe_load(f) or {}

# ── MiniMax 模型配置 ──────────────────────────────────────────────────────────
if "minimax" in _yaml_config:
    _models = _yaml_config["minimax"].get("models", {})
    if "t2v" in _models: MODEL_T2V = _models["t2v"]
    if "i2v" in _models: MODEL_I2V = _models["i2v"]
    if "image" in _models: MODEL_IMAGE = _models["image"]
    if "tts" in _models: MODEL_TTS = _models["tts"]
    if "music" in _models: MODEL_MUSIC = _models["music"]

# ── 视频配置 ─────────────────────────────────────────────────────────────────
if "video" in _yaml_config:
    _video_cfg = _yaml_config["video"]
    if "width" in _video_cfg: VIDEO_WIDTH = _video_cfg["width"]
    if "height" in _video_cfg: VIDEO_HEIGHT = _video_cfg["height"]
    if "fps" in _video_cfg: VIDEO_FPS = _video_cfg["fps"]
    if "bitrate" in _video_cfg: VIDEO_BITRATE = _video_cfg["bitrate"]
    if "duration_default" in _video_cfg:
        VIDEO_DURATION_DEFAULT = _video_cfg["duration_default"]

# ── 音乐配置 ─────────────────────────────────────────────────────────────────
if "music" in _yaml_config:
    _music_cfg = _yaml_config["music"]
    if "duration_default" in _music_cfg:
        MUSIC_DURATION_DEFAULT = _music_cfg["duration_default"]
    if "bg_volume" in _music_cfg:
        BG_MUSIC_VOLUME = float(_music_cfg["bg_volume"])

# ── TTS 配置 ─────────────────────────────────────────────────────────────────
if "tts" in _yaml_config:
    TTS_CONFIG.update(_yaml_config["tts"])

# ── AIGC 标识配置 ────────────────────────────────────────────────────────────
AIGC_CONFIG = _yaml_config.get("aigc")

TTS_PROVIDER = os.getenv("TTS_PROVIDER", TTS_CONFIG.get("active_provider", "minimax"))
