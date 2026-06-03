#pragma once
#include "esp_err.h"

// 连接 WiFi（station 模式），阻塞到连上或重试耗尽。成功返回 ESP_OK。
esp_err_t wifi_connect(void);
