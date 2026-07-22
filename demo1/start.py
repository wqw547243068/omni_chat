# coding:utf8
# https://github.com/John-Shao/qwen-omni-realtime-chat

import asyncio
import base64
import os
import time
from io import BytesIO

import dashscope
import gradio as gr
import numpy as np
from dashscope.audio.qwen_omni import OmniRealtimeCallback, OmniRealtimeConversation
from dashscope.audio.qwen_omni.omni_realtime import MultiModality
from dotenv import load_dotenv
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


load_dotenv()

dashscope.api_key = os.getenv("Qwen_API_KEY")
# MODEL = "qwen3-omni-flash-realtime"
MODEL = "qwen3.5-omni-plus-realtime"
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
            model=MODEL,
            callback=callback,
            url=API_URL,
        )
        assert self.conversation is not None
        try:
            self.conversation.connect()
            print("Session connected")
            self.conversation.update_session(
                output_modalities=[MultiModality.TEXT, MultiModality.AUDIO],
                voice="Cherry",
                instructions=(
                    "##人设\n"
                    "你是一个全能的超级助手，具备强大的知识库、情感理解能力和解决问题的能力。"
                    "你的目标是高效、专业、友好地帮助用户完成各类任务，包括但不限于日常生活、工作安排、"
                    "信息检索、学习辅导、创意写作、语言翻译和技术支持等；\n\n"
                    "##技能\n"
                    "- 用户会将视频中的某些视频帧截为图片送给你，如果用户询问与视频和图片有关的问题，"
                    "请结合【图片】信息和【用户问题】进行回答；如果用户询问与视频和图片无关的问题，"
                    "无需描述【图片】内容，直接回答【用户问题】；\n"
                    "- 如果用户给你看的是学科题目，不需要把图片里的文字内容一个一个字读出来，"
                    "只需要总结一下【图片】里的文字内容，然后直接回答【用户问题】，可以补充一些解题思路。\n\n"
                    "##约束\n"
                    "- 始终主动、礼貌、有条理；\n"
                    "- 回答准确但不冗长，必要时可提供简洁总结+详细解释；\n"
                    "- 不清楚的任务会主动澄清，不假设、不误导；\n"
                    '- 如果用户问你“明天天气”等需要联网查询才能给出回答的问题，首先确认自己是否有 web_search 工具，'
                    '如果没有，你可以和用户说“你问的问题需要实时联网才能回答，请开启联网功能再体验”；\n'
                    '- 回答中不要出现“图片”、“图中”等字眼，直接根据你看到的内容回答用户问题。\n\n'
                    "##特殊技能\n"
                    "会有不同的人和你说话，你可以识别并区分不同的用户。如果你觉得需要明确下这句话是对谁说的，"
                    "你可以在回复中加上用户的名字。"
                ),
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
