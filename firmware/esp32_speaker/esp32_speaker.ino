/*
 * 阶段4 · 第4步：MAX98357A 功放 I2S 播放自测
 * ---------------------------------------------------------------
 * 最简单的"能不能出声"验证：生成正弦波音调，通过 I2S 推给 MAX98357A，
 * 你应能从喇叭听到"嘀——"的提示音（440Hz / 880Hz 交替）。
 * 不联网。听到声音 = 功放接线和 I2S 发送配置正确。
 *
 * I2S 用 arduino-esp32 core 3.x 自带 ESP_I2S（无需另装）。
 * ⚠️ 没声音先查：VIN 供电是否足（喇叭功率大时建议 5V）、DIN/BCLK/LRC 是否接对、
 *    SD 脚是否使能、喇叭线是否接好。
 *
 * 开发板：ESP32S3 Dev Module（core 3.x）。
 */

#include <ESP_I2S.h>
#include <math.h>
#include "config.h"

I2SClass I2S;

void initSpeaker() {
  // setPins(bclk, ws, dout(输出到功放), din(麦克风,这里-1), mclk)
  I2S.setPins(SPK_BCLK, SPK_LRC, SPK_DIN, -1, -1);
  if (!I2S.begin(I2S_MODE_STD, SPK_SAMPLE_RATE,
                 I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("I2S(功放) 初始化失败！检查引脚/接线。");
    while (true) delay(1000);
  }
  Serial.println("功放 I2S 就绪。");
}

// 播放一个频率为 freq、时长 ms 的正弦音
void playTone(int freq, int ms, float volume = 0.3f) {
  const int sr = SPK_SAMPLE_RATE;
  int totalSamples = (long)sr * ms / 1000;
  for (int i = 0; i < totalSamples; i++) {
    float t = (float)i / sr;
    int16_t sample = (int16_t)(sinf(2.0f * PI * freq * t) * 32767 * volume);
    // 单声道：写 2 字节
    uint8_t bytes[2] = { (uint8_t)(sample & 0xff), (uint8_t)((sample >> 8) & 0xff) };
    I2S.write(bytes, 2);
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== MAX98357A 功放自测 ===");
  initSpeaker();
  Serial.println("开始播放提示音，你应能听到高低交替的'嘀'声。");
}

void loop() {
  Serial.println("嘀(440Hz)…");
  playTone(440, 400);
  delay(250);
  Serial.println("嘀(880Hz)…");
  playTone(880, 400);
  delay(1200);
}
