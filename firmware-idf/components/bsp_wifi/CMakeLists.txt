# 共享组件：WiFi 联网。供 esp32_chat / esp32_voice_assistant 等多个应用复用。
idf_component_register(
    SRCS "wifi.c"
    INCLUDE_DIRS "."
    REQUIRES esp_wifi esp_event esp_netif
)
