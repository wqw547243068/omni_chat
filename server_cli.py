# coding:utf8

"""
Qwen-Omni-Realtime 音视频对话客户端 v2
新增：回声消除(AEC)、说话人标记、视频顺序修复
"""

import os
import base64
import time
import json
import threading
import queue
import pyaudio
import cv2
import audioop
from collections import deque
from dashscope.audio.qwen_omni import MultiModality, OmniRealtimeCallback, OmniRealtimeConversation
import dashscope
import sys
from dotenv import load_dotenv
from conf.sp import system_prompt

load_dotenv(dotenv_path='conf/.env')
workspaceId = os.getenv('workspaceId')
dashscope.api_key = os.getenv('DASHSCOPE_API_KEY')

if not dashscope.api_key:
    print(f'配置信息读取失败！')
    sys.exit(-1)

url = f'wss://{workspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime'
model = os.getenv('MODEL', 'qwen3.5-omni-plus-realtime')
voice = 'Tina'

# 消息队列
message_queue = queue.Queue()
print_running = False

# 说话人标记
SPEAKER_USER = "👤 你"
SPEAKER_AI = "🤖 AI"
SPEAKER_SYS = "⚙️ 系统"

def start_printer():
    global print_running
    print_running = True
    def printer_loop():
        while print_running:
            try:
                msg = message_queue.get(timeout=0.1)
                print(msg)
            except queue.Empty:
                continue
    t = threading.Thread(target=printer_loop, daemon=True)
    t.start()

def log(speaker, msg):
    timestamp = time.strftime('%H:%M:%S')
    message_queue.put(f"[{timestamp}] {speaker}: {msg}")


class SimpleAEC:
    """简单回声消除"""
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.ai_playing = False
        self.ai_playing_time = 0
        self.playback_history = deque(maxlen=10)
        
    def on_ai_audio(self, audio_data):
        self.ai_playing = True
        self.ai_playing_time = time.time()
        rms = audioop.rms(audio_data, 2)
        self.playback_history.append(rms)
        
    def on_ai_end(self):
        self.ai_playing = False
        
    def should_transmit(self, mic_data, threshold_silent=300, threshold_ai_playing=800):
        rms = audioop.rms(mic_data, 2)
        if rms < threshold_silent:
            return False
        if self.ai_playing:
            if time.time() - self.ai_playing_time < 0.3:
                return rms > threshold_ai_playing
        return True


class OmniRealtimeClient(OmniRealtimeCallback):
    """Omni-Realtime 回调处理类 - 带AEC和说话人标记"""
    
    def __init__(self, pya, enable_aec=True):
        self.pya = pya
        self.out = None
        self.video_enabled = False
        self.video_thread = None
        self.cap = None
        self.running = False
        self.conv = None
        self.last_user_text = ""
        self.recognizing = False
        self.audio_started = False  # 标记音频是否已开始
        
        # AEC
        self.enable_aec = enable_aec
        self.aec = SimpleAEC() if enable_aec else None
        
        # 视频帧缓存
        self.video_frame_buffer = None
        self.video_ready = threading.Event()
        
    def on_open(self):
        self.out = self.pya.open(
            format=pyaudio.paInt16, 
            channels=1, 
            rate=24000, 
            output=True
        )
        log(SPEAKER_SYS, "音频输出已就绪" + (" | AEC已启用" if self.enable_aec else ""))
        
    def on_event(self, response):
        event_type = response.get('type', '')
        
        # AI音频数据
        if event_type == 'response.audio.delta':
            audio_data = base64.b64decode(response['delta'])
            if self.aec:
                self.aec.on_ai_audio(audio_data)
            self.out.write(audio_data)
            
        # AI播放结束
        elif event_type == 'response.done':
            if self.aec:
                self.aec.on_ai_end()
            usage = response.get('response', {}).get('usage', {})
            plugins = usage.get('plugins', {})
            if plugins.get('search'):
                log(SPEAKER_SYS, f"搜索调用: count={plugins['search']['count']}")
                
        # 用户语音转录完成
        elif event_type == 'conversation.item.input_audio_transcription.completed':
            self.recognizing = False
            transcript = response.get('transcript', '')
            if transcript and transcript.strip() and transcript != self.last_user_text:
                self.last_user_text = transcript
                log(SPEAKER_USER, transcript)
            
        # AI文本完成
        elif event_type == 'response.audio_transcript.done':
            transcript = response.get('transcript', '')
            if transcript and transcript.strip():
                log(SPEAKER_AI, transcript)
                
        # 错误
        elif event_type == 'error':
            err_msg = response.get('error', {}).get('message', 'Unknown error')
            log_err(err_msg)
    
    def process_audio(self, mic_data):
        """处理麦克风音频"""
        if not self.enable_aec or not self.aec:
            return True
        return self.aec.should_transmit(mic_data)
    
    def start_video(self, conv, camera_id=0, fps=5, delay_after_audio=2.0):
        """
        启动摄像头，等待音频建立后再开始
        
        Args:
            delay_after_audio: 音频建立后等待秒数
        """
        if self.video_enabled:
            log(SPEAKER_SYS, "摄像头已在运行")
            return
            
        self.conv = conv
        self.cap = cv2.VideoCapture(camera_id)
        
        if not self.cap.isOpened():
            log(SPEAKER_SYS, f"无法打开摄像头 {camera_id}")
            return
            
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        
        # 启动视频线程，但等待音频信号后才开始发送
        self.video_enabled = True
        self.running = True
        self.video_thread = threading.Thread(
            target=self._video_loop, 
            args=(fps, delay_after_audio)
        )
        self.video_thread.daemon = True
        self.video_thread.start()
        log(SPEAKER_SYS, f"摄像头已启动 (等待音频建立后发送...)")
        
    def _video_loop(self, fps, delay_after_audio):
        """视频采集循环 - 等待音频信号后才发送"""
        frame_interval = 1.0 / fps
        
        # 等待音频建立信号
        log(SPEAKER_SYS, f"视频等待音频初始化 ({delay_after_audio}s)...")
        time.sleep(delay_after_audio)
        
        if not self.audio_started:
            log(SPEAKER_SYS, "警告: 音频未建立，视频可能无法正常发送")
        
        log(SPEAKER_SYS, "视频开始发送")
        
        while self.running and self.video_enabled:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue
                
            # 编码为 JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # 发送视频帧 - 使用 conversation.item.create 而不是 append_video
            if self.conv and self.audio_started:
                try:
                    # 正确的方式：将视频作为消息发送
                    self.conv.append_video(frame_base64)
                except Exception as e:
                    err_msg = str(e)
                    if "append image before append audio" in err_msg:
                        # 音频还没就绪，等待
                        pass
                    else:
                        log(SPEAKER_SYS, f"视频发送失败: {err_msg[:50]}")
            
            time.sleep(frame_interval)
    
    def stop_video(self):
        self.running = False
        self.video_enabled = False
        if self.video_thread:
            self.video_thread.join(timeout=2)
        if self.cap:
            self.cap.release()
            self.cap = None
        log(SPEAKER_SYS, "摄像头已停止")


def log_err(text):
    log(SPEAKER_SYS, f"错误: {text}")


def run_audio_video():
    log(SPEAKER_SYS, "=" * 50)
    log(SPEAKER_SYS, "模式: 音视频对话 (AEC已启用)")
    log(SPEAKER_SYS, "=" * 50)
    
    pya = pyaudio.PyAudio()
    callback = OmniRealtimeClient(pya, enable_aec=True)
    conv = OmniRealtimeConversation(model=model, callback=callback, url=url)
    
    conv.connect()
    callback.on_open()
    
    # 配置会话
    conv.update_session(
        output_modalities=[MultiModality.AUDIO, MultiModality.TEXT],
        voice=voice,
        instructions=system_prompt + "\n你可以看到用户的摄像头画面，请根据画面内容进行交流。",
        enable_search=True,
        search_options={'enable_source': True}
    )
    
    # 打开麦克风
    mic = pya.open(
        format=pyaudio.paInt16, 
        channels=1, 
        rate=16000, 
        input=True,
        frames_per_buffer=3200
    )
    
    # 先发送几帧音频建立连接
    log(SPEAKER_SYS, "正在初始化音频流...")
    for _ in range(5):
        audio_data = mic.read(3200, exception_on_overflow=False)
        if callback.process_audio(audio_data):
            conv.append_audio(base64.b64encode(audio_data).decode())
        time.sleep(0.01)
    
    callback.audio_started = True
    log(SPEAKER_SYS, "音频流已建立")
    
    # 音频建立后才启动视频
    callback.start_video(conv, camera_id=0, fps=3, delay_after_audio=1.0)
    
    log(SPEAKER_SYS, "摄像头和麦克风已启动")
    log(SPEAKER_SYS, "对着麦克风说话，AI 可以看到你的画面 (Ctrl+C 退出)...")
    
    try:
        while True:
            audio_data = mic.read(3200, exception_on_overflow=False)
            if callback.process_audio(audio_data):
                conv.append_audio(base64.b64encode(audio_data).decode())
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        callback.stop_video()
        conv.close()
        mic.close()
        callback.out.close()
        pya.terminate()
        log(SPEAKER_SYS, "对话结束")


def run_audio_only():
    log(SPEAKER_SYS, "=" * 50)
    log(SPEAKER_SYS, "模式: 仅语音对话 (AEC已启用)")
    log(SPEAKER_SYS, "=" * 50)
    
    pya = pyaudio.PyAudio()
    callback = OmniRealtimeClient(pya, enable_aec=True)
    conv = OmniRealtimeConversation(model=model, callback=callback, url=url)
    
    conv.connect()
    callback.on_open()
    
    conv.update_session(
        output_modalities=[MultiModality.AUDIO, MultiModality.TEXT],
        voice=voice,
        instructions=system_prompt,
        enable_search=True,
        search_options={'enable_source': True}
    )
    
    mic = pya.open(
        format=pyaudio.paInt16, 
        channels=1, 
        rate=16000, 
        input=True,
        frames_per_buffer=3200
    )
    
    log(SPEAKER_SYS, "对着麦克风说话 (Ctrl+C 退出)...")
    
    try:
        while True:
            audio_data = mic.read(3200, exception_on_overflow=False)
            if callback.process_audio(audio_data):
                conv.append_audio(base64.b64encode(audio_data).decode())
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        conv.close()
        mic.close()
        callback.out.close()
        pya.terminate()
        log(SPEAKER_SYS, "对话结束")


if __name__ == '__main__':
    start_printer()
    
    log(SPEAKER_SYS, "Qwen-Omni-Realtime v2 (带AEC)")
    log(SPEAKER_SYS, "-" * 50)
    log(SPEAKER_SYS, "1. 仅语音对话")
    log(SPEAKER_SYS, "2. 音视频对话 (先音频后视频)")
    log(SPEAKER_SYS, "-" * 50)
    
    choice = input("选择模式 (1-2, 默认2): ").strip() or "2"
    
    if choice == "1":
        run_audio_only()
    else:
        run_audio_video()
