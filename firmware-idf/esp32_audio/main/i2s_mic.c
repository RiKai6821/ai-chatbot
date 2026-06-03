/*
 * INMP441 数字麦克风 —— IDF v5.x 新版 I2S 标准驱动 (driver/i2s_std.h)。
 * 占用 I2S0，主机模式，仅接收(RX)。底层用 DMA 搬运，CPU 只需 i2s_channel_read。
 *
 * 接线：VDD->3V3 GND->GND L/R->GND(选左声道) SCK->BCLK WS->WS SD->DIN。
 */
#include "i2s_mic.h"

#include "driver/i2s_std.h"
#include "esp_log.h"
#include "sdkconfig.h"

static const char *TAG = "mic";
static i2s_chan_handle_t s_rx = NULL;

esp_err_t mic_init(void)
{
    // 通道配置：I2S0 主机；默认含 DMA 描述符数量/帧数（可按需调大降低丢帧）
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;     // DMA 描述符个数
    chan_cfg.dma_frame_num = 240;  // 每个描述符帧数（影响延迟/吞吐）
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &s_rx));  // 只要 RX

    i2s_std_config_t std_cfg = {
        .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(CONFIG_XZ_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
                        I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = CONFIG_XZ_MIC_BCLK,
            .ws   = CONFIG_XZ_MIC_WS,
            .dout = I2S_GPIO_UNUSED,
            .din  = CONFIG_XZ_MIC_DIN,
            .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
        },
    };
    // INMP441 的 L/R 接 GND -> 数据在左声道
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;

    ESP_ERROR_CHECK(i2s_channel_init_std_mode(s_rx, &std_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(s_rx));
    ESP_LOGI(TAG, "麦克风就绪 (I2S0, %d Hz)", CONFIG_XZ_SAMPLE_RATE);
    return ESP_OK;
}

int mic_read(int16_t *buf, int max_samples)
{
    size_t bytes_read = 0;
    esp_err_t err = i2s_channel_read(s_rx, buf, max_samples * sizeof(int16_t),
                                     &bytes_read, portMAX_DELAY);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "读取失败: %s", esp_err_to_name(err));
        return 0;
    }
    return (int)(bytes_read / sizeof(int16_t));
}
