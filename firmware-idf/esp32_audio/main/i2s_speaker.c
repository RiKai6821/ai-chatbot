/*
 * MAX98357A 功放 —— IDF v5.x 新版 I2S 标准驱动 (driver/i2s_std.h)。
 * 占用 I2S1，主机模式，仅发送(TX)。底层 DMA 自动搬运。
 *
 * 接线：VIN->5V(喇叭功率大建议5V) GND->GND BCLK->BCLK LRC->WS DIN->DOUT，喇叭接+/-。
 */
#include "i2s_speaker.h"

#include <math.h>
#include "driver/i2s_std.h"
#include "esp_log.h"
#include "sdkconfig.h"

static const char *TAG = "spk";
static i2s_chan_handle_t s_tx = NULL;

esp_err_t speaker_init(void)
{
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_1, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 240;
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, &s_tx, NULL));  // 只要 TX

    i2s_std_config_t std_cfg = {
        .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(CONFIG_XZ_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
                        I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = CONFIG_XZ_SPK_BCLK,
            .ws   = CONFIG_XZ_SPK_WS,
            .dout = CONFIG_XZ_SPK_DOUT,
            .din  = I2S_GPIO_UNUSED,
            .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
        },
    };
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(s_tx, &std_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(s_tx));
    ESP_LOGI(TAG, "功放就绪 (I2S1, %d Hz)", CONFIG_XZ_SAMPLE_RATE);
    return ESP_OK;
}

int speaker_write(const int16_t *buf, int samples)
{
    size_t bytes_written = 0;
    esp_err_t err = i2s_channel_write(s_tx, buf, samples * sizeof(int16_t),
                                      &bytes_written, portMAX_DELAY);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "写入失败: %s", esp_err_to_name(err));
        return 0;
    }
    return (int)(bytes_written / sizeof(int16_t));
}

void speaker_play_tone(int freq, int ms, float volume)
{
    const int sr = CONFIG_XZ_SAMPLE_RATE;
    const int total = (long)sr * ms / 1000;
    int16_t chunk[256];
    int done = 0;
    while (done < total) {
        int n = (total - done < 256) ? (total - done) : 256;
        for (int i = 0; i < n; i++) {
            float t = (float)(done + i) / sr;
            chunk[i] = (int16_t)(sinf(2.0f * (float)M_PI * freq * t) * 32767.0f * volume);
        }
        speaker_write(chunk, n);
        done += n;
    }
}
