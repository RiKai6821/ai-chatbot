# 共享组件：GC9A01 圆屏（esp_lcd + SPI + DMA）+ 表情渲染。
# esp_lcd_gc9a01 由 idf_component.yml 经组件管理器自动拉取。
idf_component_register(
    SRCS "display.c"
    INCLUDE_DIRS "."
    REQUIRES esp_lcd driver
)
