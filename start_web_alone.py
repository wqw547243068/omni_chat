# coding:utf8
# https://github.com/John-Shao/qwen-omni-realtime-chat

import asyncio
import base64
import os
import time
from io import BytesIO
import sys
import dashscope
import gradio as gr
import numpy as np
from dashscope.audio.qwen_omni import OmniRealtimeCallback, OmniRealtimeConversation
from dashscope.audio.qwen_omni.omni_realtime import MultiModality

from fastrtc import (
    AdditionalOutputs,
    AsyncAudioVideoStreamHandler,
    VideoEmitType,
    WebRTC,
    get_cloudflare_turn_credentials_async,
    wait_for_item,
)
from gradio.utils import get_space
from PIL import Image


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
voice = 'Tina' # "Cherry"

API_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"


def encode_image(data: np.ndarray) -> str:
    """Encode a numpy image frame to base64 JPEG string."""
    with BytesIO() as buf:
        Image.fromarray(data).save(buf, "JPEG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")


class QwenOmniCallback(OmniRealtimeCallback):
    """Bridges DashScope SDK callbacks (background thread) into asyncio queues."""

    def __init__(self, handler: "QwenOmniHandler") -> None:
        self.handler = handler

    def on_open(self) -> None:
        print("Connected to Qwen-Omni-Realtime")

    def on_event(self, message: str) -> None:
        response: dict = message  # type: ignore[assignment]  # SDK passes dict despite str annotation
        event_type = response.get("type", "")
        loop = self.handler._event_loop
        if loop is None:
            return

        if event_type == "input_audio_buffer.speech_started":
            print("Speech started, clearing output queue")
            loop.call_soon_threadsafe(self.handler.clear_queue)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = response.get("transcript", "")
            print(f"User: {transcript}")
            loop.call_soon_threadsafe(
                self.handler.output_queue.put_nowait,
                AdditionalOutputs({"role": "user", "content": transcript}),
            )

        elif event_type == "response.audio_transcript.done":
            transcript = response.get("transcript", "")
            print(f"Assistant: {transcript}")
            loop.call_soon_threadsafe(
                self.handler.output_queue.put_nowait,
                AdditionalOutputs({"role": "assistant", "content": transcript}),
            )

        elif event_type == "response.audio.delta":
            audio = np.frombuffer(
                base64.b64decode(response["delta"]), dtype=np.int16
            ).reshape(1, -1)
            loop.call_soon_threadsafe(
                self.handler.output_queue.put_nowait,
                (self.handler.output_sample_rate, audio),
            )

    def on_close(self, close_status_code: int, close_msg: str) -> None:
        print(f"Connection closed (code={close_status_code}, msg={close_msg})")


class QwenOmniHandler(AsyncAudioVideoStreamHandler):
    def __init__(self) -> None:
        super().__init__(
            "mono",
            output_sample_rate=24000,
            input_sample_rate=16000,
        )
        self.video_queue: asyncio.Queue = asyncio.Queue()
        self.output_queue: asyncio.Queue = asyncio.Queue()
        self.last_frame_time: float = 0
        self.conversation: OmniRealtimeConversation | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def copy(self):
        return QwenOmniHandler()

    async def start_up(self) -> None:
        self._event_loop = asyncio.get_running_loop()
        callback = QwenOmniCallback(self)
        self.conversation = OmniRealtimeConversation(
            model=model,
            callback=callback,
            url=API_URL,
        )
        assert self.conversation is not None
        try:
            self.conversation.connect()
            print("Session connected")
            self.conversation.update_session(
                output_modalities=[MultiModality.TEXT, MultiModality.AUDIO],
                voice=voice,
                instructions=system_prompt + "\n你可以看到用户的摄像头画面，请根据画面内容进行交流。",
            )
            print("Session configured")
            # Block the startup coroutine until the SDK thread exits.
            await asyncio.get_running_loop().run_in_executor(
                None, self.conversation.thread.join
            )
        except Exception as e:
            print(f"Connection error: {e}")
            self.shutdown()

    async def video_receive(self, frame: np.ndarray) -> None:
        self.video_queue.put_nowait(frame)
        if self.conversation and time.time() - self.last_frame_time > 1:
            self.last_frame_time = time.time()
            image_b64 = encode_image(frame)
            print("Sending image frame")
            await asyncio.get_running_loop().run_in_executor(
                None, self.conversation.append_video, image_b64
            )

    async def video_emit(self) -> VideoEmitType:
        return await self.video_queue.get()

    async def receive(self, frame: tuple[int, np.ndarray]) -> None:
        if not self.conversation:
            return
        _, array = frame
        array = array.squeeze()
        audio_b64 = base64.b64encode(array.tobytes()).decode("utf-8")
        await asyncio.get_running_loop().run_in_executor(
            None, self.conversation.append_audio, audio_b64
        )

    async def emit(self) -> tuple[int, np.ndarray] | AdditionalOutputs | None:
        return await wait_for_item(self.output_queue)

    def shutdown(self) -> None:
        if self.conversation:
            self.conversation.close()
            self.conversation = None
        while not self.output_queue.empty():
            self.output_queue.get_nowait()

rtc_config = get_cloudflare_turn_credentials_async if get_space() else None

css = """
#video-source {max-width: 600px !important; max-height: 600px !important;}
.gradio-container {padding-bottom: 60px !important;}
"""

with gr.Blocks(css=css) as demo:
    with gr.Row() as row:
        with gr.Column():
            webrtc = WebRTC(
                label="Video Chat",
                modality="audio-video",
                mode="send-receive",
                elem_id="video-source",
                rtc_configuration=rtc_config,
                icon="https://avatars.githubusercontent.com/u/109945100?s=200&v=4",
                pulse_color="rgb(35, 157, 225)",
                icon_button_color="rgb(35, 157, 225)",
            )

        webrtc.stream(
            QwenOmniHandler(),
            inputs=[webrtc],
            outputs=[webrtc],
            time_limit=90,
            concurrency_limit=2,
        )


if __name__ == "__main__":
    demo.launch()
