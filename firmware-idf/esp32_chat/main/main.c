/*
 * 阶段4 · 第1步（ESP-IDF 纯 C 版）：联网 + 调通 /chat，串口里打字对话
 * ================================================================
 * 与 Arduino 版功能相同，但用工业级的 ESP-IDF：
 *   - NVS 初始化（WiFi 需要）
 *   - FreeRTOS 任务（xTaskCreate）承载对话循环
 *   - esp_wifi 事件驱动联网（见 wifi.c）
 *   - esp_http_client + cJSON 调用 /chat（见 chat_client.c）
 *   - UART/VFS 让 stdin 可阻塞按行读取（串口打字）
 *
 * 构建（已装好 ESP-IDF v5.x 环境）：
 *   idf.py set-target esp32s3
 *   idf.py menuconfig      # 在"小智 Chat 配置"里填 WiFi 和电脑 IP
 *   idf.py build flash monitor
 *
 * ⚠️ 假定 ESP-IDF v5.x。UART/VFS 头在不同小版本有差异，已用版本宏适配；
 *    若你的版本编译报 uart_vfs 相关错，按注释切到 esp_vfs_dev 分支。
 */
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "esp_log.h"
#include "esp_idf_version.h"
#include "driver/uart.h"

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
#include "driver/uart_vfs.h"
#else
#include "esp_vfs_dev.h"
#endif

#include "wifi.h"
#include "chat_client.h"

static const char *TAG = "app";

// 让 stdin 支持阻塞式按行读取（默认非阻塞，fgets 会立即返回）
static void console_init(void)
{
    setvbuf(stdin, NULL, _IONBF, 0);
    uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0);
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
    uart_vfs_dev_use_driver(UART_NUM_0);
    uart_vfs_dev_port_set_rx_line_endings(UART_NUM_0, ESP_LINE_ENDINGS_CR);
    uart_vfs_dev_port_set_tx_line_endings(UART_NUM_0, ESP_LINE_ENDINGS_CRLF);
#else
    esp_vfs_dev_uart_use_driver(UART_NUM_0);
    esp_vfs_dev_uart_port_set_rx_line_endings(UART_NUM_0, ESP_LINE_ENDINGS_CR);
#endif
}

// 去掉行尾的 \r\n
static void rstrip(char *s)
{
    size_t n = strlen(s);
    while (n && (s[n - 1] == '\n' || s[n - 1] == '\r')) s[--n] = '\0';
}

// 对话任务：自检一句，然后循环读串口输入 → 调 /chat → 打印回复
static void chat_task(void *arg)
{
    static char line[256];
    static char reply[2048];

    ESP_LOGI(TAG, "自检：发送一句『你好』测试链路…");
    if (chat_send("你好，用一句话介绍你自己", reply, sizeof(reply)) == ESP_OK) {
        printf("小智：%s\n", reply);
    }

    printf("\n现在可以打字（回车发送）开始对话：\n");
    while (1) {
        printf("你："); fflush(stdout);
        if (!fgets(line, sizeof(line), stdin)) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        rstrip(line);
        if (line[0] == '\0') continue;

        if (chat_send(line, reply, sizeof(reply)) == ESP_OK) {
            printf("小智：%s\n", reply);
        } else {
            printf("（没拿到回复，看上面的错误日志排查）\n");
        }
    }
}

void app_main(void)
{
    // NVS：WiFi 校准数据等需要它
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    console_init();
    printf("\n=== 小智 · ESP-IDF 串口对话 ===\n");

    if (wifi_connect() != ESP_OK) {
        ESP_LOGE(TAG, "联网失败，停止。");
        return;
    }

    // 用独立 FreeRTOS 任务跑对话循环（栈给足，HTTP+JSON 占用不小）
    xTaskCreate(chat_task, "chat_task", 8192, NULL, 5, NULL);
}
