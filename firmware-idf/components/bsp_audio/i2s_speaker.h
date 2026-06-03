#pragma once
#include <stdint.h>
#include "esp_err.h"

// 初始化 MAX98357A 功放（I2S1，发送，DMA）。
esp_err_t speaker_init(void);

// 写一批 16bit 样本到功放，阻塞直到 DMA 收下。返回写出的样本数。
int speaker_write(const int16_t *buf, int samples);

// 便捷：播放一个正弦音（频率 Hz、时长 ms、音量 0~1）。
void speaker_play_tone(int freq, int ms, float volume);
