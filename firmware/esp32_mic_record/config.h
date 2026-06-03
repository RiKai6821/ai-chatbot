// INMP441 数字麦克风（I2S 接收）引脚 —— 按接线改
// 接线：VDD->3V3  GND->GND  L/R->GND(选左声道)  SCK/WS/SD 如下。
#pragma once

#define MIC_BCLK 4    // INMP441 的 SCK
#define MIC_WS   5    // INMP441 的 WS (LRCL)
#define MIC_SD   6    // INMP441 的 SD  (DOUT，进 ESP32)

#define MIC_SAMPLE_RATE 16000   // 16kHz，和服务端 Paraformer 一致
