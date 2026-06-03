"""只测「TTS 子进程能不能出声」——不涉及麦克风、不涉及打断。

用法：
    .\\venv\\Scripts\\python.exe worker_audio_test.py
预期：你应能听到三句话。听到 = 子进程播报正常，问题在打断检测。
"""
import sys
import time
import subprocess

PY = sys.executable

print("启动 TTS 子进程并预热…")
p = subprocess.Popen(
    [PY, "tts_worker.py", "230"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    text=True, encoding="utf-8", bufsize=1,
)
ready = p.stdout.readline().strip()
print("子进程状态:", ready)

for s in ["第一句，你好，我是小智。", "第二句，如果你听到这句，说明播报正常。",
          "第三句，那问题就出在打断检测上。"]:
    t = time.time()
    p.stdin.write(s + "\n")
    p.stdin.flush()
    ack = p.stdout.readline().strip()
    print(f"  念《{s}》  耗时 {time.time()-t:.1f}s  {ack}")

p.kill()
print("测试完成：你听到几句？(0 句 / 3 句都听到 告诉我)")
