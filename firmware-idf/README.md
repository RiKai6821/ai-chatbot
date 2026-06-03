# 固件（ESP-IDF 纯 C 版）· 工程化实现

这是 `firmware/`（Arduino 原型版）的**工业级重写**。两套并存，刻意保留，用来讲一个完整的工程叙事：

> **Arduino 快速验证原型 → ESP-IDF 工程化落地**

面**半导体公司嵌入式岗**时，看的是 ESP-IDF 这条线体现出来的能力，而不是 Arduino。

## 为什么用 ESP-IDF 而不是 Arduino（工程实践视角）

| 维度 | Arduino (`firmware/`) | ESP-IDF (`firmware-idf/`，本目录) |
|------|------|------|
| 语言 | C/C++，高度封装 | **纯 C**，贴近底层 |
| 构建 | IDE 黑盒 | **CMake + Kconfig(menuconfig)**，可脚本化/CI |
| 并发 | `loop()` 单循环 | **FreeRTOS 任务 / 队列 / 事件组** |
| 联网 | `WiFi.h` 一行连 | **esp_wifi 事件驱动** + netif + 重试状态机 |
| 配置 | 写死在 `config.h` | **Kconfig** 菜单，密码不入版本库 |
| 工程结构 | 单 `.ino` | **component 化**（main 注册 + REQUIRES 声明依赖） |

这些正是嵌入式面试的考点：RTOS、事件驱动、构建系统、内存管理、组件化。

## 模块一览

| 工程 | 内容 | 关键技术点 |
|------|------|-----------|
| `esp32_chat/` | 联网 + 调 `/chat` 文字对话 | esp_wifi 事件驱动、esp_http_client、cJSON、FreeRTOS 任务、UART/VFS |
| `esp32_audio/` | INMP441 录音 + MAX98357A 播放自测 | **新版 I2S 标准驱动 `i2s_std.h`**、**DMA**、双路 I2S 通道、双并发 FreeRTOS 任务 |

> 嵌入式岗最看重的"外设驱动 + DMA + RTOS"集中在 `esp32_audio`：两路 I2S（I2S0 收 / I2S1 发）各由独立任务驱动，底层 DMA 搬运，CPU 只做 `i2s_channel_read/write`。

## 工程结构（`esp32_chat`）

```
esp32_chat/
├── CMakeLists.txt              # 工程入口
├── sdkconfig.defaults          # 默认配置（目标芯片、栈大小、日志级别）
└── main/
    ├── CMakeLists.txt          # 组件注册 + REQUIRES 依赖声明
    ├── Kconfig.projbuild       # menuconfig 配置项（WiFi / 服务器地址）
    ├── main.c                  # app_main：NVS → 联网 → 起 FreeRTOS 对话任务
    ├── wifi.c / wifi.h         # esp_wifi 事件驱动联网（EventGroup 同步）
    └── chat_client.c / .h      # esp_http_client + cJSON 调 /chat
```

职责分层清晰：**联网**、**HTTP/JSON 客户端**、**应用逻辑**各自独立成文件，可单独复用/测试。

## 构建与烧录

前置：装好 [ESP-IDF **v5.x**](https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/get-started/)（含 `idf.py` 工具链）。

```bash
cd firmware-idf/esp32_chat
idf.py set-target esp32s3
idf.py menuconfig          # 进 "小智 Chat 配置"：填 WiFi SSID/密码、电脑 /chat 地址
idf.py build
idf.py -p <你的串口> flash monitor   # 烧录并看日志；退出 monitor 按 Ctrl+]
```

电脑端照常启动服务端（同一 WiFi，务必 `--host 0.0.0.0`）：
```
uvicorn api_server:app --host 0.0.0.0 --port 8000
```
monitor 里会先自检发一句"你好"，然后可直接打字对话。

## 说明与排错

- **未上板验证**：开发机无硬件/工具链，本工程**尚未真机编译烧录**。代码按 IDF v5.x 规范编写，结构与 API 对齐；首次构建若报错，最可能是 **IDF 版本差异**（见下）。
- **UART/VFS 版本差异**：`main.c` 里读串口输入的 VFS 头/函数在 IDF 5.x 与更早版本名字不同，已用 `ESP_IDF_VERSION` 宏适配；个别小版本若仍报错，按注释切换 `uart_vfs` ↔ `esp_vfs_dev` 分支即可。
- **cJSON / esp_http_client** 都是 IDF 自带组件，已在 `main/CMakeLists.txt` 的 `REQUIRES` 里声明，无需额外安装。
- 后续模块（屏幕/I2S 音频/整合语音）也会按这套 component 化方式补到本目录；I2S 在 IDF 下用 `driver/i2s_std.h`（新标准驱动），比 Arduino 更能体现对外设/DMA 的掌握。
