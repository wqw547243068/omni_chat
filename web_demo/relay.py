"""
浏览器 WebSocket ⇄ DashScope Realtime 双向转发。

上游连接使用 websockets.connect + Bearer，与 video_call_demo.VideoAudioClient.connect 一致。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp
from aiohttp import web
import websockets
import websockets.exceptions

from settings import Settings
from transcript_hooks import maybe_invoke_joke_api

# 代理自定义：通知浏览器上游已 open，可发 session.update
PROXY_CONNECTED_MESSAGE = json.dumps({"type": "__proxy_connected__"}, ensure_ascii=False)


def _build_upstream_url(region_base: str, model: str) -> str:
    r = region_base.rstrip("/")
    if "model=" in r:
        return r
    joiner = "&" if "?" in r else "?"
    return f"{r}{joiner}model={model}"


async def _browser_to_upstream(
    ws_browser: web.WebSocketResponse, upstream: Any
) -> None:
    try:
        async for msg in ws_browser:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await upstream.send(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await upstream.send(msg.data)
            elif msg.type == aiohttp.WSMsgType.CLOSE:
                break
    except Exception as exc:
        print(f"[web_demo.relay] 浏览器→上游 异常: {exc}")
    finally:
        try:
            await upstream.close()
        except Exception:
            pass


async def _upstream_to_browser(
    ws_browser: web.WebSocketResponse,
    upstream: Any,
    settings: Settings,
) -> None:
    try:
        async for message in upstream:
            if isinstance(message, (bytes, bytearray)):
                raw = bytes(message)
                await maybe_invoke_joke_api(
                    settings, raw.decode("utf-8", errors="replace")
                )
                await ws_browser.send_bytes(raw)
            else:
                await maybe_invoke_joke_api(settings, message)
                await ws_browser.send_str(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as exc:
        print(f"[web_demo.relay] 上游→浏览器 异常: {exc}")
    finally:
        try:
            await ws_browser.close()
        except Exception:
            pass


async def run_websocket_relay(
    ws_browser: web.WebSocketResponse,
    *,
    api_key: str,
    model: str,
    region_base: str,
    settings: Settings,
) -> web.WebSocketResponse:
    """
    建立上游 Realtime 连接，与浏览器双向透传；任一侧结束则取消另一侧。
    """
    url = _build_upstream_url(region_base, model)
    print(f"[web_demo.relay] 上游: {url}")

    # 放宽 ping：避免与 aiohttp 同进程竞争或弱网时被默认 ping_timeout 判死
    upstream = await websockets.connect(
        url,
        additional_headers={"Authorization": f"Bearer {api_key}"},
        ping_interval=30,
        ping_timeout=120,
        proxy=None,  # 禁用代理，直接连接
    )

    await ws_browser.send_str(PROXY_CONNECTED_MESSAGE)

    b2u = asyncio.create_task(_browser_to_upstream(ws_browser, upstream))
    u2b = asyncio.create_task(
        _upstream_to_browser(ws_browser, upstream, settings)
    )
    _, pending = await asyncio.wait(
        {b2u, u2b}, return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    return ws_browser


def parse_proxy_query(request: web.Request, settings: Settings) -> tuple[str, str, str]:
    """从 /ws-proxy URL 查询串解析 apiKey / model / region。"""
    api_key = request.query.get("apiKey", "").strip()
    model = request.query.get("model", settings.default_model)
    region = request.query.get("region", settings.default_region)
    return api_key, model, region
