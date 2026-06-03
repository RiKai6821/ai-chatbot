/*
 * GC9A01 1.28" 圆屏 —— IDF esp_lcd 面板 API（SPI + DMA）+ 表情渲染。
 *
 * 工程点：
 *   - SPI 总线 + esp_lcd_panel_io_spi + esp_lcd_new_panel_gc9a01 标准初始化流程
 *   - 分带(band)渲染：只用 240x40 的小缓冲，逐带光栅化再 draw_bitmap 刷出，
 *     省内存、不依赖 PSRAM（体现对受限内存的工程意识）
 *   - 纯软件画椭圆眼 + 圆瞳，不依赖任何图形库
 *
 * 接线：VCC->3V3 GND->GND，其余按 Kconfig（默认 SCLK12/MOSI11/DC8/CS10/RST9/BL14）。
 * ⚠️ 颜色不对(红蓝反/反色)时，调 rgb_ele_order 或 invert_color，以及 SWAP 宏。
 */
#include "display.h"

#include <string.h>
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_gc9a01.h"
#include "esp_log.h"
#include "sdkconfig.h"

static const char *TAG = "disp";

#define H_RES   240
#define V_RES   240
#define LCD_HOST SPI2_HOST
#define BAND_H  40                      // 每带高度；缓冲 = 240*40*2 ≈ 19KB

// GC9A01 走 SPI 多需高字节在前；这里把 RGB565 字节交换后再写缓冲。
#define SWAP565(c) ((uint16_t)((((c) & 0xFF) << 8) | (((c) >> 8) & 0xFF)))
#define C_BLACK  SWAP565(0x0000)
#define C_WHITE  SWAP565(0xFFFF)
#define C_CYAN   SWAP565(0x07FF)
#define C_YELLOW SWAP565(0xFFE0)
#define C_GREEN  SWAP565(0x07E0)

static esp_lcd_panel_handle_t s_panel = NULL;
static uint16_t s_band[H_RES * BAND_H];   // 静态分带缓冲

// 几何（与 Arduino 版一致）
#define CX 120
#define CY 120
#define EYE_HALF_W 23
#define GAP 24
#define PUPIL_R 12

esp_err_t display_init(void)
{
    spi_bus_config_t bus = {
        .sclk_io_num     = CONFIG_XZ_TFT_SCLK,
        .mosi_io_num     = CONFIG_XZ_TFT_MOSI,
        .miso_io_num     = -1,
        .quadwp_io_num   = -1,
        .quadhd_io_num   = -1,
        .max_transfer_sz = H_RES * BAND_H * sizeof(uint16_t),
    };
    ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &bus, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_handle_t io = NULL;
    esp_lcd_panel_io_spi_config_t io_cfg = {
        .dc_gpio_num       = CONFIG_XZ_TFT_DC,
        .cs_gpio_num       = CONFIG_XZ_TFT_CS,
        .pclk_hz           = 40 * 1000 * 1000,
        .lcd_cmd_bits      = 8,
        .lcd_param_bits    = 8,
        .spi_mode          = 0,
        .trans_queue_depth = 10,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)LCD_HOST, &io_cfg, &io));

    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = CONFIG_XZ_TFT_RST,
        .rgb_ele_order  = LCD_RGB_ELEMENT_ORDER_BGR,   // 红蓝反了就改 RGB
        .bits_per_pixel = 16,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_gc9a01(io, &panel_cfg, &s_panel));

    ESP_ERROR_CHECK(esp_lcd_panel_reset(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_init(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_invert_color(s_panel, true));  // GC9A01 通常需反色
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(s_panel, true));

    // 背光
    gpio_config_t bl = { .pin_bit_mask = 1ULL << CONFIG_XZ_TFT_BL, .mode = GPIO_MODE_OUTPUT };
    gpio_config(&bl);
    gpio_set_level(CONFIG_XZ_TFT_BL, 1);

    ESP_LOGI(TAG, "GC9A01 就绪 (%dx%d, SPI%d)", H_RES, V_RES, LCD_HOST + 1);
    return ESP_OK;
}

// 返回像素 (x,y) 的颜色（已字节交换）
static inline uint16_t eye_pixel(display_mood_t mood, int x, int y,
                                 float blink, int gx, int gy)
{
    uint16_t eyecolor = C_WHITE;
    float half_h = 32.0f;               // 眼睛半高（睁开）
    switch (mood) {
        case MOOD_LISTENING: eyecolor = C_CYAN;   half_h = 36.0f; break;
        case MOOD_THINKING:  eyecolor = C_YELLOW; half_h = 25.0f; break;
        case MOOD_SPEAKING:  eyecolor = C_GREEN;  half_h = 30.0f; break;
        default:             eyecolor = C_WHITE;  half_h = 32.0f; break;
    }
    float b = half_h * (1.0f - blink);
    if (b < 2.0f) b = 2.0f;

    const int lx = CX - GAP - EYE_HALF_W;   // 73
    const int rx = CX + GAP + EYE_HALF_W;   // 167
    const int centers[2] = { lx, rx };

    for (int e = 0; e < 2; e++) {
        float nx = (float)(x - centers[e]) / EYE_HALF_W;
        float ny = (float)(y - CY) / b;
        if (nx * nx + ny * ny <= 1.0f) {           // 椭圆内 = 眼白
            if (blink < 0.6f) {                    // 睁着才画瞳孔
                int px = x - (centers[e] + gx);
                int py = y - (CY + gy);
                if (px * px + py * py <= PUPIL_R * PUPIL_R) return C_BLACK;
            }
            return eyecolor;
        }
    }
    return C_BLACK;
}

void display_draw(display_mood_t mood, float blink, int gaze_dx, int gaze_dy)
{
    if (!s_panel) return;
    for (int y0 = 0; y0 < V_RES; y0 += BAND_H) {
        int y1 = (y0 + BAND_H > V_RES) ? V_RES : y0 + BAND_H;
        for (int y = y0; y < y1; y++) {
            uint16_t *row = &s_band[(y - y0) * H_RES];
            for (int x = 0; x < H_RES; x++) {
                row[x] = eye_pixel(mood, x, y, blink, gaze_dx, gaze_dy);
            }
        }
        // 刷这一带（坐标右/下端为开区间）
        esp_lcd_panel_draw_bitmap(s_panel, 0, y0, H_RES, y1, s_band);
    }
}

void display_set_mood(display_mood_t mood)
{
    display_draw(mood, 0.0f, 0, 0);
}
