"""
在代理层根据上游 Realtime 下行事件做旁路逻辑（不替代透传，仅额外触发本机 HTTP）。

例如：用户语音转写完成后若包含「笑话」，则请求本服务 /api/joke，便于在终端看到调用日志。
"""

from __future__ import annotations

import json

import aiohttp

from web_demo.settings import Settings


async def maybe_invoke_joke_api(settings: Settings, payload: str) -> None:
    """解析单条上游 JSON 文本帧；命中规则则 POST 本机笑话接口。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return
    if data.get("type") != "conversation.item.input_audio_transcription.completed":
        return
    transcript = (data.get("transcript") or "").strip()
    if not transcript or "笑话" not in transcript:
        return

    url = f"http://127.0.0.1:{settings.port}/api/joke"
    print(
        f"[笑话接口] ① 代理旁路命中（转写含「笑话」）→ 即将请求本机 POST {url}",
        flush=True,
    )
    print(f"[笑话接口]    携带 transcript={transcript!r}", flush=True)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json={"transcript": transcript}
            ) as resp:
                body = await resp.read()
                print(
                    f"[笑话接口] ② HTTP 请求结束 status={resp.status} "
                    f"（下一步若出现「③」则说明已进入 handlers.joke_api）",
                    flush=True,
                )
                if resp.status != 200:
                    print(f"[笑话接口]    响应体: {body[:200]!r}", flush=True)
    except Exception as exc:
        print(f"[笑话接口] ✗ POST {url} 失败: {exc}", flush=True)
