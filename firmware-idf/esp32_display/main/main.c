/*
 * ESP-IDF GC9A01 圆屏表情自测
 * ================================================================
 * 用 esp_lcd（SPI+DMA）驱动圆屏，循环演示四种表情和小动作：
 *   待机(定时眨眼) / 听(睁大) / 想(眼珠左右看) / 说(眼珠上下动)
 *
 * 构建：idf.py set-target esp32s3 && idf.py menuconfig && idf.py build flash monitor
 *   （首次 build 会自动从组件管理器下载 esp_lcd_gc9a01）
 * ⚠️ 未上板验证。颜色不对时调 display.c 里的 rgb_ele_order / invert_color / SWAP565。
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "display.h"

static void blink_once(display_mood_t mood)
{
    for (float b = 0; b <= 1.0f; b += 0.25f) { display_draw(mood, b, 0, 0); vTaskDelay(pdMS_TO_TICKS(18)); }
    for (float b = 1.0f; b >= 0; b -= 0.25f) { display_draw(mood, b, 0, 0); vTaskDelay(pdMS_TO_TICKS(18)); }
}

void app_main(void)
{
    ESP_ERROR_CHECK(display_init());
    ESP_LOGI("disp", "开始演示四种表情。");

    while (1) {
        // 待机 + 定时眨眼
        display_set_mood(MOOD_IDLE);
        for (int i = 0; i < 3; i++) { vTaskDelay(pdMS_TO_TICKS(900)); blink_once(MOOD_IDLE); }

        // 听：睁大、轻微上看
        display_draw(MOOD_LISTENING, 0, 0, -6);
        vTaskDelay(pdMS_TO_TICKS(1500));

        // 想：眼珠左右来回看
        for (int i = 0; i < 2; i++) {
            for (int dx = -10; dx <= 10; dx += 5) { display_draw(MOOD_THINKING, 0, dx, 0); vTaskDelay(pdMS_TO_TICKS(80)); }
            for (int dx = 10; dx >= -10; dx -= 5) { display_draw(MOOD_THINKING, 0, dx, 0); vTaskDelay(pdMS_TO_TICKS(80)); }
        }

        // 说：眼珠上下轻动
        for (int i = 0; i < 6; i++) {
            display_draw(MOOD_SPEAKING, 0, 0, -4); vTaskDelay(pdMS_TO_TICKS(120));
            display_draw(MOOD_SPEAKING, 0, 0,  4); vTaskDelay(pdMS_TO_TICKS(120));
        }
    }
}
