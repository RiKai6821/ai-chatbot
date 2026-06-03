"""阶段3：语音对话（PC 版）——无缝播报 + 可打断(barge-in)。

设计：
- 生产者线程流式读大模型 → 切句 → 入队列（只操作队列，不碰 TTS 引擎）。
- 主线程从队列取句，凑成一批后用一个新引擎一次性 say + runAndWait → 批内无缝。
  批间只有 make_engine（约0ms）+ queue.get 的等待，几乎察觉不到。
- BargeMonitor 在另一线程监听麦克风，检测到说话就调当前引擎 stop() → 真打断。

依赖（在 venv 里）：
    .\\venv\\Scripts\\python.exe -m pip install -r requirements.txt -r requirements-voice.txt
运行：
    .\\venv\\Scripts\\python.exe voice.py
调试打断阈值（实时看麦克风能量）：
    $env:DEBUG_ENERGY=1; .\\venv\\Scripts\\python.exe voice.py
"""
import os
import re
import queue
import audioop
import tempfile
import threading

import config  # 自动加载 .env + 修复 Windows UTF-8 输出

import pyttsx3
import speech_recognition as sr
import dashscope
from dashscope.audio.asr import Recognition
from openai import OpenAI

dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

SYSTEM = (
    "你是一个friendly、生动的中文语音助手，名字叫小智，说话自然、有感情。\n"
    "根据场景调整篇幅：\n"
    "- 日常聊天、问答：口语化、简短，两三句话即可，别啰嗦。\n"
    "- 但当用户让你讲故事、讲笑话、唱歌、背诗、或详细解释时：要尽情展开，"
    "内容生动丰富、有情节有细节，别敷衍。讲故事要讲完整、有起承转合的一段；"
    "唱歌就把完整歌词一句句念出来。这种时候话多是对的。\n"
    "不要使用任何表情符号(emoji)，因为你的回答会被读出来。"
)
MODEL = "qwen-flash"
TTS_RATE = 230
ASR_RATE = 16000

ENDERS = re.compile(r"[。！？!?；;\n]")   # 只在句末断，不在逗号断
MIN_CHUNK = 6
EMOJI = re.compile(
    r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️☀-⛿✀-➿]"
)

rec = sr.Recognizer()
mic = sr.Microphone()
CHUNK = 1024

barge_threshold = 500
BARGE_HOLD  = 0.25   # 持续这么久(秒)才算数，过滤杂声
BARGE_GRACE = 0.5    # 每轮开头不检测的时间(秒)，防开口瞬间误杀
DEBUG_ENERGY = bool(os.getenv("DEBUG_ENERGY"))


# ── TTS 工具 ──────────────────────────────────────────────
def make_engine() -> pyttsx3.Engine:
    e = pyttsx3.init()
    for v in e.getProperty("voices"):
        if "chinese" in v.name.lower() or "huihui" in v.name.lower():
            e.setProperty("voice", v.id)
            break
    e.setProperty("rate", TTS_RATE)
    return e


# ── 语音识别 ──────────────────────────────────────────────
def transcribe(audio: sr.AudioData) -> str:
    wav = audio.get_wav_data(convert_rate=ASR_RATE, convert_width=2)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav)
        path = f.name
    try:
        r = Recognition(model="paraformer-realtime-v2", format="wav",
                        sample_rate=ASR_RATE, callback=None)
        res = r.call(path)
        sents = res.get_sentence()
        if isinstance(sents, list):
            return "".join(s.get("text", "") for s in sents)
        return sents.get("text", "") if sents else ""
    finally:
        os.remove(path)


# ── 打断监控 ──────────────────────────────────────────────
class BargeMonitor(threading.Thread):
    """后台监听麦克风能量；检测到持续人声就置位 detected 并 stop 当前引擎。"""

    def __init__(self, get_engine):
        """get_engine: 返回当前活动引擎的可调用对象（None 表示没有引擎在播）。"""
        super().__init__(daemon=True)
        self.get_engine = get_engine
        self.stop_flag  = threading.Event()
        self.detected   = threading.Event()
        self.emax = 0

    def run(self):
        need  = max(2, int(BARGE_HOLD  * mic.SAMPLE_RATE / CHUNK))
        grace = int(BARGE_GRACE * mic.SAMPLE_RATE / CHUNK)
        hot, frame_i = 0, 0
        try:
            with mic as source:
                while not self.stop_flag.is_set():
                    data   = source.stream.read(CHUNK, exception_on_overflow=False)
                    frame_i += 1
                    energy  = audioop.rms(data, 2)
                    self.emax = max(self.emax, energy)
                    if DEBUG_ENERGY and frame_i % 8 == 0:
                        print(f"\r[energy={energy:5d} 阈值={barge_threshold}]",
                              end="", flush=True)
                    if frame_i <= grace:
                        continue
                    hot = hot + 1 if energy > barge_threshold else 0
                    if hot >= need:
                        print(f"\n[检测到打断 energy={energy}]")
                        self.detected.set()
                        e = self.get_engine()
                        if e:
                            e.stop()         # 跨线程打断当前 runAndWait
                        return
        except Exception:
            return


# ── 核心回复播报 ──────────────────────────────────────────
def assistant_reply(messages):
    """生产者线程切句入队；主线程用微批方式取句连续播报；BargeMonitor 跨线打断。

    返回 (完整回复文本, 打断时录到的音频或 None)。
    """
    full_box    = [""]
    sent_q: queue.Queue = queue.Queue()
    prod_stop   = threading.Event()
    cur_engine  = [None]                  # 当前播报用的引擎（供 BargeMonitor）

    # ── 生产者：只写队列，不碰引擎 ──
    def produce():
        buf = ""
        try:
            stream = client.chat.completions.create(
                model=MODEL, messages=messages, temperature=0.8, stream=True,
            )
            for chunk in stream:
                if prod_stop.is_set():
                    return
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                full_box[0] += delta
                print(delta, end="", flush=True)
                buf += delta
                while True:
                    cut = -1
                    for m in ENDERS.finditer(buf):
                        if m.end() >= MIN_CHUNK:
                            cut = m.end(); break
                    if cut < 0:
                        break
                    s = EMOJI.sub("", buf[:cut]).strip()
                    buf = buf[cut:]
                    if s:
                        sent_q.put(s)
            if buf.strip() and not prod_stop.is_set():
                s = EMOJI.sub("", buf).strip()
                if s:
                    sent_q.put(s)
        finally:
            sent_q.put(None)              # 结束哨兵

    threading.Thread(target=produce, daemon=True).start()

    monitor = BargeMonitor(lambda: cur_engine[0])
    monitor.start()
    print("小智：", end="", flush=True)

    # ── 主线程：微批播报（批内无缝，批间几乎无感） ──
    stream_done = False
    while not stream_done and not monitor.detected.is_set():
        # 等第一句就绪
        item = sent_q.get()
        if item is None:
            break

        # 非阻塞地排空队列，凑成一批
        batch = [item]
        while True:
            try:
                nxt = sent_q.get_nowait()
                if nxt is None:
                    stream_done = True; break
                batch.append(nxt)
            except queue.Empty:
                break

        if monitor.detected.is_set():
            break

        # 这批句子用一个引擎一次性播完（批内真正无缝）
        engine = make_engine()
        cur_engine[0] = engine
        for s in batch:
            engine.say(s)
        engine.runAndWait()
        engine.stop()
        cur_engine[0] = None

    print()
    prod_stop.set()
    monitor.stop_flag.set()
    monitor.join(timeout=1)

    if DEBUG_ENERGY:
        print(f"[本轮最大能量={monitor.emax} 阈值={barge_threshold}]")

    interrupted_audio = None
    if monitor.detected.is_set():
        with mic as source:
            print("（打断）🎤 我在听…")
            interrupted_audio = rec.listen(source, phrase_time_limit=15)

    return full_box[0], interrupted_audio


# ── 主循环 ────────────────────────────────────────────────
def listen_once() -> sr.AudioData:
    with mic as source:
        print("\n🎤 请说话…")
        return rec.listen(source, phrase_time_limit=15)


def main():
    print("正在校准环境噪音，请保持安静…")
    with mic as source:
        rec.adjust_for_ambient_noise(source, duration=1)
    global barge_threshold
    barge_threshold = max(500, int(rec.energy_threshold * 1.6))
    print(f"就绪（打断阈值={barge_threshold}）。语音对话开始（Ctrl+C 退出）")

    messages      = [{"role": "system", "content": SYSTEM}]
    pending_audio = None
    try:
        while True:
            audio = pending_audio if pending_audio is not None else listen_once()
            pending_audio = None
            text = transcribe(audio)
            if not text.strip():
                print("没听清，请再说一次…")
                continue
            print(f"你：{text}")
            messages.append({"role": "user", "content": text})
            reply, interrupted_audio = assistant_reply(messages)
            messages.append({"role": "assistant", "content": reply})
            if interrupted_audio is not None:
                pending_audio = interrupted_audio
    except KeyboardInterrupt:
        print("\n再见！")


if __name__ == "__main__":
    main()
