// ── 整合版语音助手配置：WiFi + 服务端 + 所有外设引脚 ──────────
// 改完再烧。注意：这里只放 WiFi 和电脑地址，绝不放大模型 API Key。
#pragma once

// 1) WiFi（必须 2.4GHz）
#define WIFI_SSID  "你的WiFi名称"
#define WIFI_PASS  "你的WiFi密码"

// 2) 电脑上语音接口地址（服务端需新增 /voice，见 firmware/README.md 的"服务端契约"）
//    启动服务端要带 --host 0.0.0.0。查电脑IP：ipconfig。
#define VOICE_URL   "http://192.168.1.10:8000/voice"
#define SESSION_ID  "esp32-1"

// 3) 录音时长（秒）—— 按一次键录这么久；先用定长，跑通后可改成"按住说话"
#define RECORD_SECONDS 4

// ── 外设引脚 ──────────────────────────────────────────────
// 唤醒按键（板载 BOOT 键就是 GPIO0，最省事；按下=低电平）
#define BTN_PIN 0

// GC9A01 圆屏（SPI）
#define TFT_SCLK 12
#define TFT_MOSI 11
#define TFT_DC    8
#define TFT_CS   10
#define TFT_RST   9
#define TFT_BL   14

// INMP441 麦克风（I2S 端口0，接收）
#define MIC_BCLK 4
#define MIC_WS   5
#define MIC_SD   6

// MAX98357A 功放（I2S 端口1，发送）
#define SPK_BCLK 15
#define SPK_LRC  16
#define SPK_DIN   7

#define SAMPLE_RATE 16000   // 录音/播放统一 16kHz 16bit 单声道
