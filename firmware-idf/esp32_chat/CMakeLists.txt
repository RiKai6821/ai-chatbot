# 工程级 CMake：ESP-IDF 标准入口。
# 构建：idf.py set-target esp32s3 && idf.py menuconfig && idf.py build flash monitor
cmake_minimum_required(VERSION 3.16)
# 引入上层共享组件（bsp_wifi 等）
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32_chat)
