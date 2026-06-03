"""麦克风自测：尝试打开默认麦克风并录 2 秒，报告成功/失败。

用法（在 venv 里）：
    .\\venv\\Scripts\\python.exe mic_test.py
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pyaudio

pa = pyaudio.PyAudio()
print("默认主机 API:", pa.get_default_host_api_info()["name"])

ok = False
for idx in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(idx)
    if info["maxInputChannels"] < 1:
        continue
    rate = int(info["defaultSampleRate"])
    try:
        stream = pa.open(
            input_device_index=idx, channels=1, format=pyaudio.paInt16,
            rate=rate, frames_per_buffer=1024, input=True,
        )
        print(f"✅ 成功打开麦克风 [idx={idx}] {info['name']} rate={rate}")
        print("   录音 2 秒…请说话")
        vol_max = 0
        for _ in range(int(rate / 1024 * 2)):
            data = stream.read(1024, exception_on_overflow=False)
            vol_max = max(vol_max, max(abs(int.from_bytes(data[i:i+2], "little", signed=True))
                                       for i in range(0, len(data), 2)))
        stream.stop_stream()
        stream.close()
        print(f"   录音完成。检测到的最大音量: {vol_max} (说话时应明显 > 500)")
        ok = True
        break
    except Exception as e:
        print(f"❌ [idx={idx}] {info['name']}: {e}")

pa.terminate()

if ok:
    print("\n🎉 麦克风可用！现在可以跑 voice.py 了。")
else:
    print("\n⚠️ 所有麦克风都打不开 —— 仍是系统/硬件问题，按清单继续排查。")
