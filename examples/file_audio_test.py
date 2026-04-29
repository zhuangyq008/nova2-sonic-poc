"""
Nova 2 Sonic 音频文件输入测试

从 PCM/WAV 文件读取音频，发送给 Nova 2 Sonic，接收文本和音频响应。
基于 AWS 官方示例代码适配，适合无麦克风的服务器环境测试。

用法:
  python3 file_audio_test.py                       # 使用默认测试音频
  python3 file_audio_test.py path/to/audio.pcm     # 指定 PCM 文件（16kHz 16-bit mono）
  python3 file_audio_test.py path/to/audio.wav      # 指定 WAV 文件
"""

import os
import sys
import asyncio
import base64
import json
import uuid
import wave

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

# Configuration
MODEL_ID = "amazon.nova-2-sonic-v1:0"
REGION = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
VOICE_ID = "tiffany"
CHUNK_SIZE = 1024
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audio")


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
            print("  Loaded credentials from boto3 session")
    except Exception as e:
        print(f"  Warning: Could not load boto3 credentials: {e}")


def load_audio_file(filepath: str) -> bytes:
    """Load audio from PCM or WAV file."""
    if filepath.endswith(".wav"):
        with wave.open(filepath, "rb") as wf:
            assert wf.getnchannels() == 1, f"Expected mono, got {wf.getnchannels()} channels"
            assert wf.getsampwidth() == 2, f"Expected 16-bit, got {wf.getsampwidth()*8}-bit"
            return wf.readframes(wf.getnframes())
    else:
        with open(filepath, "rb") as f:
            return f.read()


class NovaSonicFileTest:
    """Test Nova 2 Sonic with audio file input (no microphone needed)."""

    def __init__(self, region=REGION, voice_id=VOICE_ID):
        self.region = region
        self.voice_id = voice_id
        self.model_id = MODEL_ID
        self.client = None
        self.stream = None
        self.is_active = False
        self.prompt_name = str(uuid.uuid4())
        self.system_content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())
        # Results
        self.role = None
        self.display_assistant_text = False
        self.texts = []
        self.audio_chunks_count = 0
        self.total_audio_bytes = 0
        self.output_audio = bytearray()
        self.errors = []

    def _init_client(self):
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        self.client = BedrockRuntimeClient(config=config)

    async def _send(self, event_json: str):
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )
        await self.stream.input_stream.send(event)

    async def _send_dict(self, event_dict: dict):
        await self._send(json.dumps(event_dict))

    async def _process_responses(self):
        """Process response events from the model (runs concurrently)."""
        try:
            while self.is_active:
                try:
                    output = await asyncio.wait_for(self.stream.await_output(), timeout=15)
                    result = await output[1].receive()
                    if not (result.value and result.value.bytes_):
                        continue

                    raw = result.value.bytes_.decode("utf-8")
                    data = json.loads(raw)

                    if "event" not in data:
                        print(f"  [Unknown] {raw[:200]}")
                        continue

                    evt = data["event"]

                    if "contentStart" in evt:
                        cs = evt["contentStart"]
                        self.role = cs.get("role", "")
                        if "additionalModelFields" in cs:
                            fields = json.loads(cs["additionalModelFields"])
                            self.display_assistant_text = fields.get("generationStage") == "SPECULATIVE"
                        else:
                            self.display_assistant_text = False

                    elif "textOutput" in evt:
                        text = evt["textOutput"]["content"]
                        self.texts.append({"role": self.role or "", "text": text})
                        if self.role == "USER":
                            print(f"  🎤 ASR: {text}")
                        elif self.role == "ASSISTANT" and self.display_assistant_text:
                            print(f"  🤖 Assistant: {text}")

                    elif "audioOutput" in evt:
                        audio_bytes = base64.b64decode(evt["audioOutput"]["content"])
                        self.audio_chunks_count += 1
                        self.total_audio_bytes += len(audio_bytes)
                        self.output_audio.extend(audio_bytes)

                except asyncio.TimeoutError:
                    break

        except StopAsyncIteration:
            pass
        except Exception as e:
            err_str = str(e)
            if "closed" not in err_str.lower():
                self.errors.append(err_str)
                print(f"  [Error] {e}")

    async def run(self, audio_path: str, system_prompt: str = None):
        """Run the full test."""
        if system_prompt is None:
            system_prompt = (
                "You are a warm, professional, and helpful AI assistant. "
                "Give accurate answers that sound natural, direct, and human. "
                "Keep responses under 3 sentences."
            )

        audio_data = load_audio_file(audio_path)
        duration_s = len(audio_data) / (INPUT_SAMPLE_RATE * 2)
        print(f"\n  Audio: {audio_path}")
        print(f"  Duration: {duration_s:.1f}s ({len(audio_data):,} bytes)")
        print(f"  Voice: {self.voice_id} | Region: {self.region}")

        self._init_client()
        self.stream = await self.client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True

        # === 1. Session Start ===
        await self._send_dict({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7,
                    }
                }
            }
        })

        # === 2. Prompt Start ===
        await self._send_dict({
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
        })

        # === 3. System Prompt (interactive=false) ===
        await self._send_dict({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.system_content_name,
                    "type": "TEXT",
                    "interactive": False,
                    "role": "SYSTEM",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        })
        await self._send_dict({
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.system_content_name,
                    "content": system_prompt,
                }
            }
        })
        await self._send_dict({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.system_content_name,
                }
            }
        })

        # === Start receiving responses concurrently ===
        recv_task = asyncio.create_task(self._process_responses())

        # === 4. Audio Input (interactive=true) ===
        await self._send_dict({
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
        })

        # Send audio in chunks (pacing to ~real-time)
        print("\n  Sending audio...")
        offset = 0
        chunks_sent = 0
        while offset < len(audio_data):
            chunk = audio_data[offset : offset + CHUNK_SIZE]
            blob = base64.b64encode(chunk).decode("utf-8")
            await self._send_dict({
                "event": {
                    "audioInput": {
                        "promptName": self.prompt_name,
                        "contentName": self.audio_content_name,
                        "content": blob,
                    }
                }
            })
            offset += CHUNK_SIZE
            chunks_sent += 1
            # Pace at ~half real-time
            await asyncio.sleep(CHUNK_SIZE / (INPUT_SAMPLE_RATE * 2) * 0.5)

        print(f"  Sent {chunks_sent} audio chunks")

        # Send trailing silence to help VAD detect end of speech
        silence = bytes(INPUT_SAMPLE_RATE * 2 * 2)  # 2 seconds of silence
        for i in range(0, len(silence), CHUNK_SIZE):
            chunk = silence[i : i + CHUNK_SIZE]
            blob = base64.b64encode(chunk).decode("utf-8")
            await self._send_dict({
                "event": {
                    "audioInput": {
                        "promptName": self.prompt_name,
                        "contentName": self.audio_content_name,
                        "content": blob,
                    }
                }
            })
            await asyncio.sleep(0.01)
        print("  Sent trailing silence for VAD")

        # End audio content
        await self._send_dict({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                }
            }
        })

        # Wait for model to process (VAD + generation)
        print("  Waiting for model response...")
        await asyncio.sleep(12)

        # === 5. Close session ===
        self.is_active = False
        try:
            await self._send_dict({"event": {"promptEnd": {"promptName": self.prompt_name}}})
            await self._send_dict({"event": {"sessionEnd": {}}})
            await self.stream.input_stream.close()
        except Exception:
            pass

        # Wait for receiver
        await asyncio.sleep(2)
        if not recv_task.done():
            recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass

        # Save output audio
        if self.output_audio:
            out_path = os.path.join(AUDIO_DIR, "response_output.wav")
            os.makedirs(AUDIO_DIR, exist_ok=True)
            with wave.open(out_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(OUTPUT_SAMPLE_RATE)
                wf.writeframes(bytes(self.output_audio))
            print(f"\n  Output audio saved: {out_path}")

        # Print summary
        print(f"\n{'='*50}")
        print(f"  Summary")
        print(f"{'='*50}")
        print(f"  ASR/Text outputs: {len(self.texts)}")
        for t in self.texts:
            label = "ASR" if t["role"] == "USER" else "Assistant"
            print(f"    [{label}] {t['text'][:150]}")
        print(f"  Audio chunks: {self.audio_chunks_count}")
        if self.total_audio_bytes > 0:
            out_dur = self.total_audio_bytes / (OUTPUT_SAMPLE_RATE * 2)
            print(f"  Output audio: ~{out_dur:.1f}s ({self.total_audio_bytes:,} bytes)")
        if self.errors:
            # Filter out stream-close errors (normal during shutdown)
            real_errors = [e for e in self.errors if "Invalid input" not in e]
            if real_errors:
                print(f"  Errors: {len(real_errors)}")
                for e in real_errors:
                    print(f"    - {e[:150]}")

        has_response = len(self.texts) > 0 or self.audio_chunks_count > 0
        if has_response:
            print(f"\n  ✅ SUCCESS — Model responded")
        elif self.errors:
            print(f"\n  ❌ FAILED — Errors occurred")
        else:
            print(f"\n  ⚠️  No response — synthetic audio may not trigger ASR/VAD")
            print(f"     Try with real speech audio (record via ffmpeg or use a WAV file)")
        return has_response


async def main():
    print("=" * 60)
    print("Amazon Nova 2 Sonic — Audio File Test")
    print("=" * 60)

    ensure_env_credentials()

    if len(sys.argv) > 1:
        audio_path = sys.argv[1]
        if not os.path.exists(audio_path):
            print(f"Error: File not found: {audio_path}")
            return 1
    else:
        # Prefer real speech, fall back to synthetic
        for name in ["test_speech_en.pcm", "test_speech_polly.pcm", "speech_like_3s.pcm"]:
            audio_path = os.path.join(AUDIO_DIR, name)
            if os.path.exists(audio_path):
                break
        else:
            print("Test audio not found. Run generate_test_audio.py first:")
            print("  python3 generate_test_audio.py")
            return 1

    tester = NovaSonicFileTest()
    ok = await tester.run(audio_path)
    return 0 if ok else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
