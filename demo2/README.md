# [Qwen Omni Realtime](https://github.com/xiaoyuge886/qwen_omni_realtime/tree/main)

> 🎤 实时语音与视频对话 AI 助手 - 基于 Qwen Omni Realtime API 的 Web 演示

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

<div align="center">
  <img src="public/WechatIMG586.png" alt="界面截图" width="800">
</div>

## ✨ 特性

- 🎤 **实时语音对话** - 低延迟 WebSocket 语音交互
- 📷 **视频视觉能力** - 摄像头实时传输，AI 可见你看到的内容
- 🎨 **Apple 风格界面** - 精心设计的 UI，遵循 Human Interface Guidelines
- 🌗 **深色模式支持** - 自动适配系统偏好
- 🎯 **智能 VAD** - 自动判断说话结束
- 🪟 **可拖动浮窗** - 悬浮式控制面板

## 🚀 快速开始

```bash
# 克隆仓库
git clone https://github.com/xiaoyuge886/qwen_omni_realtime.git
cd qwen-realtime-export

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m web_demo
```

访问 `http://localhost:3000` 开始使用。

## 📖 文档

详细文档请查看 [web_demo/README.md](web_demo/README.md)

## 🛠️ 技术栈

- **后端**: Python + aiohttp + websockets
- **前端**: 原生 JavaScript + Web Audio API
- **API**: Qwen Omni Realtime API

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 🔗 相关链接

- [Qwen Omni API 文档](https://help.aliyun.com/zh/model-studio/realtime)
- [DashScope 控制台](https://dashscope.aliyun.com/)

---

⭐ 如果这个项目对你有帮助，请给它一个 Star！

