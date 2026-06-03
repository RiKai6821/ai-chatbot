# 组件注册：联网用共享组件 bsp_wifi，HTTP/JSON 用 IDF 自带组件。
idf_component_register(
    SRCS "main.c" "chat_client.c"
    INCLUDE_DIRS "."
    REQUIRES bsp_wifi nvs_flash esp_http_client json driver
)
