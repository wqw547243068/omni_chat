# omni_chat

omni 视频对话，基于 Qwen-Omni-Realtime 音视频实时对话工具

## 部署部署


### 安装依赖

```bash
pip install dashscope pyaudio opencv-python websockets
```
macOS 安装 pyaudio：

```bash
brew install portaudio
pip install pyaudio
```

### 配置 API Key

复制 `.env` 文件

```sh
cp conf/env.example conf/.env
```

编辑 `conf/env.example`：
- 准备阿里百炼key: `DASHSCOPE_API_KEY`
- 阿里百炼Agent平台:  `workspaceId`

```python
DASHSCOPE_API_KEY = 'sk-xxxxxxxxxxxx'
workspaceId = 'your-workspace-id'
```

### 启动服务

```sh
uv run server_cli.py
# python3 server_cli.py
```


## 功能


功能特点
- 🎙️ **语音对话** — 麦克风输入 + 实时语音播放
- 📹 **视频输入** — 本地摄像头画面实时传输
- 📺 **屏幕共享** — 浏览器端共享屏幕作为视频源
- 💬 **文本聊天** — 文字输入与 AI 交互
- 🔍 **联网搜索** — 实时信息搜索（需模型支持）
- 🌐 **Web 调试界面** — 可视化页面，支持音频/视频/字幕开关
- 🖥️ **Python 客户端** — 命令行模式，支持语音/视频/文本三种模式

## 项目结构

```
omni/
├── conf/
│   ├── env.py          # API Key 与工作空间配置
│   └── sp.py           # 系统提示词
├── server_cli.py         # Python 客户端（命令行音视频对话）
├── web/
│   ├── index.html      # Web 调试页面
│   ├── omni-client.js  # 浏览器端 JavaScript 客户端
│--── server.py       # WebSocket 代理 + 静态文件服务器
└── README.md
```

## 功能


### 终端交互

选择模式：
| 选项 | 模式 | 说明 |
|------|------|------|
| `1` | 仅语音对话 | 麦克风输入 + 语音输出 |
| `2` | 音视频对话 | 摄像头 + 麦克风输入 |
| `3` | 视频+文本对话 | 摄像头 + 文字输入 |

### Web 交互

启动服务器：

```bash
cd web
python server.py
```

默认端口：
- HTTP 服务：`http://localhost:8080`
- WebSocket 代理：`ws://localhost:8081`

通过环境变量自定义端口：
```bash
HTTP_PORT=3000 WS_PORT=9090 python server.py
```

打开浏览器访问 `http://localhost:8080`。

Web 界面功能
- **连接配置** — 设置 WebSocket URL、API Key、模型和语音
- **功能开关** — 控制音频/摄像头/搜索/字幕开关
- **视频预览** — 本地摄像头画面与 AI 回复状态
- **聊天记录** — 实时显示对话内容
- **通信日志** — 详细的 WebSocket 协议流程调试信息


## 注意事项

1. **浏览器支持** — 请使用 Chrome 或 Edge 获取最佳体验
2. **HTTPS 限制** — 获取摄像头需要 HTTPS 或 `localhost` 环境
3. **视频帧率** — 建议 2-5 fps 以平衡流量和响应速度
4. **音频采样率** — 输入 16kHz / 输出 24kHz
5. **API Key 安全** — 不要在公开网络传输中明文传递 API Key

## 开发计划

- [ ] 多路视频源切换
- [ ] 录音录像功能
- [ ] 历史对话导出
- [ ] 模型参数实时调整






