# 共享组件：I2S 音频（INMP441 录音 + MAX98357A 播放）。
idf_component_register(
    SRCS "i2s_mic.c" "i2s_speaker.c"
    INCLUDE_DIRS "."
    REQUIRES driver
)
