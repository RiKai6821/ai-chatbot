/*
 * ESP-IDF I2S 音频自测：INMP441 录音 + MAX98357A 播放
 * ================================================================
 * 体现的能力：
 *   - IDF v5.x 新版 I2S 标准驱动 (i2s_std.h)，DMA 搬运
 *   - 两路 I2S 独立通道（I2S0 收 / I2S1 发）
 *   - 两个并发 FreeRTOS 任务各自驱动一路，互不阻塞
 *
 * 现象：
 *   - 喇叭每隔几秒发出高低交替的"嘀"声（播放任务）
 *   - 串口持续打印麦克风音量条，说话/拍手时变长（录音任务）
 *
 * 构建：idf.py set-target esp32s3 && idf.py menuconfig && idf.py build flash monitor
 * ⚠️ 未上板验证；I2S 引脚、单声道左右声道(slot_mask)是最可能要按板子微调的地方。
 */
#include <stdio.h>
#include <stdlib.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "i2s_mic.h"
#include "i2s_speaker.h"

static const char *TAG = "audio";

// 录音任务：读麦克风 → 算这批样本的峰值 → 打音量条
static void mic_task(void *arg)
{
    static int16_t buf[512];
    while (1) {
        int n = mic_read(buf, 512);
        int peak = 0;
        for (int i = 0; i < n; i++) {
            int a = buf[i] < 0 ? -buf[i] : buf[i];
            if (a > peak) peak = a;
        }
        int bars = peak / 1000;
        if (bars > 40) bars = 40;
        char line[48];
        int k = 0;
        for (; k < bars && k < 40; k++) line[k] = '#';
        line[k] = '\0';
        printf("音量=%5d |%s\n", peak, line);
        vTaskDelay(pdMS_TO_TICKS(120));
    }
}

// 播放任务：周期性播放提示音
static void speaker_task(void *arg)
{
    while (1) {
        speaker_play_tone(440, 300, 0.3f);
        vTaskDelay(pdMS_TO_TICKS(150));
        speaker_play_tone(880, 300, 0.3f);
        vTaskDelay(pdMS_TO_TICKS(1500));
    }
}

void app_main(void)
{
    printf("\n=== ESP-IDF I2S 音频自测 ===\n");
    ESP_ERROR_CHECK(mic_init());
    ESP_ERROR_CHECK(speaker_init());

    // 两个任务并发：录音在核心打音量、播放在另一节奏发声，互不阻塞
    xTaskCreate(mic_task,     "mic_task",     4096, NULL, 5, NULL);
    xTaskCreate(speaker_task, "speaker_task", 4096, NULL, 5, NULL);

    ESP_LOGI(TAG, "录音/播放任务已启动。");
}
