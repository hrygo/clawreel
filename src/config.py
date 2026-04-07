"""配置加载模块 — 单一职责：只负责配置加载和常量定义。

API 调用逻辑已迁移到 api_client.py。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

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

# ── 封面参数 ────────────────────────────────────────────────────────────────
COVER_FULL = (720, 1280)
COVER_VISIBLE = (1080, 1464)

# ── 输出路径 ────────────────────────────────────────────────────────────────
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUT_DIR = PROJECT_ROOT / "output"

# 确保目录存在
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── API 模型名称 ─────────────────────────────────────────────────────────────
MODEL_T2V = "MiniMax-Hailuo-02"
MODEL_I2V = "MiniMax-Hailuo-2.3-Fast"
MODEL_IMAGE = "image-01"
MODEL_TTS = "speech-2.8-hd"
MODEL_MUSIC = "music-2.5+"

# ── TTS 供应商配置 ───────────────────────────────────────────────────────────
import yaml

config_file = PROJECT_ROOT / "config.yaml"
# Defaults in case config.yaml is missing
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

if config_file.exists():
    with open(config_file, "r", encoding="utf-8") as f:
        _yaml_config = yaml.safe_load(f) or {}
        if "tts" in _yaml_config:
            TTS_CONFIG.update(_yaml_config["tts"])

TTS_PROVIDER = os.getenv("TTS_PROVIDER", TTS_CONFIG.get("active_provider", "minimax"))
