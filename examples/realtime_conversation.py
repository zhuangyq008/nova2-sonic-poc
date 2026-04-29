"""
Nova 2 Sonic 实时麦克风对话 — 完整示例

基于 AWS 官方文档示例，实现实时语音对话。
需要麦克风和扬声器（适合本地开发机测试）。

用法:
  python realtime_conversation.py
  python realtime_conversation.py --voice matthew --region us-west-2

按 Enter 键结束对话。
"""

import os
import sys
import asyncio
import base64
import json
import uuid
import argparse

try:
    import pyaudio
except ImportError:
    print("Error: pyaudio not installed. Run: pip install pyaudio")
    sys.exit(1)

try:
    from aws_sdk_bedrock_runtime.client import (
        BedrockRuntimeClient,
        InvokeModelWithBidirectionalStreamOperationInput,
    )
    from aws_sdk_bedrock_runtime.models import (
        InvokeModelWithBidirectionalStreamInputChunk,
        BidirectionalInputPayloadPart,
    )
    from aws_sdk_bedrock_runtime.config import Config
    from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver
except ImportError:
    print("Error: aws-sdk-bedrock-runtime not installed.")
    print("Run: pip install aws-sdk-bedrock-runtime")
    sys.exit(1)


def ensure_env_credentials():
    """Ensure AWS credentials are in env vars for smithy SDK."""
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        return
    try:
        import boto3
        session = boto3.Session()
        creds = session.get_credentials()
        if creds:
            frozen = creds.get_frozen_credentials()
            os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
            os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
            if frozen.token:
                os.environ["AWS_SESSION_TOKEN"] = frozen.token
    except Exception:
        pass

# Audio configuration
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK_SIZE = 1024

# Default system prompt
DEFAULT_SYSTEM_PROMPT = (
    "You are a warm, professional, and helpful AI assistant. "
    "Give accurate answers that sound natural, direct, and human. "
    "Start by answering the user's question clearly in 1–2 sentences. "
    "Then, expand only enough to make the answer understandable, "
    "staying within 3–5 short sentences total. "
    "Avoid sounding like a lecture or essay."
)

# Bone conduction headphone customer support prompt
SUPPORT_PROMPT = (
    "You are a friendly and knowledgeable customer support agent for bone conduction headphones. "
    "You help customers with bone conduction headphones — product questions, "
    "troubleshooting, and recommendations. "
    "Guidelines: "
    "- Ask about the customer's use case or issue "
    "- Guide through one step at a time for troubleshooting "
    "- Wait for confirmation after each step before moving on "
    "- Use simple, everyday language "
    "- Keep responses conversational and concise (2-3 sentences) "
    "- Be warm and helpful, not robotic"
)


class NovaSonicConversation:
    def __init__(self, model_id="amazon.nova-2-sonic-v1:0", region="us-east-1",
                 voice_id="tiffany", system_prompt=None):
        self.model_id = model_id
        self.region = region
        self.voice_id = voice_id
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.client = None
        self.stream = None
        self.response_task = None
        self.is_active = False
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())
        self.audio_queue = asyncio.Queue()
        self.display_assistant_text = False
        self.role = ""

    def _initialize_client(self):
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        self.client = BedrockRuntimeClient(config=config)

    async def send_event(self, event_json):
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )
        await self.stream.input_stream.send(event)

    async def start_session(self):
        if not self.client:
            self._initialize_client()

        self.stream = await self.client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True

        # Session Start
        await self.send_event(json.dumps({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7,
                    },
                    "turnDetectionConfiguration": {
                        "endpointingSensitivity": "HIGH"
                    }
                }
            }
        }))

        # Prompt Start
        await self.send_event(json.dumps({
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": self.voice_id,
                        "encoding": "base64",
                        "audioType": "SPEECH",
                    },
                }
            }
        }))

        # System Prompt
        await self.send_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "type": "TEXT",
                    "interactive": True,
                    "role": "SYSTEM",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }))
        await self.send_event(json.dumps({
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "content": self.system_prompt,
                }
            }
        }))
        await self.send_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                }
            }
        }))

        # Start processing responses
        self.response_task = asyncio.create_task(self._process_responses())

    async def start_audio_input(self):
        await self.send_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": INPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64",
                    },
                }
            }
        }))

    async def send_audio_chunk(self, audio_bytes):
        if not self.is_active:
            return
        blob = base64.b64encode(audio_bytes).decode("utf-8")
        await self.send_event(json.dumps({
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": blob,
                }
            }
        }))

    async def end_audio_input(self):
        await self.send_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                }
            }
        }))

    async def end_session(self):
        if not self.is_active:
            return
        await self.send_event(json.dumps({
            "event": {"promptEnd": {"promptName": self.prompt_name}}
        }))
        await self.send_event(json.dumps({"event": {"sessionEnd": {}}}))
        await self.stream.input_stream.close()

    async def _process_responses(self):
        try:
            while self.is_active:
                output = await self.stream.await_output()
                result = await output[1].receive()
                if result.value and result.value.bytes_:
                    data = json.loads(result.value.bytes_.decode("utf-8"))
                    if "event" in data:
                        evt = data["event"]
                        if "contentStart" in evt:
                            cs = evt["contentStart"]
                            self.role = cs.get("role", "")
                            if "additionalModelFields" in cs:
                                fields = json.loads(cs["additionalModelFields"])
                                self.display_assistant_text = (
                                    fields.get("generationStage") == "SPECULATIVE"
                                )
                            else:
                                self.display_assistant_text = False
                        elif "textOutput" in evt:
                            text = evt["textOutput"]["content"]
                            if self.role == "ASSISTANT" and self.display_assistant_text:
                                print(f"\n🤖 Assistant: {text}")
                            elif self.role == "USER":
                                print(f"\n🎤 You: {text}")
                        elif "audioOutput" in evt:
                            audio_bytes = base64.b64decode(evt["audioOutput"]["content"])
                            await self.audio_queue.put(audio_bytes)
        except Exception as e:
            if self.is_active:
                print(f"\nError processing responses: {e}")

    async def play_audio(self):
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=OUTPUT_SAMPLE_RATE, output=True)
        try:
            while self.is_active:
                audio_data = await self.audio_queue.get()
                stream.write(audio_data)
        except Exception:
            pass
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    async def capture_audio(self):
        p = pyaudio.PyAudio()
        stream = p.open(
            format=FORMAT, channels=CHANNELS, rate=INPUT_SAMPLE_RATE,
            input=True, frames_per_buffer=CHUNK_SIZE
        )
        print("\n🎙️  Listening... Speak into your microphone.")
        print("   Press Enter to stop.\n")
        await self.start_audio_input()
        try:
            while self.is_active:
                audio_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                await self.send_audio_chunk(audio_data)
                await asyncio.sleep(0.01)
        except Exception as e:
            print(f"Error capturing audio: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
            await self.end_audio_input()


async def main():
    parser = argparse.ArgumentParser(description="Nova 2 Sonic Real-time Conversation")
    parser.add_argument("--voice", default="tiffany",
                        choices=["tiffany", "matthew", "amy", "olivia", "kiara", "arjun",
                                 "ambre", "florian", "beatrice", "lorenzo", "tina", "lennart",
                                 "lupe", "carlos", "carolina", "leo"],
                        help="Voice ID (default: tiffany)")
    parser.add_argument("--region", default="us-east-1",
                        choices=["us-east-1", "us-west-2", "eu-north-1", "ap-northeast-1"])
    parser.add_argument("--support", action="store_true",
                        help="Use bone conduction headphone customer support prompt")
    args = parser.parse_args()

    ensure_env_credentials()
    system_prompt = SUPPORT_PROMPT if args.support else DEFAULT_SYSTEM_PROMPT

    print("=" * 60)
    print("Amazon Nova 2 Sonic — Real-time Conversation")
    print(f"Voice: {args.voice} | Region: {args.region}")
    if args.support:
        print("Mode: Customer Support")
    print("=" * 60)

    client = NovaSonicConversation(
        region=args.region, voice_id=args.voice, system_prompt=system_prompt
    )

    await client.start_session()
    playback_task = asyncio.create_task(client.play_audio())
    capture_task = asyncio.create_task(client.capture_audio())

    # Wait for Enter to stop
    await asyncio.get_event_loop().run_in_executor(None, input)

    client.is_active = False
    for task in [playback_task, capture_task]:
        if not task.done():
            task.cancel()
    await asyncio.gather(playback_task, capture_task, return_exceptions=True)

    if client.response_task and not client.response_task.done():
        client.response_task.cancel()

    await client.end_session()
    print("\nSession ended. Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
