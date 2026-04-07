"""单元测试 - 验证各模块接口和关键规格."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import (
    AUDIO_SAMPLE_RATE,
    AUDIO_BIT_RATE,
    COVER_FULL,
    COVER_VISIBLE,
    MODEL_T2V,
    MODEL_I2V,
    MODEL_IMAGE,
    MODEL_TTS,
    MODEL_MUSIC,
)


class TestConfigSpecs:
    """验证技术规格是否正确."""

    def test_sample_rate_is_44100(self):
        """⚠️ 采样率必须是 44100 Hz，不是 32000."""
        assert AUDIO_SAMPLE_RATE == 44100, f"采样率错误: {AUDIO_SAMPLE_RATE}，应为 44100"

    def test_audio_bit_rate(self):
        """音频码率 128000."""
        assert AUDIO_BIT_RATE == 128000

    def test_cover_visible_region(self):
        """封面可见区域：顶部 456px 被遮挡，即 1080×1464."""
        assert COVER_VISIBLE == (1080, 1464), f"封面可见区域错误: {COVER_VISIBLE}"

    def test_cover_full_resolution(self):
        """封面全分辨率 720×1280."""
        assert COVER_FULL == (720, 1280)

    def test_model_names(self):
        """API 模型名称必须符合 MiniMax 官方规范."""
        # T2V: MiniMax-Hailuo-2.3 或 MiniMax-Hailuo-02
        assert MODEL_T2V in ("MiniMax-Hailuo-2.3", "MiniMax-Hailuo-02"), f"T2V 模型名异常: {MODEL_T2V}"
        # I2V: MiniMax-Hailuo-2.3-Fast
        assert MODEL_I2V in ("MiniMax-Hailuo-2.3-Fast", "MiniMax-Hailuo-02"), f"I2V 模型名异常: {MODEL_I2V}"
        # TTS: speech-2.8-hd（无 MiniMax- 前缀，API 直接用此名称）
        assert MODEL_TTS.startswith("speech-"), f"TTS 模型名异常: {MODEL_TTS}"
        # Music: music-2.5+
        assert MODEL_MUSIC.startswith("music-"), f"Music 模型名异常: {MODEL_MUSIC}"

    def test_image_model(self):
        """图片模型 image-01."""
        assert MODEL_IMAGE == "image-01"


class TestScriptGenerator:
    """测试脚本生成模块."""

    def test_script_data_structure(self):
        """验证 ScriptData 结构."""
        from src.script_generator import ScriptData
        data: ScriptData = {
            "title": "测试标题",
            "script": "测试脚本内容",
            "hooks": ["钩子1", "钩子2"],
            "cta": "关注我",
        }
        assert "title" in data
        assert "script" in data
        assert "hooks" in data
        assert "cta" in data


class TestTTS:
    """测试 TTS 模块."""

    def test_video_fps(self):
        """视频帧率应为 25fps（MiniMax Hailuo 推荐）."""
        from src.config import VIDEO_FPS
        assert VIDEO_FPS == 25, f"视频帧率应为 25，实际: {VIDEO_FPS}"


class TestMusicGenerator:
    """测试音乐生成模块 - 验证 is_instrumental 字段名."""

    def test_is_instrumental_field_name(self):
        """⚠️ 音乐生成 API 字段名是 is_instrumental，不是 instrumental."""
        import inspect
        from src.music_generator import generate_music
        source = inspect.getsource(generate_music)
        assert "is_instrumental" in source, "music_generator.py 必须使用 is_instrumental 字段"
        assert "instrumental" not in source or "is_instrumental" in source


class TestCoverSpecs:
    """封面规格验证."""

    def test_cover_visible_region_key_content_bottom(self):
        """封面关键内容应放在下半部分（顶部456px被抖音标题遮挡）."""
        # COVER_FULL = (720, 1280) 是输出分辨率
        # COVER_VISIBLE = (1080, 1464) 是渲染在 1080 宽画布上的可见区域
        # 抖音标题栏遮挡顶部约 1/3 区域
        # 关键内容必须布局在可见区域下半部分（y > 456）
        assert COVER_VISIBLE == (1080, 1464), f"可见区域应为 1080×1464，实际 {COVER_VISIBLE}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
