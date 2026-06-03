idf_component_register(
    SRCS "main.c" "i2s_mic.c" "i2s_speaker.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_timer
)
