# 组件注册：源文件 + 依赖的 IDF 组件。
# REQUIRES 显式声明依赖，是 IDF component 化工程的规范写法。
idf_component_register(
    SRCS "main.c" "wifi.c" "chat_client.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_wifi esp_event esp_netif esp_http_client json driver esp_timer
)
