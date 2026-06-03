"""/voice 接口用到的语音零件：STT(Paraformer 听) + TTS(CosyVoice 说)。

单独成模块、并在 api_server.py 里"惰性导入"，好处是：只装了 requirements.txt
（没装 requirements-voice.txt）的人，仍能正常启动基础的 /chat 等接口；只有真正
调用 /voice 时才需要语音依赖（dashscope）。

音频统一：16kHz / 16bit / 单声道 —— 和设备端 INMP441/MAX98357A 一致。
"""
import io
import os
import wave
import tempfile

import dashscope
from dashscope.audio.asr import Recognition

dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")

ASR_RATE = 16000
TTS_VOICE = "longxiaochun"     # CosyVoice 音色，可换 longwan/longcheng 等


# ── 听：把一段 WAV（路径）转成文字 ─────────────────────────
def stt_from_file(wav_path: str) -> str:
    r = Recognition(model="paraformer-realtime-v2", format="wav",
                    sample_rate=ASR_RATE, callback=None)
    res = r.call(wav_path)
    sents = res.get_sentence()
    if isinstance(sents, list):
        return "".join(s.get("text", "") for s in sents)
    return sents.get("text", "") if sents else ""


def stt_from_bytes(wav_bytes: bytes) -> str:
    """设备发来的是 WAV 字节流；落临时文件再交给 Paraformer。"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        path = f.name
    try:
        return stt_from_file(path)
    finally:
        os.remove(path)


# ── 说：把文字合成成 16k 单声道 PCM，再包成标准 WAV ─────────
def tts_pcm(text: str) -> bytes:
    """返回裸 PCM（16kHz/16bit/单声道）。"""
    from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
    synth = SpeechSynthesizer(
        model="cosyvoice-v1",
        voice=TTS_VOICE,
        format=AudioFormat.PCM_16000HZ_MONO_16BIT,
    )
    return synth.call(text)


def pcm_to_wav(pcm: bytes, rate: int = ASR_RATE) -> bytes:
    """给 PCM 加上标准 44 字节 WAV 头（设备播放端默认跳过这 44 字节）。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)       # 16bit = 2 bytes
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def tts_wav(text: str) -> bytes:
    """文字 → 可直接回给设备/浏览器的 WAV 字节。"""
    return pcm_to_wav(tts_pcm(text))
