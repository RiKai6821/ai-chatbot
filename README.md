# 小智 · 端云协同 AI 语音助手

[![CI](https://github.com/RiKai6821/ai-chatbot/actions/workflows/ci.yml/badge.svg)](https://github.com/RiKai6821/ai-chatbot/actions/workflows/ci.yml)

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

核心原则：**大脑在云端，设备只做瘦客户端**——设备不跑大模型，只负责"听/说/显示"，通过 WiFi/HTTP 把音频交给服务器。好处：设备成本低、可随时升级"大脑"。

## 技术栈

| 层 | 技术 |
|----|------|
| 嵌入式 | C / **ESP-IDF v5.x**、FreeRTOS、CMake/Kconfig、组件化(BSP)、**I2S+DMA**、**esp_lcd(SPI)**、GPIO 中断、esp_http_client、cJSON |
| 云端服务 | Python、**FastAPI**、SSE 流式、SQLite 持久化、异步并发、限流/重试/超时/背压 |
| AI / Agent | DashScope(通义千问, OpenAI 兼容)、**Function Calling**、**RAG**(text-embedding-v3)、Paraformer(STT)、CosyVoice(TTS) |
| 工程化 | 评测框架(LLM 裁判)、结构化日志/可观测性、Docker、GitHub Actions CI |

## 两条技术线（均已实现并验证）

### 🔧 嵌入式固件 — `firmware-idf/`（ESP-IDF 纯 C，工程化）
- **共享 BSP 组件**（`bsp_wifi` / `bsp_audio` / `bsp_display`）+ 4 个应用，多应用复用底层。
- 覆盖考点：esp_wifi 事件驱动、**I2S 录音/播放 + DMA**、**esp_lcd 圆屏(分带渲染省内存)**、FreeRTOS 多任务、**GPIO 中断→队列**、状态机、HTTP 流式双向音频。
- 旗舰应用 `esp32_voice_assistant`：按键→录音→`/voice`→播放，表情随状态同步。
- （`firmware/` 是更早的 Arduino 原型版，保留以展示"原型→工程化"的演进。）
- ⚠️ 固件按 ESP-IDF v5 规范编写、接口与服务端对齐，但**尚未在真实硬件上烧录验证**。

### 🤖 AI Agent 服务 — 根目录 Python
- `api_server.py`：`/chat`、`/chat/stream`(SSE)、`/agent`(工具调用)、`/voice`(语音进出)，含上下文压缩与会话持久化；全异步 + 限流/重试/超时/背压。
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
├── resilience.py        # 限流 / 退避重试 / 超时
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

> API Key 申请：阿里云百炼 https://bailian.console.aliyun.com/ （兼容 OpenAI 接口；换 `base_url`/`model` 也可用 OpenAI、DeepSeek、本地 Ollama 等）。

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
