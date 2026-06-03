"""TTS 子进程：从标准输入逐行读句子并朗读，可被主进程随时 kill 以实现打断。

协议（主进程 <-> 本进程，均为 UTF-8 文本行）：
  启动后本进程预热好 SAPI，打印一行 "READY"。
  主进程每写入一行句子，本进程朗读它，念完打印一行 "ACK"。
  主进程 kill 本进程即可瞬间停止朗读（用于打断）。
"""
import sys
import re

RATE = int(sys.argv[1]) if len(sys.argv) > 1 else 230
EMOJI = re.compile(
    r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️☀-⛿✀-➿]"
)

import pyttsx3   # 顶层导入，预热开销发生在进程启动阶段


def make_engine():
    e = pyttsx3.init()
    for v in e.getProperty("voices"):
        if "chinese" in v.name.lower() or "huihui" in v.name.lower():
            e.setProperty("voice", v.id)
            break
    e.setProperty("rate", RATE)
    return e


def main():
    make_engine()              # 预热：让 SAPI/COM 完成首次初始化
    sys.stdout.write("READY\n")
    sys.stdout.flush()

    for line in sys.stdin:     # 阻塞读，主进程写一行念一句
        text = EMOJI.sub("", line).strip()
        if text:
            engine = make_engine()   # 每句新建，避免「只响第一句」
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        sys.stdout.write("ACK\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
