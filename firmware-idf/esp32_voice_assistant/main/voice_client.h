#pragma once
#include "esp_err.h"

// 对话状态（驱动表情/指示，这里用日志体现；后续可接 GC9A01/LED）。
typedef enum {
    ST_IDLE,        // 待机
    ST_LISTENING,   // 听（录音中）
    ST_THINKING,    // 想（已上传，等服务器）
    ST_SPEAKING,    // 说（播放回复）
} xz_state_t;

typedef void (*xz_state_cb)(xz_state_t st);

// 完成一轮：录音 → 流式上传到 /voice → 流式播放回复音频。
// 全程不缓存整段音频（边录边传、边收边播），无需大内存/PSRAM。
esp_err_t voice_do_turn(xz_state_cb on_state);
