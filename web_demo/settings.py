# coding:utf8

"""可配置项：监听地址、默认模型与地域、静态资源目录。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import os
import sys
from dotenv import load_dotenv
from sp import system_prompt



@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 3000

    load_dotenv(dotenv_path='../conf/.env')
    workspaceId = os.getenv('workspaceId')
    api_key = os.getenv('DASHSCOPE_API_KEY')

    if not api_key:
        print(f'配置信息读取失败！')
        sys.exit(-1)

    url = f'wss://{workspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime'
    model = os.getenv('MODEL', 'qwen3.5-omni-plus-realtime')
    voice = 'Tina' # "Cherry"

    # default_model: str = "qwen3-omni-flash-realtime"
    # default_model: str =  "qwen3.5-omni-plus-realtime"
    default_model: str = model
    # default_region: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    default_region: str = url
    voice: str = voice
    default_sp = system_prompt

    @property
    def repo_root(self) -> Path:
        # return Path(__file__).resolve().parent.parent
        return Path(__file__).resolve().parent

    @property
    def public_dir(self) -> Path:
        """前端单页所在目录（与旧版 server.js / Express 共用 public）。"""
        return self.repo_root / "public"


def load_settings() -> Settings:
    return Settings()
