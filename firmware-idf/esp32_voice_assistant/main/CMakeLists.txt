# 组件注册：复用共享组件 bsp_wifi + bsp_audio；HTTP/GPIO/NVS 用 IDF 自带。
idf_component_register(
    SRCS "main.c" "voice_client.c"
    INCLUDE_DIRS "."
    REQUIRES bsp_wifi bsp_audio nvs_flash esp_http_client driver
)
