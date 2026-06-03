# 固件（阶段4）· ESP32-S3 C/C++ 代码

设备是"瘦客户端"：只负责**收输入 → WiFi 发 HTTP → 显示/播报**，大脑（大模型）在电脑上的 `api_server.py`。**API Key 永远不进设备。**

代码按 README 路线图拆成**可独立验证**的模块，建议照顺序逐个跑通，最后用整合版串起来。

| 模块 | 路线图步骤 | 验证目标 | 是否联网 |
|------|------|------|------|
| `esp32_chat/` | ① Hello & 联网 | 串口打字 ↔ `/chat` 文字对话 | ✅ |
| `esp32_display/` | ② 点屏 | GC9A01 圆屏显示会动的表情眼睛 | ❌ |
| `esp32_mic_record/` | ③ 录音 | INMP441 录音，串口看音量条 | ❌ |
| `esp32_speaker/` | ④ 播放 | MAX98357A 播正弦提示音 | ❌ |
| `esp32_voice_assistant/` | ⑤ 大脑联动 | 按键→录音→上传→播放→表情同步 | ✅ |

---

## 开发环境

1. [Arduino IDE 2.x](https://www.arduino.cc/en/software)
2. 开发板：首选项里加
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`，
   开发板管理器装 **esp32 by Espressif Systems（core 3.x）**，开发板选 **ESP32S3 Dev Module**。
   > ⚠️ 音频用的是 core 3.x 自带的 `ESP_I2S` 库；若你装的是 2.x，I2S 写法不同，编译会报错。
3. 库管理器安装：**GFX Library for Arduino**（by moononournation，即 Arduino_GFX）。
   `WiFi.h` / `HTTPClient.h` / `ESP_I2S.h` 都是 core 自带，无需另装。
4. 若用到 PSRAM（录音缓冲）：开发板菜单里把 **PSRAM** 设为 `OPI PSRAM`（按你的板子）。

---

## 接线总表（默认引脚，可在各自 config.h 改）

| 外设 | 模块脚 | ESP32-S3 GPIO |
|------|------|------|
| **GC9A01 圆屏** | SCL/CLK | 12 |
| | SDA/DIN(MOSI) | 11 |
| | DC | 8 |
| | CS | 10 |
| | RST | 9 |
| | BL(背光) | 14 |
| | VCC / GND | 3V3 / GND |
| **INMP441 麦克风** | SCK | 4 |
| | WS(LRCL) | 5 |
| | SD | 6 |
| | L/R | **GND**（选左声道） |
| | VDD / GND | 3V3 / GND |
| **MAX98357A 功放** | BCLK | 15 |
| | LRC | 16 |
| | DIN | 7 |
| | VIN / GND | 5V / GND（喇叭功率大建议 5V） |
| **唤醒按键** | — | GPIO0（板载 BOOT 键，免接） |

> 屏幕 SPI、麦克风 I2S、功放 I2S 各走独立总线/端口，互不冲突（S3 有 2 个 I2S 端口）。

---

## 逐模块跑通

### ① `esp32_chat` —— 联网调通 /chat（文字）
见本节最初版本：改 `config.h` 的 WiFi 和电脑 IP，电脑跑 `uvicorn api_server:app --host 0.0.0.0 --port 8000`，串口监视器（115200，换行）里打字对话。

### ② `esp32_display` —— 点屏 + 表情
接好屏，直接烧。应看到一对眼睛轮流演示 待机/听/想/说 四种状态（眨眼、左右看、上下动）。不亮先查 BL 背光脚和 SPI 接线。

### ③ `esp32_mic_record` —— 录音自测
接好 INMP441，烧录。串口会持续打印音量条：安静时很短，**说话/拍手时明显变长**=麦克风正常。一直≈0：查 L/R 接 GND、SD 接对、3V3 供电。

### ④ `esp32_speaker` —— 播放自测
接好 MAX98357A + 喇叭，烧录。应听到高低交替的"嘀"声。没声音：查 VIN 供电、DIN/BCLK/LRC、SD 使能、喇叭线。

### ⑤ `esp32_voice_assistant` —— 整合版
四样都单独跑通后再上这个。改 `config.h`（WiFi + `VOICE_URL` + 引脚），烧录，**按 BOOT 键说话**：表情会随 听→想→说 切换，并播报小智的语音回复。
> 它依赖电脑端的 `/voice` 接口，**目前服务端还没有**，见下。

---

## 服务端契约（整合版需要电脑端新增 `/voice`）

整合版固件按这个约定收发音频，电脑端需要补一个接口：

```
POST /voice
  Header: X-Session-Id: esp32-1
  Body  : WAV 音频（16kHz / 16bit / 单声道）—— 设备录的音
返回:
  Body  : WAV 音频（16kHz / 16bit / 单声道）—— 小智回复的语音
  (可选) Header: X-Reply-Text / X-Emotion
```
电脑端内部流程 = **STT(Paraformer) → 大模型(/agent 同款) → TTS(返回16k PCM)**。
现有 `voice.py` 已有 STT/大模型/TTS 的全部零件，把它们组装成一个 HTTP 接口即可。
**需要的话我来加这个 `/voice` 接口。**

---

## ⚠️ 重要说明

- 以上固件**尚未在真实 ESP32-S3 上编译/烧录验证过**（开发机无硬件与工具链）。结构、接口、引脚都按文档对齐了，但嵌入式高度依赖具体板子/库版本——**首次上板大概率要调**，最可能出问题的是：
  - **I2S**：core 版本差异、单声道左右声道选择、双端口分配；
  - **屏幕**：SPI 引脚、IPS/旋转参数、背光；
  - **WAV 头**：播放时默认跳 44 字节标准头，若服务端返回裸 PCM 就把那段 `off=44` 改成 0。
- 上板报错（编译错误或串口异常）直接贴给我，我按你的具体板子/库版本调。
