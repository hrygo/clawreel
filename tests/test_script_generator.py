"""单元测试 — script_generator."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawreel.script_generator import format_script, ScriptData


class TestFormatScript:
    def test_format_pipe_separated(self):
        """测试 | 分隔的文本格式化."""
        result = format_script(content="第一句|第二句|第三句", title="测试标题")
        assert isinstance(result, dict)
        assert result["title"] == "测试标题"
        assert len(result["sentences"]) == 3
        assert result["sentences"][0] == "第一句"

    def test_format_newline_separated(self):
        """测试换行分隔的文本格式化."""
        result = format_script(content="第一句\n第二句\n第三句")
        assert len(result["sentences"]) == 3

    def test_format_extracts_title_from_hash(self):
        """测试从 # 提取标题."""
        result = format_script(content="# 我的视频标题\n第一句|第二句")
        assert result["title"] == "我的视频标题"

    def test_format_hooks_first_two(self):
        """测试钩子识别为前两句."""
        result = format_script(content="钩子1|钩子2|正文")
        assert result["hooks"] == ["钩子1", "钩子2"]

    def test_format_single_sentence(self):
        """测试单句内容."""
        result = format_script(content="只有一句")
        assert len(result["sentences"]) == 1
        assert result["hooks"] == ["只有一句"]

    def test_format_auto_cta(self):
        """测试自动生成 CTA."""
        result = format_script(content="句子1|句子2")
        assert "关注" in result["cta"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
