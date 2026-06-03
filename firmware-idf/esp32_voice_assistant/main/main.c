/*
 * 整合语音助手（ESP-IDF）：按键唤醒 → 录音 → /voice → 播放，多任务 + 状态机
 * ================================================================
 * 架构（嵌入式"系统设计"亮点）：
 *   - 按键用 GPIO 中断(ISR) → FreeRTOS 队列，把硬件事件交给任务处理（ISR 只做最少事）
 *   - 一个 conversation_task 跑状态机：待机→听→想→说→待机
 *   - 录音/播放复用共享组件 bsp_audio；联网复用 bsp_wifi
 *   - 一轮对话全程流式（边录边传、边收边播），见 voice_client.c
 *
 * 现象：按 BOOT 键说话，松手前持续录 RECORD_SECONDS 秒，随后听到小智的语音回复；
 *       串口日志会打印 听/想/说 的状态切换。
 *
 * 构建：idf.py set-target esp32s3 && idf.py menuconfig && idf.py build flash monitor
 * ⚠️ 未上板验证。I2S 引脚/声道、按键去抖时长是上板要微调的点。
 */
#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/gpio.h"
#include "nvs_flash.h"
#include "esp_log.h"
#include "sdkconfig.h"

#include "wifi.h"
#include "i2s_mic.h"
#include "i2s_speaker.h"
#include "voice_client.h"

static const char *TAG = "app";
static QueueHandle_t s_btn_q;

// 按键中断：ISR 里只把事件丢进队列，真正处理放到任务（IRAM_ATTR 让 ISR 常驻 IRAM）
static void IRAM_ATTR btn_isr(void *arg)
{
    uint32_t evt = 1;
    BaseType_t hp = pdFALSE;
    xQueueSendFromISR(s_btn_q, &evt, &hp);
    if (hp) portYIELD_FROM_ISR();
}

static void button_init(void)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << CONFIG_XZ_BTN_GPIO,
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .intr_type    = GPIO_INTR_NEGEDGE,   // 按下=低电平，下降沿触发
    };
    gpio_config(&io);
    gpio_install_isr_service(0);
    gpio_isr_handler_add(CONFIG_XZ_BTN_GPIO, btn_isr, NULL);
}

// 状态变化：当前用日志体现；后续可在此驱动 GC9A01 表情或 RGB 灯
static void on_state(xz_state_t st)
{
    const char *name[] = { "待机", "听…", "想…", "说…" };
    ESP_LOGI(TAG, "[状态] %s", name[st]);
}

static void conversation_task(void *arg)
{
    uint32_t evt;
    on_state(ST_IDLE);
    ESP_LOGI(TAG, "就绪：按 BOOT 键说话。");
    while (1) {
        if (xQueueReceive(s_btn_q, &evt, portMAX_DELAY) != pdTRUE) continue;
        vTaskDelay(pdMS_TO_TICKS(30));                 // 去抖
        if (gpio_get_level(CONFIG_XZ_BTN_GPIO) != 0) continue;

        voice_do_turn(on_state);                       // 一轮：听→想→说
        on_state(ST_IDLE);

        while (gpio_get_level(CONFIG_XZ_BTN_GPIO) == 0) // 等松手
            vTaskDelay(pdMS_TO_TICKS(10));
        xQueueReset(s_btn_q);                          // 丢弃抖动期间的余票
    }
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    printf("\n=== 小智 · 语音助手 (ESP-IDF) ===\n");

    if (wifi_connect() != ESP_OK) {
        ESP_LOGE(TAG, "联网失败，停止。");
        return;
    }
    ESP_ERROR_CHECK(mic_init());
    ESP_ERROR_CHECK(speaker_init());

    s_btn_q = xQueueCreate(4, sizeof(uint32_t));
    button_init();

    xTaskCreate(conversation_task, "conv_task", 8192, NULL, 5, NULL);
}
