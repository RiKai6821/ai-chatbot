#pragma once
#include <stddef.h>
#include "esp_err.h"

// 初始化 INMP441 麦克风（I2S0，接收，DMA）。
esp_err_t mic_init(void);

// 阻塞读取一批 16bit 样本到 buf，返回实际读到的样本数（非字节）。
// buf 容量为 max_samples 个 int16_t。
int mic_read(int16_t *buf, int max_samples);
