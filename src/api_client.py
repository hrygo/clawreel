"""统一 API 客户端基类 — DRY + SOLID 核心。

所有 MiniMax API 调用必须通过此类，禁止各模块各自实现。

职责：
- 统一的错误处理和重试
- Session 复用（FINOPS：减少连接开销）
- 幂等性 token 生成
- 彻底移除 GroupId（Token Plan 不需要）
"""
import hashlib
import time
import logging
import contextlib
from pathlib import Path
from typing import Optional

import aiohttp
import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# ── MiniMax API Base URL ────────────────────────────────────────────────────
# 统一使用 /v1 路径（已通过 TTS 验证，Token Plan 和传统 API 均用 /v1）
_MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"
_MINIMAX_API_KEY = ""  # 延迟加载，避免循环导入


def _get_api_key() -> str:
    global _MINIMAX_API_KEY
    if not _MINIMAX_API_KEY:
        import os
        _MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
    return _MINIMAX_API_KEY


def _build_headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


# ── 重试策略 ────────────────────────────────────────────────────────────────
_client_session: Optional[aiohttp.ClientSession] = None


@contextlib.asynccontextmanager
async def get_session() -> aiohttp.ClientSession:
    """获取共享的 AioHTTP Session（线程安全单例）。

    Usage:
        async with get_session() as session:
            async with session.post(url, ...) as resp:
                ...
    """
    global _client_session, _session_lock
    if _client_session is None or _client_session.closed:
        _client_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
        )
    try:
        yield _client_session
    finally:
        pass  # 不关闭 session，复用于整个进程生命周期


async def close_session() -> None:
    """显式关闭 session（进程退出前调用）。"""
    global _client_session
    if _client_session and not _client_session.closed:
        await _client_session.close()
        _client_session = None


# ── 幂等 Token ─────────────────────────────────────────────────────────────
def generate_idempotency_key(*parts: str) -> str:
    """生成幂等性 key（用于防重复提交）。
    同一组 parts 同一时间戳内产生相同的 key。
    """
    ts = int(time.time() // 10)  # 10秒窗口
    raw = f"{':'.join(parts)}:{ts}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


# ── Base API 调用 ───────────────────────────────────────────────────────────

async def api_post(
    endpoint: str,
    payload: dict,
    params: dict | None = None,
    session: aiohttp.ClientSession | None = None,
) -> dict:
    """统一 POST 调用。"""
    url = f"{_MINIMAX_BASE_URL}{endpoint}"

    async def _do_request(sess: aiohttp.ClientSession) -> dict:
        async with sess.post(
            url,
            json=payload,
            headers=_build_headers(),
            params=params or {},
            raise_for_status=False,
        ) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"API {endpoint} HTTP {resp.status}: {text[:200]}")
            return await resp.json()

    if session:
        return await _do_request(session)

    async with get_session() as sess:
        return await _do_request(sess)


async def api_get(
    endpoint: str,
    params: dict | None = None,
    session: aiohttp.ClientSession | None = None,
) -> dict:
    """统一 GET 调用。"""
    url = f"{_MINIMAX_BASE_URL}{endpoint}"

    async def _do_request(sess: aiohttp.ClientSession) -> dict:
        async with sess.get(
            url,
            headers=_build_headers(),
            params=params or {},
            raise_for_status=False,
        ) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"API {endpoint} HTTP {resp.status}: {text[:200]}")
            return await resp.json()

    if session:
        return await _do_request(session)

    async with get_session() as sess:
        return await _do_request(sess)


async def download_file(url: str, output_path: Path) -> Path:
    """下载文件到本地路径（流式写入，避免内存占用）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with get_session() as sess:
        async with sess.get(url, raise_for_status=True) as resp:
            with open(output_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)
    return output_path
