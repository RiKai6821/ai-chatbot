#pragma once
#include <stddef.h>
#include "esp_err.h"

// 把 message 发给服务端 /chat，把回复写进 reply_out（容量 reply_cap）。
// 成功返回 ESP_OK。线程安全：内部不使用全局状态。
esp_err_t chat_send(const char *message, char *reply_out, size_t reply_cap);
