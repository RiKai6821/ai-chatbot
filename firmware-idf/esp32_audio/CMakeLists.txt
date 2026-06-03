# 工程级 CMake：ESP-IDF I2S 音频自测（INMP441 录音 + MAX98357A 播放）。
# 构建：idf.py set-target esp32s3 && idf.py menuconfig && idf.py build flash monitor
cmake_minimum_required(VERSION 3.16)
# 引入上层共享组件（bsp_audio）
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32_audio)
