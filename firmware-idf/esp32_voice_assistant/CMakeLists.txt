# 工程级 CMake：整合语音助手（按键→录音→/voice→播放，多任务+状态机）。
cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32_voice_assistant)
