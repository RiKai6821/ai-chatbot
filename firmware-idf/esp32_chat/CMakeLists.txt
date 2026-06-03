# 工程级 CMake：ESP-IDF 标准入口。
# 构建：idf.py set-target esp32s3 && idf.py menuconfig && idf.py build flash monitor
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32_chat)
