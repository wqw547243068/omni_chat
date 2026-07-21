# coding:utf8

"""
Qwen-O Omni Realtime — 浏览器端本地演示包。

运行入口请使用 ``python -m web_demo`` 或 ``from web_demo.app import run`` / ``create_app``，
避免在此处导入 ``app`` 时强制依赖 aiohttp（仅 import package 名时更轻量）。
"""

from web_demo.settings import Settings

__all__ = ["Settings"]
