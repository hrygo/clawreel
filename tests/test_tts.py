import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.tts_voice import generate_voice
from src.config import ASSETS_DIR

logging.basicConfig(level=logging.INFO)

async def main():
    text = "你好，这是来自 Edge TTS 的测试声音。很高兴见到你。"
    
    # Test Edge TTS
    print("Testing Edge TTS...")
    edge_path = ASSETS_DIR / "test_edge.mp3"
    try:
        await generate_voice(text, output_path=edge_path, provider="edge", voice_id="zh-CN-XiaoxiaoNeural")
        print(f"Edge TTS success: {edge_path}")
    except Exception as e:
        print(f"Edge TTS failed: {e}")

    # Test MiniMax TTS (optional, might need API key)
    # print("\nTesting MiniMax TTS...")
    # minimax_path = ASSETS_DIR / "test_minimax.mp3"
    # try:
    #     await generate_voice(text, output_path=minimax_path, provider="minimax")
    #     print(f"MiniMax TTS success: {minimax_path}")
    # except Exception as e:
    #     print(f"MiniMax TTS failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
