/*
 * 语音一轮闭环（流式双向，无大缓冲）：
 *   录音 → 流式 POST 到 /voice → 流式接收回复音频 → 边收边推给功放。
 *
 * 工程亮点：
 *   - 上行：已知总长度，esp_http_client_open() 后用 write() 把"WAV头 + 实时录的PCM"
 *     一块块推上去，全程不缓存整段录音（省内存，不依赖 PSRAM）。
 *   - 下行：fetch_headers() 后 read() 流式取回复音频，跳过 44 字节 WAV 头，
 *     直接 speaker_write 播放；处理跨块的奇数字节对齐。
 */
#include "voice_client.h"

#include <string.h>
#include "esp_http_client.h"
#include "esp_log.h"
#include "sdkconfig.h"

#include "i2s_mic.h"
#include "i2s_speaker.h"

static const char *TAG = "voice";

// 构造 44 字节标准 WAV 头（PCM/单声道/16bit）
static void build_wav_header(uint8_t *h, uint32_t pcm_len, uint32_t rate)
{
    uint32_t byte_rate = rate * 2;          // 单声道 * 2字节
    uint32_t chunk_size = 36 + pcm_len;
    memcpy(h, "RIFF", 4);
    h[4] = chunk_size; h[5] = chunk_size >> 8; h[6] = chunk_size >> 16; h[7] = chunk_size >> 24;
    memcpy(h + 8, "WAVE", 4);
    memcpy(h + 12, "fmt ", 4);
    h[16] = 16; h[17] = 0; h[18] = 0; h[19] = 0;   // Subchunk1Size=16
    h[20] = 1;  h[21] = 0;                          // PCM
    h[22] = 1;  h[23] = 0;                          // 单声道
    h[24] = rate; h[25] = rate >> 8; h[26] = rate >> 16; h[27] = rate >> 24;
    h[28] = byte_rate; h[29] = byte_rate >> 8; h[30] = byte_rate >> 16; h[31] = byte_rate >> 24;
    h[32] = 2; h[33] = 0;                           // block align = 2
    h[34] = 16; h[35] = 0;                          // 16 bit
    memcpy(h + 36, "data", 4);
    h[40] = pcm_len; h[41] = pcm_len >> 8; h[42] = pcm_len >> 16; h[43] = pcm_len >> 24;
}

esp_err_t voice_do_turn(xz_state_cb on_state)
{
    const uint32_t rate = CONFIG_XZ_SAMPLE_RATE;
    const uint32_t pcm_len = rate * 2 * CONFIG_XZ_RECORD_SECONDS;  // 字节
    const uint32_t total   = 44 + pcm_len;                         // 含 WAV 头

    esp_http_client_config_t cfg = {
        .url        = CONFIG_XZ_VOICE_URL,
        .method     = HTTP_METHOD_POST,
        .timeout_ms = 30000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    esp_http_client_set_header(client, "Content-Type", "audio/wav");
    esp_http_client_set_header(client, "X-Session-Id", CONFIG_XZ_SESSION_ID);

    // 打开连接，声明将要写入的 body 总长度
    esp_err_t err = esp_http_client_open(client, total);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "连接失败: %s（查电脑IP/端口/--host 0.0.0.0）", esp_err_to_name(err));
        esp_http_client_cleanup(client);
        return err;
    }

    // ── 上行：先写 WAV 头，再边录边写 PCM ──
    if (on_state) on_state(ST_LISTENING);
    uint8_t header[44];
    build_wav_header(header, pcm_len, rate);
    esp_http_client_write(client, (const char *)header, 44);

    int16_t buf[512];
    uint32_t sent = 0;
    while (sent < pcm_len) {
        int n = mic_read(buf, 512);                 // 实时录一小段
        if (n <= 0) continue;
        int bytes = n * (int)sizeof(int16_t);
        if (sent + bytes > pcm_len) bytes = pcm_len - sent;  // 末尾对齐总长
        int w = esp_http_client_write(client, (const char *)buf, bytes);
        if (w < 0) { ESP_LOGE(TAG, "上传中断"); esp_http_client_cleanup(client); return ESP_FAIL; }
        sent += w;
    }

    // ── 等服务器处理（STT→大模型→TTS）──
    if (on_state) on_state(ST_THINKING);
    int clen = esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    if (status != 200) {
        ESP_LOGE(TAG, "/voice 返回 %d", status);
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "开始接收回复音频 (content-length=%d)", clen);

    // ── 下行：流式接收并播放，跳过 44 字节 WAV 头，处理奇数字节对齐 ──
    char rbuf[1024];
    int  hdr_skip = 44;
    uint8_t carry; int has_carry = 0;
    bool speaking_set = false;
    while (1) {
        int r = esp_http_client_read(client, rbuf, sizeof(rbuf));
        if (r <= 0) break;                 // 0=结束, <0=错误
        if (!speaking_set) { if (on_state) on_state(ST_SPEAKING); speaking_set = true; }

        int off = 0;
        if (hdr_skip > 0) {                // 先吃掉响应里的 WAV 头
            int take = (r < hdr_skip) ? r : hdr_skip;
            off += take; hdr_skip -= take;
        }
        if (off >= r) continue;

        // 把上一块遗留的半个样本拼上，保证 16bit 对齐再送功放
        static int16_t pcm[600];
        int pcm_n = 0;
        int i = off;
        if (has_carry) {
            pcm[pcm_n++] = (int16_t)((uint8_t)rbuf[i] << 8 | carry);
            i++; has_carry = 0;
        }
        int remain = r - i;
        if (remain & 1) { carry = (uint8_t)rbuf[r - 1]; has_carry = 1; remain--; }
        for (int j = 0; j < remain; j += 2) {
            pcm[pcm_n++] = (int16_t)((uint8_t)rbuf[i + j] | ((uint8_t)rbuf[i + j + 1] << 8));
        }
        if (pcm_n) speaker_write(pcm, pcm_n);
    }

    esp_http_client_cleanup(client);
    return ESP_OK;
}
