/*
 * /chat 客户端：用 cJSON 构造请求、esp_http_client 发 POST、
 * 在事件回调里把响应体攒进动态缓冲，再用 cJSON 解析出 reply。
 *
 * 这里体现的工程点：HTTP 客户端事件驱动收数据、堆内存管理、JSON 解析、
 * 出错路径处理（status 非 200、JSON 缺字段等）。
 */
#include "chat_client.h"

#include <stdlib.h>
#include <string.h>
#include "esp_http_client.h"
#include "esp_log.h"
#include "cJSON.h"
#include "sdkconfig.h"

static const char *TAG = "chat";

// 收响应用的动态缓冲
typedef struct {
    char  *buf;
    int    len;
    int    cap;
} resp_acc_t;

static esp_err_t http_event(esp_http_client_event_t *evt)
{
    resp_acc_t *acc = (resp_acc_t *)evt->user_data;
    if (evt->event_id == HTTP_EVENT_ON_DATA && acc) {
        // 按需扩容后追加
        if (acc->len + evt->data_len + 1 > acc->cap) {
            int newcap = (acc->cap ? acc->cap * 2 : 512);
            while (newcap < acc->len + evt->data_len + 1) newcap *= 2;
            char *p = realloc(acc->buf, newcap);
            if (!p) return ESP_ERR_NO_MEM;
            acc->buf = p;
            acc->cap = newcap;
        }
        memcpy(acc->buf + acc->len, evt->data, evt->data_len);
        acc->len += evt->data_len;
        acc->buf[acc->len] = '\0';
    }
    return ESP_OK;
}

esp_err_t chat_send(const char *message, char *reply_out, size_t reply_cap)
{
    if (!message || !reply_out || reply_cap == 0) return ESP_ERR_INVALID_ARG;
    reply_out[0] = '\0';

    // 1) 构造请求 JSON：{"session_id":..., "message":...}
    cJSON *req = cJSON_CreateObject();
    cJSON_AddStringToObject(req, "session_id", CONFIG_XZ_SESSION_ID);
    cJSON_AddStringToObject(req, "message", message);
    char *body = cJSON_PrintUnformatted(req);
    cJSON_Delete(req);
    if (!body) return ESP_ERR_NO_MEM;

    // 2) 发 POST
    resp_acc_t acc = { 0 };
    esp_http_client_config_t cfg = {
        .url           = CONFIG_XZ_SERVER_URL,
        .method        = HTTP_METHOD_POST,
        .timeout_ms    = 30000,            // 大模型生成可能要几秒
        .event_handler = http_event,
        .user_data     = &acc,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body, strlen(body));

    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);
    free(body);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HTTP 失败: %s（检查电脑IP/端口/--host 0.0.0.0）", esp_err_to_name(err));
        free(acc.buf);
        return err;
    }
    if (status != 200) {
        ESP_LOGE(TAG, "服务端返回 %d: %s", status, acc.buf ? acc.buf : "");
        free(acc.buf);
        return ESP_FAIL;
    }

    // 3) 解析 {"reply": "..."}
    esp_err_t ret = ESP_FAIL;
    cJSON *root = cJSON_Parse(acc.buf ? acc.buf : "");
    if (root) {
        cJSON *reply = cJSON_GetObjectItem(root, "reply");
        if (cJSON_IsString(reply) && reply->valuestring) {
            strncpy(reply_out, reply->valuestring, reply_cap - 1);
            reply_out[reply_cap - 1] = '\0';
            ret = ESP_OK;
        } else {
            ESP_LOGE(TAG, "响应缺少 reply 字段");
        }
        cJSON_Delete(root);
    } else {
        ESP_LOGE(TAG, "JSON 解析失败: %s", acc.buf ? acc.buf : "(空)");
    }
    free(acc.buf);
    return ret;
}
