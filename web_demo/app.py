# coding:utf8

"""应用工厂与进程入口。"""

from __future__ import annotations

import argparse
from dataclasses import replace

from aiohttp import web

from web_demo.handlers import (
    index_page,
    joke_api,
    joke_api_options,
    websocket_proxy,
)
from web_demo.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> web.Application:
    s = settings or load_settings()
    app = web.Application()
    app["settings"] = s
    app.router.add_get("/ws-proxy", websocket_proxy)
    app.router.add_post("/api/joke", joke_api)
    app.router.add_get("/api/joke", joke_api)
    app.router.add_options("/api/joke", joke_api_options)
    app.router.add_get("/", index_page)
    return app


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Qwen-O Omni Realtime 浏览器演示（本地代理 + public 静态页）"
    )
    parser.add_argument(
        "--host",
        default=None,
        help=f"监听地址（默认 {load_settings().host}）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"端口（默认 {load_settings().port}）",
    )
    args = parser.parse_args(argv)
    base = load_settings()
    s = base
    if args.host is not None:
        s = replace(s, host=args.host)
    if args.port is not None:
        s = replace(s, port=args.port)

    print(f"\n✅ web_demo 已启动 → http://localhost:{s.port}\n")
    web.run_app(create_app(s), host=s.host, port=s.port)
