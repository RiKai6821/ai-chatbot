"""TTS 自测：连说 3 句，验证「每句都有声音」+ 语速是否合适。

用法（在 venv 里，不需要麦克风）：
    .\\venv\\Scripts\\python.exe tts_test.py
想调语速：改下面的 RATE（默认 200，越大越快）。
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pyttsx3

RATE = 230   # 语速：默认 200，260 偏快，180 偏慢


def speak(text: str):
    print("播报：", text)
    engine = pyttsx3.init()                 # 每句新建引擎，避免只响第一句
    for v in engine.getProperty("voices"):
        if "chinese" in v.name.lower() or "huihui" in v.name.lower():
            engine.setProperty("voice", v.id)
            break
    engine.setProperty("rate", RATE)
    engine.say(text)
    engine.runAndWait()
    engine.stop()


if __name__ == "__main__":
    print(f"当前语速 RATE = {RATE}")
    speak("第一句，你好，我是小智。")
    speak("第二句，如果你能听到这句，说明只响一次的问题已经解决。")
    speak("第三句，觉得太快或太慢，就改脚本里的 RATE 数值。")
    print("测试完成：三句都应有声音。")
