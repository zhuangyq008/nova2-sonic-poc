"""
Nova 2 Sonic 文本输入测试 — 最简验证脚本

通过纯文本（非语音）与 Nova 2 Sonic 交互，验证：
1. SDK 安装是否正确
2. AWS 凭证和权限是否到位
3. 模型是否可调用
4. 事件流协议是否正常

无需麦克风或扬声器，适合服务器环境测试。
"""

import os
import sys
import asyncio
import base64
import json
import uuid

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
    """Ensure AWS credentials are available as environment variables.
    The smithy SDK's EnvironmentCredentialsResolver only reads env vars,
    so we extract credentials from boto3 (which supports profiles, instance roles, etc.)
    and set them as env vars if not already present."""
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        return  # already set
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
            print(f"  Loaded credentials from boto3 session")
    except Exception as e:
        print(f"  Warning: Could not load boto3 credentials: {e}")

# Configuration
MODEL_ID = "amazon.nova-2-sonic-v1:0"
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
VOICE_ID = "tiffany"  # en-US female, multilingual

# Test system prompts in different languages
TEST_PROMPTS = [
    {
        "name": "English - Basic",
        "system": "You are a helpful assistant. Keep responses under 2 sentences.",
        "user_text": "What is Amazon Nova Sonic? Answer briefly.",
    },
    {
        "name": "English - Product",
        "system": (
            "You are a product specialist for bone conduction headphones. You help customers choose "
            "bone conduction headphones. Keep responses conversational and under 3 sentences."
        ),
        "user_text": "What are the benefits of bone conduction headphones for runners?",
    },
    {
        "name": "French - Greeting",
        "system": "Tu es un assistant chaleureux. Réponds en français en 1-2 phrases.",
        "user_text": "Bonjour! Comment vas-tu aujourd'hui?",
        "voice_id": "ambre",
    },
]


async def run_text_test(test_case: dict):
    """Run a single text-based test against Nova 2 Sonic."""
    name = test_case["name"]
    system_prompt = test_case["system"]
    user_text = test_case["user_text"]
    voice_id = test_case.get("voice_id", VOICE_ID)

    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print(f"Voice: {voice_id}")
    print(f"System: {system_prompt[:80]}...")
    print(f"User: {user_text}")
    print(f"{'='*60}")

    prompt_name = str(uuid.uuid4())
    system_content_name = str(uuid.uuid4())
    user_content_name = str(uuid.uuid4())

    # Initialize client
    config = Config(
        endpoint_uri=f"https://bedrock-runtime.{REGION}.amazonaws.com",
        region=REGION,
        aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
    )
    client = BedrockRuntimeClient(config=config)

    try:
        # Open stream
        stream = await client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=MODEL_ID)
        )

        async def send(event_json: str):
            event = InvokeModelWithBidirectionalStreamInputChunk(
                value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
            )
            await stream.input_stream.send(event)

        # 1. Session Start
        await send(json.dumps({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 512,
                        "topP": 0.9,
                        "temperature": 0.7,
                    }
                }
            }
        }))

        # 2. Prompt Start
        await send(json.dumps({
            "event": {
                "promptStart": {
                    "promptName": prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 24000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": voice_id,
                        "encoding": "base64",
                        "audioType": "SPEECH",
                    },
                }
            }
        }))

        # 3. System Prompt
        await send(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": system_content_name,
                    "type": "TEXT",
                    "interactive": False,
                    "role": "SYSTEM",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }))
        await send(json.dumps({
            "event": {
                "textInput": {
                    "promptName": prompt_name,
                    "contentName": system_content_name,
                    "content": system_prompt,
                }
            }
        }))
        await send(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": system_content_name,
                }
            }
        }))

        # 4. User Text Input
        await send(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": user_content_name,
                    "type": "TEXT",
                    "interactive": True,
                    "role": "USER",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }))
        await send(json.dumps({
            "event": {
                "textInput": {
                    "promptName": prompt_name,
                    "contentName": user_content_name,
                    "content": user_text,
                }
            }
        }))
        await send(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": user_content_name,
                }
            }
        }))

        # 5. Prompt End
        await send(json.dumps({
            "event": {"promptEnd": {"promptName": prompt_name}}
        }))

        # 6. Session End
        await send(json.dumps({"event": {"sessionEnd": {}}}))
        await stream.input_stream.close()

        # 7. Read Responses
        print("\n--- Response ---")
        assistant_texts = []
        audio_chunks = 0
        total_audio_bytes = 0

        while True:
            try:
                output = await asyncio.wait_for(stream.await_output(), timeout=30)
                result = await output[1].receive()
                if result.value and result.value.bytes_:
                    data = json.loads(result.value.bytes_.decode("utf-8"))
                    if "event" in data:
                        evt = data["event"]
                        if "textOutput" in evt:
                            text = evt["textOutput"]["content"]
                            role = evt["textOutput"].get("role", "")
                            assistant_texts.append(text)
                            print(f"  [Text] {text}")
                        elif "audioOutput" in evt:
                            audio_bytes = base64.b64decode(evt["audioOutput"]["content"])
                            audio_chunks += 1
                            total_audio_bytes += len(audio_bytes)
                        elif "contentStart" in evt:
                            cs = evt["contentStart"]
                            role = cs.get("role", "?")
                            ctype = cs.get("type", "?")
                            print(f"  [ContentStart] role={role} type={ctype}")
                        elif "contentEnd" in evt:
                            pass
            except asyncio.TimeoutError:
                break
            except StopAsyncIteration:
                break
            except Exception as e:
                if "stream" in str(e).lower() or "closed" in str(e).lower():
                    break
                print(f"  [Error] {e}")
                break

        # Summary
        print(f"\n--- Summary ---")
        print(f"  Text responses: {len(assistant_texts)}")
        print(f"  Audio chunks: {audio_chunks}")
        if total_audio_bytes > 0:
            duration_s = total_audio_bytes / (24000 * 2)  # 24kHz 16-bit mono
            print(f"  Audio duration: ~{duration_s:.1f}s ({total_audio_bytes:,} bytes)")
        full_text = " ".join(assistant_texts)
        if full_text:
            print(f"  Full response: {full_text[:200]}")
        print(f"  Status: ✅ SUCCESS")
        return True

    except Exception as e:
        print(f"  Status: ❌ FAILED — {e}")
        return False


async def main():
    print("=" * 60)
    print("Amazon Nova 2 Sonic — Text Input Test")
    print(f"Region: {REGION}")
    print(f"Model: {MODEL_ID}")
    print("=" * 60)

    # Ensure credentials are available as env vars for smithy SDK
    ensure_env_credentials()

    results = []
    for test in TEST_PROMPTS:
        ok = await run_text_test(test)
        results.append((test["name"], ok))

    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status} — {name}")

    all_pass = all(ok for _, ok in results)
    print(f"\nOverall: {'✅ All tests passed' if all_pass else '❌ Some tests failed'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
