"""aiohttp 路由：首页与 WebSocket 代理入口。"""

from __future__ import annotations

import datetime

from aiohttp import web

from relay import parse_proxy_query, run_websocket_relay
from settings import Settings


async def joke_api(request: web.Request) -> web.Response:
    """
    演示用「笑话接口」：仅供前端在识别到用户话术中含「笑话」等时调用；
    在运行 web_demo 的终端打印调用日志。
    """
    transcript = ""
    if request.method == "POST" and request.can_read_body:
        try:
            data = await request.json()
            if isinstance(data, dict):
                transcript = str(data.get("transcript", ""))[:300]
        except Exception:
            pass
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"[笑话接口] ③ handlers.joke_api 已执行（本地 HTTP 接口 /api/joke 被真实调用） "
        f"| {now} | method={request.method} | transcript={transcript!r}",
        flush=True,
    )
    return web.json_response(
        {"ok": True, "message": "笑话接口已收到请求"},
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def joke_api_options(_: web.Request) -> web.Response:
    """供浏览器跨域预检时使用（本机同源一般不需要）。"""
    return web.Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


async def config_api(request: web.Request) -> web.Response:
    """返回系统配置：api_key 默认值 和 system_prompt"""
    settings: Settings = request.app["settings"]
    return web.json_response(
        {
            "success": True,
            "api_key": settings.api_key,
            "system_prompt": settings.default_sp,
            "model": settings.default_model,
            "voice": settings.voice,
            "url": settings.default_region
        },
        headers={"Access-Control-Allow-Origin": "*"}
    )


async def config_api_options(_: web.Request) -> web.Response:
    """CORS 预检响应"""
    return web.Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


async def index_page(request: web.Request) -> web.FileResponse:
    settings: Settings = request.app["settings"]
    index_file = settings.public_dir / "index.html"
    if not index_file.is_file():
        raise web.HTTPNotFound(text=f"缺少前端文件: {index_file}")
    return web.FileResponse(index_file)


async def websocket_proxy(request: web.Request) -> web.WebSocketResponse:
    settings: Settings = request.app["settings"]
    ws_browser = web.WebSocketResponse()
    await ws_browser.prepare(request)

    api_key, model, region = parse_proxy_query(request, settings)
    if not api_key:
        await ws_browser.send_json(
            {"type": "error", "error": {"message": "缺少 API Key"}}
        )
        await ws_browser.close()
        return ws_browser

    return await run_websocket_relay(
        ws_browser,
        api_key=api_key,
        model=model,
        region_base=region,
        settings=settings,
    )
