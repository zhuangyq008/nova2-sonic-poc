"""
生成测试用音频文件。

包括：
1. 合成信号（正弦波、静音）— 用于基础连通性测试
2. 真实语音（通过 Amazon Polly TTS）— 用于完整功能测试

实际客户测试建议使用真实录制的语音文件（16kHz, 16-bit, mono PCM）。
"""

import numpy as np
import os
import subprocess
import sys

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audio")
SAMPLE_RATE = 16000


def generate_sine_wave(frequency: float, duration: float, sample_rate: int = 16000) -> bytes:
    """Generate a sine wave as 16-bit PCM bytes."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    wave = 0.3 * np.sin(2 * np.pi * frequency * t)
    wave += 0.15 * np.sin(2 * np.pi * frequency * 2 * t)
    wave += 0.1 * np.sin(2 * np.pi * frequency * 3 * t)
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)
    wave = wave * envelope
    wave = np.clip(wave, -1, 1)
    pcm_data = (wave * 32767).astype(np.int16)
    return pcm_data.tobytes()


def generate_silence(duration: float, sample_rate: int = 16000) -> bytes:
    """Generate silence as 16-bit PCM bytes."""
    return b'\x00\x00' * int(sample_rate * duration)


def save_pcm_file(filepath: str, audio_bytes: bytes):
    """Save raw PCM audio to file."""
    with open(filepath, 'wb') as f:
        f.write(audio_bytes)
    print(f"  Saved: {filepath} ({len(audio_bytes)} bytes, {len(audio_bytes) / 2 / SAMPLE_RATE:.1f}s)")


def save_wav_file(filepath: str, audio_bytes: bytes, sample_rate: int = 16000):
    """Save PCM audio as WAV file for easy playback verification."""
    import wave
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_bytes)
    print(f"  Saved: {filepath} (WAV format)")


def generate_polly_speech(text: str, output_path: str, voice_id: str = "Matthew",
                          region: str = "us-east-1") -> bool:
    """Generate speech using Amazon Polly (requires AWS CLI configured)."""
    try:
        result = subprocess.run([
            "aws", "polly", "synthesize-speech",
            "--output-format", "pcm",
            "--sample-rate", "16000",
            "--voice-id", voice_id,
            "--text", text,
            "--region", region,
            output_path
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            size = os.path.getsize(output_path)
            dur = size / (SAMPLE_RATE * 2)
            print(f"  Saved: {output_path} ({size} bytes, {dur:.1f}s) [Polly: {voice_id}]")
            return True
        else:
            print(f"  ⚠️ Polly failed: {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        print(f"  ⚠️ AWS CLI not found — skipping Polly speech generation")
        return False
    except Exception as e:
        print(f"  ⚠️ Polly error: {e}")
        return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Generating test audio files...\n")

    # 1. Synthetic signals
    print("[1/5] Generating silence...")
    save_pcm_file(os.path.join(OUTPUT_DIR, "silence_3s.pcm"), generate_silence(3))

    print("[2/5] Generating tone signal...")
    save_pcm_file(os.path.join(OUTPUT_DIR, "tone_440hz_3s.pcm"), generate_sine_wave(440, 3))

    print("[3/5] Generating speech-like signal...")
    speech_like = generate_sine_wave(150, 3)
    save_pcm_file(os.path.join(OUTPUT_DIR, "speech_like_3s.pcm"), speech_like)
    save_wav_file(os.path.join(OUTPUT_DIR, "speech_like_3s.wav"), speech_like)

    # 2. Real speech via Amazon Polly
    print("[4/5] Generating English speech (Polly)...")
    generate_polly_speech(
        "Hello, I'm interested in learning about bone conduction headphones. "
        "Can you tell me about the benefits for runners?",
        os.path.join(OUTPUT_DIR, "test_speech_en.pcm"),
        voice_id="Matthew"
    )

    print("[5/5] Generating French speech (Polly)...")
    generate_polly_speech(
        "Bonjour, je voudrais en savoir plus sur les casques à conduction osseuse. "
        "Quels sont les avantages pour le sport?",
        os.path.join(OUTPUT_DIR, "test_speech_fr.pcm"),
        voice_id="Mathieu"
    )

    print(f"\nDone! Files saved to: {OUTPUT_DIR}")
    print("\n📌 Tips:")
    print("  - Use test_speech_en.pcm / test_speech_fr.pcm for real functionality tests")
    print("  - Use silence/tone files for basic connectivity tests")
    print("  - To record your own speech:")
    print("    ffmpeg -i input.mp3 -ar 16000 -ac 1 -f s16le -acodec pcm_s16le output.pcm")


if __name__ == "__main__":
    main()
