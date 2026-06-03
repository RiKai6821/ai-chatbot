# 小智 · 端云协同 AI 语音助手

一个**端云协同**的 AI 语音助手：嵌入式设备（ESP32-S3）做"瘦客户端"负责收音/播报/表情，云端服务负责语音识别、大模型对话与语音合成。一个项目串起**嵌入式固件**与 **AI Agent 服务**两条完整技术线。

> 在线仓库：https://github.com/RiKai6821/ai-chatbot

## 架构

```
 ┌────────────── 设备端（ESP32-S3, C / ESP-IDF）──────────────┐        ┌──────── 云端（Python）────────┐
 │ 按键唤醒 → INMP441 录音(I2S/DMA) ─────── WiFi/HTTP ───────▶ │  /voice │ STT(Paraformer) → 大模型 → TTS │
 │ GC9A01 圆屏表情(esp_lcd) ◀── 状态机 ──── MAX98357A 播放 ◀── │ ◀────── │  + 工具调用 / RAG / 记忆        │
 └────────────────────────────────────────────────────────────┘        └────────────────────────────────┘
   设备只负责"听/说/显示"，不跑大模型                                      大脑在云端：会聊、能办事、可检索资料
```

## 技术栈

| 层 | 技术 |
|----|------|
| 嵌入式 | C / **ESP-IDF v5.x**、FreeRTOS、CMake/Kconfig、组件化(BSP)、**I2S+DMA**、**esp_lcd(SPI)**、GPIO 中断、esp_http_client、cJSON |
| 云端服务 | Python、**FastAPI**、SSE 流式、SQLite 持久化 |
| AI / Agent | DashScope(通义千问, OpenAI 兼容)、**Function Calling**、**RAG**(text-embedding-v3)、Paraformer(STT)、CosyVoice(TTS) |
| 工程化 | 评测框架(LLM 裁判 + CI)、结构化日志/trace 可观测性、Git |

## 两条技术线（均已实现并验证）

### 🔧 嵌入式固件 — `firmware-idf/`（ESP-IDF 纯 C，工程化）
- **共享 BSP 组件**（`bsp_wifi` / `bsp_audio` / `bsp_display`）+ 4 个应用，多应用复用底层。
- 覆盖考点：esp_wifi 事件驱动、**I2S 录音/播放 + DMA**、**esp_lcd 圆屏(分带渲染省内存)**、FreeRTOS 多任务、**GPIO 中断→队列**、状态机、HTTP 流式双向音频。
- 旗舰应用 `esp32_voice_assistant`：按键→录音→`/voice`→播放，表情随状态同步。
- （`firmware/` 是更早的 Arduino 原型版，保留以展示"原型→工程化"的演进。）

### 🤖 AI Agent 服务 — 根目录 Python
- `api_server.py`：`/chat`、`/chat/stream`(SSE)、`/agent`(工具调用)、`/voice`(语音进出)，含上下文压缩与会话持久化。
- `tools.py` + `agent.py`：**函数调用闭环**（时间/天气/计算/知识检索），命令行与 HTTP 共用。
- `rag.py` + `knowledge/`：**RAG 检索增强**，让助手据私有资料作答而非瞎编。
- `eval_agent.py` + `evals/`：**评测框架**（工具选择 + 关键词 + LLM 裁判，退出码接 CI）。
- `tracing.py`：**结构化日志/可观测性**（每轮 token、工具耗时、延迟 p50/p95）。

## 仓库结构

```
ai-chatbot/
├── api_server.py        # FastAPI 服务：/chat /chat/stream /agent /voice
├── chat.py / agent.py   # 命令行：对话 / 工具调用 Agent
├── tools.py             # 工具定义 + 调用闭环（HTTP 与命令行共用）
├── rag.py  knowledge/   # RAG 检索 + 私有知识库
├── eval_agent.py evals/ # Agent 评测框架
├── tracing.py           # 结构化日志/可观测性
├── voice.py voice_server.py # PC 语音对话 / 语音接口零件(STT+TTS)
├── store.py config.py   # 会话持久化 / .env 加载
├── firmware-idf/        # ESP-IDF 纯 C 固件（BSP 组件 + 4 应用）★
└── firmware/            # Arduino 原型固件
```

## 快速上手（云端，3 步，不需要硬件）

```bash
pip install -r requirements.txt
cp .env.example .env          # 填入 DASHSCOPE_API_KEY
uvicorn api_server:app --host 0.0.0.0 --port 8000   # 打开 /docs 测试
```
命令行体验：`python chat.py`（对话）、`python agent.py`（能办事）、`python eval_agent.py --judge`（评测）。
设备端固件构建见 [`firmware-idf/README.md`](firmware-idf/README.md)。

## 部署（Docker）

```bash
cp .env.example .env          # 填入 DASHSCOPE_API_KEY
docker compose up -d --build  # 起服务，端口 8000
# 或不用 compose：
# docker build -t xiaozhi-api . && docker run -p 8000:8000 --env-file .env xiaozhi-api
```
- 镜像基于 `python:3.12-slim`，非 root 运行，带 `HEALTHCHECK`。
- 会话库/日志/RAG 索引通过 `XZ_DATA_DIR` 落在挂载卷 `xz-data`，容器重建不丢记忆。
- 韧性参数（并发/超时/背压）可用环境变量覆盖，见 `resilience.py` 与 `docker-compose.yml`。
- `DASHSCOPE_API_KEY` 仅运行时由 `.env` 注入，不打进镜像。

---

# 附录：从 0 开始搭建指南（教程）

> 下面是项目最初的分阶段教程（文字对话 → HTTP 接口 → 语音 → 单片机接入），每阶段都能独立跑通，保留作学习参考。

一个循序渐进的项目：从命令行文字对话，到语音对话，最终接入单片机/边缘设备。
核心原则：**大脑（大模型）在云端/电脑，设备只是"瘦客户端"**——设备只负责收输入、显示/播报，思考交给服务器。

---

## 🎯 最终形态

操作员 ⇄ 设备(屏幕/语音)  →  你的电脑/服务器(/chat 接口)  →  大模型(通义千问)
瘦客户端                  对话大脑 + 记忆                  生成回复



## 🪜 分阶段目标（每阶段独立可用）

- **阶段0**：命令行文字对话（多轮记忆）—— 30 分钟跑通
- **阶段1**：流式输出（边生成边显示，体验更像真人）
- **阶段2**：做成 `POST /chat` HTTP 接口（任何前端/设备都能连）
- **阶段3**：语音对话（麦克风听 + 喇叭说，先在电脑跑）
- **阶段4**：单片机/边缘设备接入（设备只发 HTTP）

---

## 0. 前置准备

1. **装 Python 3.10+**：https://www.python.org/
2. **申请大模型 API Key**（这里用阿里云百炼，兼容 OpenAI 接口）：
   - 注册 https://bailian.console.aliyun.com/ → 开通 → 创建 API-KEY（形如 `sk-xxxx`）
3. **建项目文件夹**并进入：
   ```bash
   mkdir ai-chatbot && cd ai-chatbot
1. 项目结构（先建好这些空文件）

ai-chatbot/
├── .env                # 存 API Key（不提交到 git）
├── .gitignore
├── requirements.txt    # 依赖
├── config.py           # 读取 .env
├── chat.py             # 阶段0/1：命令行对话
├── api_server.py       # 阶段2：HTTP 接口
└── voice.py            # 阶段3：语音对话
2. 配置文件
.env（把 key 填进去，这个文件别外传）


DASHSCOPE_API_KEY=sk-你的key
.gitignore


.env
__pycache__/
*.pyc
venv/
requirements.txt


openai>=1.40.0
fastapi>=0.110.0
uvicorn>=0.27.0
config.py（无第三方依赖地加载 .env）


import os

def load_env():
    if os.path.exists(".env"):
        for line in open(".env", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()
if not os.getenv("DASHSCOPE_API_KEY"):
    raise SystemExit("请在 .env 里填 DASHSCOPE_API_KEY")
安装依赖：


pip install -r requirements.txt
3. 阶段0：命令行多轮对话
chat.py


import os
import config  # 自动加载 .env
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

SYSTEM = "你是一个友好、简洁的中文 AI 助手，名字叫小智。"

def main():
    messages = [{"role": "system", "content": SYSTEM}]
    print("开始对话（输入 quit 退出）")
    while True:
        user = input("\n你：").strip()
        if user.lower() in ("quit", "exit", "q"):
            break
        messages.append({"role": "user", "content": user})
        resp = client.chat.completions.create(
            model="qwen-flash",          # 便宜快；要更聪明用 qwen-plus
            messages=messages,
            temperature=0.7,
        )
        reply = resp.choices[0].message.content
        print(f"小智：{reply}")
        messages.append({"role": "assistant", "content": reply})  # 记住上下文

if __name__ == "__main__":
    main()
运行：


python chat.py
messages 列表就是"记忆"——每轮把用户和 AI 的话都存进去，模型才能记得前文。

4. 阶段1：流式输出（可选，体验升级）
把上面的请求换成流式，文字会逐字蹦出来：


stream = client.chat.completions.create(
    model="qwen-flash", messages=messages, temperature=0.7, stream=True,
)
reply = ""
print("小智：", end="", flush=True)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
        reply += delta
print()
messages.append({"role": "assistant", "content": reply})
5. 阶段2：做成 HTTP 接口（让设备能连）
api_server.py


import os
import config
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
app = FastAPI(title="AI 对话机器人")
SYSTEM = "你是一个友好、简洁的中文 AI 助手，名字叫小智。"

# 每个会话一条消息历史（生产环境应换成 Redis/数据库）
SESSIONS: dict[str, list] = {}

class ChatRequest(BaseModel):
    session_id: str = "default"   # 不同设备/用户用不同 id，互不串话
    message: str

@app.post("/chat")
def chat(req: ChatRequest):
    msgs = SESSIONS.setdefault(req.session_id, [{"role": "system", "content": SYSTEM}])
    msgs.append({"role": "user", "content": req.message})
    resp = client.chat.completions.create(
        model="qwen-flash", messages=msgs, temperature=0.7,
    )
    reply = resp.choices[0].message.content
    msgs.append({"role": "assistant", "content": reply})
    return {"reply": reply}

@app.get("/")
def health():
    return {"status": "ok"}
启动：


uvicorn api_server:app --host 0.0.0.0 --port 8000
浏览器开 http://127.0.0.1:8000/docs 直接测试 /chat
--host 0.0.0.0 让同一 WiFi 下的设备也能访问（用电脑的局域网 IP，如 http://192.168.1.10:8000/chat）
测试（命令行）：


curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d "{\"message\":\"你好\"}"
6. 阶段3：语音对话（先在电脑跑通）
语音 = STT（听：语音转文字） + 你的 /chat + TTS（说：文字转语音）。

最省事的本地方案（离线、免费、跨平台）：


pip install SpeechRecognition pyttsx3 pyaudio requests
voice.py（骨架，按需调整）


import requests
import speech_recognition as sr   # STT
import pyttsx3                     # TTS

API = "http://127.0.0.1:8000/chat"
tts = pyttsx3.init()
rec = sr.Recognizer()
mic = sr.Microphone()

def listen() -> str:
    with mic as source:
        print("🎤 请说话…")
        audio = rec.listen(source)
    return rec.recognize_google(audio, language="zh-CN")  # 也可换百炼/whisper

def speak(text: str):
    print(f"小智：{text}")
    tts.say(text); tts.runAndWait()

if __name__ == "__main__":
    while True:
        try:
            text = listen()
            print(f"你：{text}")
            reply = requests.post(API, json={"message": text}).json()["reply"]
            speak(reply)
        except Exception as e:
            print("识别失败，再说一次：", e)
想要更好的中文识别/更自然的语音，把 STT/TTS 换成云端服务（百炼有 Paraformer 语音识别、CosyVoice 语音合成）。

7. 阶段4：单片机设备接入（C语言开发 NOMI / 小黄人 实体化）
关键认知：单片机不跑大模型、不跑你的 Python。它只做三件事：

收输入（按键/局域网文字、麦克风 I2S 录音）
用 WiFi 发 HTTP/WebSocket 给你电脑的 Python 接口
把回复显示在屏幕（LVGL 动画） / 用 I2S 喇叭播报

**硬件架构推荐（针对 ESP32-S3 C语言栈）**
*   **主控**：ESP32-S3 核心板（带 PSRAM，性能足以跑图形和音频）。
*   **听（音频采集）**：INMP441（I2S 接口数字全向麦克风）。
*   **说（音频播放）**：MAX98357A（I2S 接口 DAC + 功放）+ 4Ω 3W 小喇叭。
*   **看（表情显示）**：1.28 寸 GC9A01 圆形 TFT 屏幕（SPI 接口，非常适合做眼睛动画）。

**C 语言开发工具与核心库（基于 ESP-IDF 或 Arduino-C）**
为了实现目标，你需要在 C 语言环境中集成以下关键技术库：
1.  **WiFi 与 网络**：
    *   基础：`<WiFi.h>` (Arduino) 或 `esp_wifi` (IDF)。
    *   通信：`<HTTPClient.h>` 用于短连接，或 `<WebSocketsClient.h>` 用于低延迟全双工语音流。
    *   JSON解析：`cJSON` 库 或 `ArduinoJson` 库，解析服务器发来的指令。
2.  **音频处理（I2S）**：
    *   使用 ESP32 的 I2S 外设直接驱动。
    *   进阶推荐：使用乐鑫官方的 **ESP-ADF (Audio Development Framework)**。这是一个纯 C 语言的音频框架，自带 Ring Buffer，极大简化了“录音上传”和“边下载边播放”的逻辑。
3.  **UI 表情动画**：
    *   **LVGL (Light and Versatile Graphics Library)**：嵌入式最强的纯 C 语言开源图形库。
    *   你需要配置显示驱动（如 `TFT_eSPI` 或 `esp_lcd`），并在 LVGL 中利用 GIF 解码组件或多张静态图片循环（Image 控件），根据对话状态（待机、听、想、说）切换表情。

**ESP32（Arduino C++）基础网络示例**

```c
#include <WiFi.h>
#include <HTTPClient.h>

const char* ssid = "你的WiFi";
const char* pass = "WiFi密码";
const char* url  = "http://192.168.1.10:8000/chat";  // 你电脑的局域网IP

void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  Serial.println("WiFi 已连接");

  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST("{\"message\":\"你好\"}");
  if (code == 200) Serial.println(http.getString());  // 打印 AI 回复
  http.end();
}
void loop() {}
```

**后续 C 语言开发落地步骤 (Roadmap)**
建议你分模块、循序渐进地用 C 语言实现：
1.  **Hello World & 联网**：买到 ESP32-S3 后，先跑通上面的代码，能在串口打印出服务器大模型的回复。
2.  **点亮屏幕与动画**：接上 GC9A01 圆屏，移植 LVGL。尝试在屏幕上显示一个眨眼的静态/动态图像。
3.  **录音测试**：接上 INMP441，配置 I2S 录制一段环境音，尝试通过局域网发给电脑保存为 wav 文件，验证录音没问题。
4.  **播放测试**：接上 MAX98357A，让 ESP32 去访问一个固定的 MP3 链接或 PCM 音频流，验证能发声。
5.  **大脑联动**：重写 Python 端的接口，让它接收音频文件并返回音频流。最后在单片机上将“按键唤醒 -> 录音 -> 发 HTTP 请求 -> 接收音频流播放 -> 同步改变 LVGL 表情”串联起来。

购物清单（ESP32 方案）
*   ESP32-S3 开发板 (约 ￥25)
*   INMP441 麦克风模块 (约 ￥10)
*   MAX98357A 功放模块 + 喇叭 (约 ￥15)
*   1.28寸 GC9A01 圆屏 (约 ￥30)
*   杜邦线和面包板 (约 ￥15)
*   **总计：不到 ￥100 即可开始硬件 C 语言开发！**
8. 关键概念速记
概念	说明
瘦客户端	设备只收发，不思考；大脑在服务器
会话记忆	用 messages 列表存上下文；多用户用 session_id 区分
API Key 安全	只放服务器 .env，永不写进设备/前端/git
流式输出	stream=True，降低"感知延迟"
成本/延迟	qwen-flash 便宜快、qwen-plus 更聪明；按需选
上下文上限	对话太长要做"历史压缩"（保留最近N轮）防超长
9. 路线图 Checklist（✅=已实现并实测，⬜=待硬件）
- [x] 阶段0：`python chat.py` 能多轮对话
- [x] 阶段1：流式输出（`chat.py` STREAM 开关）
- [x] 阶段2：`/chat` 接口 + Swagger 测试通过
- [x] 阶段3：电脑上语音对话跑通（`voice.py`，含打断 barge-in）
- [x] 进阶：工具调用（`agent.py` / `tools.py` / `/agent`，查时间·天气·计算）
- [x] 进阶：上下文压缩（保留最近 N 轮）+ 会话持久化（SQLite，重启不丢记忆）
- [x] 进阶：语音进语音出接口 `/voice`（STT→大模型→TTS，给设备用）
- [x] 阶段4·step1：ESP32 联网串口调通 `/chat`（`firmware/esp32_chat`，代码就绪）
- [ ] 阶段4·step2~5：屏幕表情 / 录音 / 播放 / 整合语音助手 —— 固件已写好，**待上板验证**
- [ ] 进阶：换更自然音色、上云部署

### 项目现状速览
当前已实现的 HTTP 接口（`api_server.py`，启动：`uvicorn api_server:app --host 0.0.0.0 --port 8000`）：

| 接口 | 作用 |
|------|------|
| `POST /chat` | 一次性文字对话 |
| `POST /chat/stream` | 流式文字对话（SSE） |
| `POST /agent` | 能调工具（时间/天气/计算），返回 `tools_used` |
| `POST /voice` | 语音进语音出（收 WAV → 回 WAV），供单片机用 |
| `GET /` | 健康检查 |

单片机固件见 [`firmware/`](firmware/) 目录（含接线总表、逐模块自测、服务端契约、排错清单）。
**软件侧已全部完成；剩余工作主要是拿到 ESP32-S3 后逐模块烧录验证。**

10. 常见问题
Q：必须用阿里云百炼吗？
不必。任何 OpenAI 兼容接口都行（OpenAI、DeepSeek、本地 Ollama）——改 base_url 和 model 即可。

Q：断网能用吗？
云端模型断网就不行。要离线得在边缘设备（树莓派/带NPU的盒子）跑本地小模型（如 Ollama + qwen2.5:1.5b），质量会下降。

Q：怎么让它"会查资料/会干活"？
加"工具调用"（function calling）：把查询函数描述给模型，模型自己决定何时调用。这是从"聊天"到"能办事的 Agent"的关键一步。



---

这份指南**从零到单片机**全程可落地,且每个阶段都能单独验证。建议你**按 0→1→2→3→4 顺序推进**,先在电脑上把对话和 `/chat` 接口跑通(不花钱),再买硬件。

需要的话,我可以接着帮你:
1. 把**阶段0/2 的代码直接生成成文件**放进你指定的新文件夹(你给我路径);
2. 或在这个对话机器人骨架上,加一个**工具调用的最小示例**(让它从"会聊天"变成"能查东西办事")。

