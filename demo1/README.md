# [qwen-omni-realtime-chat](https://github.com/John-Shao/qwen-omni-realtime-chat/tree/main)

通义千问实时音视频聊天模型（**Qwen-Omni-Realtime**）演示程序。

基于阿里云 [DashScope](https://dashscope.aliyun.com/) 的 `qwen3-omni-flash-realtime` 模型，结合 [FastRTC](https://github.com/freddyaboulton/fastrtc) + [Gradio](https://www.gradio.app/) 提供一个开箱即用的浏览器端实时音视频对话 Demo——用户通过摄像头和麦克风与模型交互，模型实时返回语音及文字。

## 功能特性

- 🎙️ **实时双向语音对话**：基于 WebRTC，低延迟音频上下行
- 📹 **视频帧理解**：每秒上送一帧画面，模型可结合画面内容回答问题
- 🗣️ **可定制音色 / 人设**：通过 `voice` 与 `instructions` 灵活配置
- 🔊 **服务端 VAD 自动打断**：用户开口时自动清空模型当前回放队列
- 📝 **实时字幕**：用户语音转写与助手回复文本同步事件回调

## 环境要求

- Python **3.10+**
- 可访问 [DashScope](https://dashscope.console.aliyun.com/) 的 API Key
- 支持 WebRTC 的现代浏览器（Chrome / Edge / Firefox 等）
- 麦克风与摄像头权限

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/John-Shao/qwen-omni-realtime-chat.git
cd qwen-omni-realtime-chat
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置 API Key

`.env` 里填入 DashScope API Key：


```dotenv
Qwen_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

> 也可以通过系统环境变量直接设置 `Qwen_API_KEY`。

### 4. 启动 Demo

```bash
python video_chat.py
```

启动后访问终端打印的本地 URL（默认 http://127.0.0.1:7860），在页面中允许浏览器使用摄像头和麦克风，点击开始即可与模型对话。

## 项目结构

```
qwen-omni-realtime-chat/
├── video_chat.py        # 主程序：Gradio + FastRTC + DashScope 实时会话
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量模板
├── LICENSE              # MIT
└── README.md
```

## 自定义配置

主要配置项集中在 [video_chat.py](video_chat.py) 中：

| 配置项 | 位置 | 说明 |
| --- | --- | --- |
| `MODEL` | [video_chat.py:28](video_chat.py#L28) | DashScope 模型名，默认 `qwen3-omni-flash-realtime` |
| `API_URL` | [video_chat.py:29](video_chat.py#L29) | Realtime WebSocket 接入点 |
| `voice` | [video_chat.py:118](video_chat.py#L118) | 输出音色，可选 `Cherry`、`Ethan` 等（详见 DashScope 文档） |
| `instructions` | [video_chat.py:119-140](video_chat.py#L119-L140) | 系统提示词 / 角色设定 |
| `output_sample_rate` / `input_sample_rate` | [video_chat.py:92-94](video_chat.py#L92-L94) | 音频采样率（输出 24kHz、输入 16kHz） |
| 视频帧采样间隔 | [video_chat.py:153](video_chat.py#L153) | 默认每秒上送 1 帧 |
| `time_limit` | [video_chat.py:209](video_chat.py#L209) | 单次会话时长上限（秒） |

## 工作原理

```
┌────────────┐  WebRTC   ┌──────────────────┐  WebSocket   ┌───────────────────────┐
│  浏览器     │ ───────▶ │ FastRTC + Gradio │ ──────────▶ │ DashScope Realtime API│
│ (mic/cam)  │ ◀──────── │  (video_chat.py) │ ◀────────── │   qwen3-omni-flash    │
└────────────┘   音视频   └──────────────────┘   事件流     └───────────────────────┘
```

- 浏览器通过 WebRTC 将音频（16kHz PCM）与视频帧推送到本地服务
- `QwenOmniHandler` 将音频经 base64 编码后通过 `append_audio` 上送 DashScope；视频帧约每秒一次通过 `append_video` 上送
- DashScope 异步回调 `response.audio.delta`、`response.audio_transcript.done` 等事件，由 `QwenOmniCallback` 转入 asyncio 队列，再经 FastRTC 回送浏览器播放和渲染

## 常见问题

- **连接失败 / 401**：检查 `Qwen_API_KEY` 是否正确、是否已开通 `qwen3-omni-flash-realtime` 模型访问权限。
- **听不到声音**：确认浏览器已授予扬声器/麦克风权限；某些浏览器要求 HTTPS 才能使用 WebRTC，本地 `127.0.0.1` 通常被视为安全源。
- **延迟高 / 卡顿**：实时模型对网络敏感，建议使用稳定的有线网络；如部署在公网，可配置 TURN 服务器（代码已支持 Cloudflare TURN 凭证）。
- **联网搜索**：模型本身不联网。若需「明天天气」等实时信息，需要自行接入 `web_search` 工具。

## 参考链接

- [Qwen-Omni-Realtime 模型文档](https://help.aliyun.com/zh/model-studio/qwen-omni-realtime)
- [DashScope Python SDK](https://github.com/dashscope/dashscope-sdk-python)
- [FastRTC](https://github.com/freddyaboulton/fastrtc)
- [Gradio](https://www.gradio.app/)

## License

[MIT](LICENSE) © 2026 John Shao
