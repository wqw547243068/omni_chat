#!/usr/bin/env python3
# coding:utf8
"""
Qwen-Omni-Realtime Web 调试服务器
支持：心跳保活、自动重连、连接状态监控
"""

import os
import sys
import json
import base64
import asyncio
import websockets
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread
from dotenv import load_dotenv

load_dotenv(dotenv_path='conf/.env')

DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY', '')
WORKSPACE_ID = os.getenv('workspaceId', '')

if WORKSPACE_ID:
    DASHSCOPE_WS_URL = f"wss://{WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime"
else:
    DASHSCOPE_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"

print(f"[配置] WebSocket URL: {DASHSCOPE_WS_URL.replace(WORKSPACE_ID, '***') if WORKSPACE_ID else DASHSCOPE_WS_URL}")
print(f"[配置] API Key: {'已设置' if DASHSCOPE_API_KEY else '未设置'}")


class APIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
        super().__init__(*args, directory=self.web_dir, **kwargs)
    
    def do_GET(self):
        if self.path == '/api/config':
            config = {
                'api_key': DASHSCOPE_API_KEY,
                'model': os.getenv('MODEL', 'qwen3.5-omni-plus-realtime'),
                'workspace': WORKSPACE_ID
            }
            self.send_json(config)
            return
        super().do_GET()
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def end_headers(self):
        self.send_cors_headers()
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}")


class WebSocketProxy:
    """WebSocket 代理 - 带心跳保活"""
    
    def __init__(self):
        self.clients = {}
        self.ping_interval = 20  # 每20秒发送ping
        self.ping_timeout = 10   # ping超时10秒
        
    async def handle_client(self, websocket, path=None):
        client_id = id(websocket)
        dashscope_ws = None
        heartbeat_task = None
        
        print(f"[代理] 客户端 {client_id} 已连接")
        
        try:
            # 设置客户端超时
            websocket.ping_interval = self.ping_interval
            websocket.ping_timeout = self.ping_timeout
            
            # 等待初始化消息
            init_msg = await asyncio.wait_for(websocket.recv(), timeout=30)
            init_data = json.loads(init_msg)
            
            api_key = init_data.get('api_key') or DASHSCOPE_API_KEY
            model = init_data.get('model', 'qwen3.5-omni-plus-realtime')
            
            if not api_key:
                await self.send_error(websocket, 'API Key 不能为空')
                return
            
            # 连接 DashScope
            if WORKSPACE_ID:
                dashscope_url = f"wss://{WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?api_key={api_key}"
            else:
                dashscope_url = f"wss://dashscope.aliyuncs.com/api-ws/v1/realtime?api_key={api_key}"
            
            print(f"[代理] 正在连接 DashScope: {model}")
            
            # 连接时设置更长的超时
            dashscope_ws = await websockets.connect(
                dashscope_url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                close_timeout=10
            )
            print(f"[代理] DashScope 连接成功")
            
            # 发送连接成功消息
            await websocket.send(json.dumps({
                'type': 'connection.open',
                'message': '已连接到 DashScope'
            }))
            
            # 启动心跳保活
            heartbeat_task = asyncio.create_task(
                self.heartbeat(websocket, dashscope_ws, client_id)
            )
            
            # 启动双向转发
            await asyncio.gather(
                self.forward_to_dashscope(websocket, dashscope_ws),
                self.forward_to_client(websocket, dashscope_ws),
                heartbeat_task,
                return_exceptions=True
            )
            
        except asyncio.TimeoutError:
            print(f"[代理] 客户端 {client_id} 初始化超时")
            await self.send_error(websocket, '连接超时，请重试')
        except websockets.exceptions.InvalidStatusCode as e:
            print(f"[代理] DashScope 连接被拒绝: HTTP {e.status_code}")
            error_msg = "API Key 认证失败" if e.status_code == 401 else f"连接被拒绝 ({e.status_code})"
            await self.send_error(websocket, error_msg)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[代理] 连接关闭: code={e.code}, reason={e.reason}")
        except Exception as e:
            print(f"[代理] 错误: {type(e).__name__}: {e}")
            await self.send_error(websocket, str(e))
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
            if dashscope_ws:
                await dashscope_ws.close()
            print(f"[代理] 客户端 {client_id} 资源已清理")
    
    async def heartbeat(self, client_ws, dashscope_ws, client_id):
        """心跳保活 - 定期检查连接状态"""
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                
                # 检查客户端连接
                if client_ws.closed:
                    print(f"[心跳] 客户端 {client_id} 已断开")
                    break
                
                # 检查 DashScope 连接
                if dashscope_ws.closed:
                    print(f"[心跳] DashScope 连接已断开")
                    break
                
                # 发送保活消息给客户端
                try:
                    await client_ws.send(json.dumps({
                        'type': 'ping',
                        'timestamp': asyncio.get_event_loop().time()
                    }))
                except:
                    break
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[心跳] 错误: {e}")
    
    async def send_error(self, websocket, message):
        """发送错误消息"""
        try:
            await websocket.send(json.dumps({
                'type': 'error',
                'error': {'message': message}
            }))
        except:
            pass
    
    async def forward_to_dashscope(self, client_ws, dashscope_ws):
        """转发客户端到 DashScope"""
        try:
            async for message in client_ws:
                if dashscope_ws.closed:
                    break
                    
                data = json.loads(message)
                msg_type = data.get('type', 'unknown')
                
                # 跳过保活响应
                if msg_type == 'pong':
                    continue
                if msg_type == 'init':
                    continue
                
                # 转换消息格式
                if msg_type == 'input_audio_buffer.append':
                    dashscope_msg = {
                        'type': 'input_audio_buffer.append',
                        'audio': data.get('audio', '')
                    }
                elif msg_type == 'input_video_frame.append':
                    dashscope_msg = {
                        'type': 'conversation.item.create',
                        'item': {
                            'type': 'message',
                            'role': 'user',
                            'content': [{
                                'type': 'image_url',
                                'image_url': {'url': f"data:image/jpeg;base64,{data.get('video_frame', '')}"}
                            }]
                        }
                    }
                else:
                    dashscope_msg = data
                
                await dashscope_ws.send(json.dumps(dashscope_msg))
                
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[代理] 转发错误: {e}")
    
    async def forward_to_client(self, client_ws, dashscope_ws):
        """转发 DashScope 到客户端"""
        try:
            async for message in dashscope_ws:
                if client_ws.closed:
                    break
                    
                data = json.loads(message)
                msg_type = data.get('type', 'unknown')
                
                # 只记录非频繁消息
                if msg_type not in ['response.audio.delta']:
                    print(f"[代理] DashScope -> 客户端: {msg_type}")
                
                await client_ws.send(message)
                
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[代理] 转发错误: {e}")


def start_http_server(port=None):
    if port is None:
        port = int(os.getenv('HTTP_PORT', '8080'))
    server = HTTPServer(('0.0.0.0', port), APIHandler)
    print(f"[HTTP] 服务器已启动: http://localhost:{port}")
    server.serve_forever()


async def start_websocket_proxy(port=None):
    if port is None:
        port = int(os.getenv('WS_PORT', '8081'))
    proxy = WebSocketProxy()
    
    # 启动 WebSocket 服务器，启用自动ping/pong
    async with websockets.serve(
        proxy.handle_client, 
        '0.0.0.0', 
        port,
        ping_interval=20,      # 每20秒发送ping
        ping_timeout=10,       # ping超时10秒
        close_timeout=5        # 关闭超时5秒
    ):
        print(f"[WebSocket] 代理已启动: ws://localhost:{port}")
        print(f"[WebSocket] 心跳间隔: 20s, 超时: 10s")
        await asyncio.Future()


async def main():
    print("=" * 50)
    print("Qwen-Omni-Realtime Web 调试服务器")
    print("功能: 心跳保活 | 连接监控 | 错误重试")
    print("=" * 50)
    
    if not DASHSCOPE_API_KEY:
        print("警告: 未设置 DASHSCOPE_API_KEY")
    
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
    if not os.path.exists(web_dir):
        print(f"错误: web 目录不存在")
        sys.exit(1)
    
    http_thread = Thread(target=start_http_server, daemon=True)
    http_thread.start()
    await start_websocket_proxy()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[服务器] 已停止")
