# 组件注册：音频用共享组件 bsp_audio。
idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES bsp_audio
)
