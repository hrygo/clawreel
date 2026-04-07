"""单元测试 — script_generator."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawreel.pipeline.p1_script import _parse_script, ScriptData


# ── JSON 解析测试 ────────────────────────────────────────────────────────────

class TestScriptParsing:
    def test_parse_valid_script(self):
        """测试解析合法的脚本 JSON。"""
        json_text = """{
          "title": "测试标题",
          "script": "第一句|第二句|第三句",
          "hooks": ["钩子1", "钩子2"],
          "hook_prompt": "片头提示词",
          "cta": "关注我",
          "style_prompt": "电影感风格",
          "image_prompts": ["场景1", "场景2", "场景3"]
        }"""
        result = _parse_script(json_text)

        assert isinstance(result, dict)
        assert result["title"] == "测试标题"
        assert len(result["sentences"]) == 3
        assert len(result["image_prompts"]) == 3
        # 验证 style_prompt 已合并
        assert all("电影感风格" in p for p in result["image_prompts"])

    def test_image_prompts_count_mismatch_raises(self):
        """测试 image_prompts 数量不匹配时抛出错误。"""
        json_text = """{
          "title": "测试标题",
          "script": "第一句|第二句|第三句",
          "hooks": ["钩子1"],
          "hook_prompt": "片头提示词",
          "cta": "关注我",
          "image_prompts": ["场景1", "场景2"]
        }"""

        with pytest.raises(ValueError, match="image_prompts 数量.*不一致"):
            _parse_script(json_text)

    def test_missing_hook_prompt_raises(self):
        """测试缺少 hook_prompt 时抛出错误。"""
        json_text = """{
          "title": "测试标题",
          "script": "第一句|第二句",
          "hooks": ["钩子1"],
          "cta": "关注我",
          "image_prompts": ["场景1", "场景2"]
        }"""

        with pytest.raises(ValueError, match="脚本缺少必填字段.*hook_prompt"):
            _parse_script(json_text)

    def test_style_prompt_optional(self):
        """测试 style_prompt 可选（默认空字符串）。"""
        json_text = """{
          "title": "测试标题",
          "script": "第一句|第二句",
          "hooks": ["钩子1"],
          "hook_prompt": "片头提示词",
          "cta": "关注我",
          "image_prompts": ["场景1", "场景2"]
        }"""
        result = _parse_script(json_text)

        # 应该正常工作，image_prompts 不包含额外前缀
        assert len(result["image_prompts"]) == 2
        assert result["image_prompts"][0] == "场景1"


# ── JSON 提取测试 ────────────────────────────────────────────────────────────

class TestJSONExtraction:
    def test_extract_json_from_markdown(self):
        """测试从 Markdown 代码块中提取 JSON。"""
        text = """```json
        {
          "title": "测试",
          "script": "一句|两句",
          "hooks": ["钩子"],
          "hook_prompt": "片头",
          "cta": "关注",
          "image_prompts": ["场景1", "场景2"]
        }
        ```"""
        result = _parse_script(text)
        assert result["title"] == "测试"

    def test_extract_json_with_surrounding_text(self):
        """测试从包含额外文本的内容中提取 JSON。"""
        text = """这是一些前言。

        {
          "title": "测试",
          "script": "一句|两句",
          "hooks": ["钩子"],
          "hook_prompt": "片头",
          "cta": "关注",
          "image_prompts": ["场景1", "场景2"]
        }

        这是后续说明。"""
        result = _parse_script(text)
        assert result["title"] == "测试"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
