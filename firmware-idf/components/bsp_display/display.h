#pragma once
#include "esp_err.h"

// 对话状态对应的表情
typedef enum {
    MOOD_IDLE,        // 待机（白眼）
    MOOD_LISTENING,   // 听（青色、睁大）
    MOOD_THINKING,    // 想（黄色、略眯）
    MOOD_SPEAKING,    // 说（绿色）
} display_mood_t;

// 初始化 GC9A01 圆屏（SPI + DMA）。
esp_err_t display_init(void);

// 画一帧眼睛。
//   blink:   0=完全睁开, 1=完全闭合（眨眼动画用）
//   gaze_dx/gaze_dy: 眼珠偏移（左右看/上下看）
void display_draw(display_mood_t mood, float blink, int gaze_dx, int gaze_dy);

// 便捷：完全睁开、正视前方。
void display_set_mood(display_mood_t mood);
