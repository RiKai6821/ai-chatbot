// GC9A01 1.28" 圆形 TFT（SPI）引脚 —— 按你的接线改这里
// 主控：ESP32-S3。下面是一组避开 strapping/USB 脚的安全默认值。
#pragma once

#define TFT_SCLK 12   // 屏 SCL / CLK
#define TFT_MOSI 11   // 屏 SDA / DIN
#define TFT_DC    8   // 数据/命令
#define TFT_CS   10   // 片选
#define TFT_RST   9   // 复位
#define TFT_BL   14   // 背光（高电平亮）
