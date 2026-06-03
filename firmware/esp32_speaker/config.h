// MAX98357A 功放（I2S 发送）引脚 —— 按接线改
// 接线：VIN->5V(或3V3)  GND->GND  DIN/BCLK/LRC 如下；
//   SD 脚：悬空或拉高=开启；GAIN 脚按模块说明设增益。喇叭接 +/-。
#pragma once

#define SPK_BCLK 15   // MAX98357A 的 BCLK
#define SPK_LRC  16   // MAX98357A 的 LRC (WS)
#define SPK_DIN   7   // MAX98357A 的 DIN (从 ESP32 输出)

#define SPK_SAMPLE_RATE 16000
