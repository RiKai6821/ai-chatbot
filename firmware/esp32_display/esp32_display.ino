/*
 * 阶段4 · 第2步：点亮 GC9A01 圆屏 + 画"会眨眼的表情"
 * ---------------------------------------------------------------
 * 这一步只验证屏幕：能显示一对眼睛，并在 4 种状态间切换演示：
 *   IDLE（待机·定时眨眼）/ LISTENING（听·睁大）/
 *   THINKING（想·左右看）/ SPEAKING（说·上下动）
 * 不联网、不接音频，纯屏幕自测。整合到语音助手后由对话状态来驱动表情。
 *
 * 为什么用 Arduino_GFX 直接画而不是 LVGL：
 *   直接画几何图形实现表情，依赖少、最易一次跑通；LVGL 需要庞大的 lv_conf.h
 *   配置，没硬件时极易出错。等基础跑通后想升级 LVGL 再说。
 *
 * 依赖库（Arduino IDE 库管理器搜装）：
 *   - "GFX Library for Arduino"  by moononournation   (即 Arduino_GFX)
 * 开发板：ESP32S3 Dev Module（arduino-esp32 core 3.x）。
 *
 * 接线（默认引脚见 config.h，可改）：
 *   屏 VCC->3V3  GND->GND  其余按 config.h。背光 BL 接 TFT_BL。
 */

#include <Arduino_GFX_Library.h>
#include "config.h"

// ── 显示驱动 ──────────────────────────────────────────────
Arduino_DataBus *bus = new Arduino_ESP32SPI(
    TFT_DC, TFT_CS, TFT_SCLK, TFT_MOSI, GFX_NOT_DEFINED /* MISO 不用 */);
// 最后的 true = IPS 屏（GC9A01 圆屏通常是 IPS，颜色更正）
Arduino_GFX *gfx = new Arduino_GC9A01(bus, TFT_RST, 0 /*旋转*/, true /*IPS*/);

// 屏幕 240x240，圆心和半径
static const int CX = 120, CY = 120;

// 对话状态 —— 整合进语音助手后，由"正在听/想/说"来设置它
enum Mood { IDLE, LISTENING, THINKING, SPEAKING };

// ── 画一对眼睛（核心）────────────────────────────────────
// blink: 0=完全睁开, 1=完全闭合（用于眨眼动画）
// dx/dy: 眼珠偏移（左右看 / 上下看）
void drawEyes(Mood mood, float blink, int dx, int dy) {
  gfx->fillScreen(BLACK);

  uint16_t color = WHITE;
  int eyeW = 46, eyeH = 64;     // 眼白尺寸
  switch (mood) {
    case LISTENING: color = CYAN;  eyeH = 72; break;  // 睁大
    case THINKING:  color = YELLOW; eyeH = 50; break; // 略眯
    case SPEAKING:  color = GREEN; eyeH = 60; break;
    default:        color = WHITE; eyeH = 64; break;
  }

  int gap = 24;                  // 两眼间距的一半
  int lx = CX - gap - eyeW / 2;  // 左眼中心
  int rx = CX + gap + eyeW / 2;  // 右眼中心
  int ey = CY;

  int h = (int)(eyeH * (1.0f - blink));   // 眨眼时高度变小
  if (h < 4) h = 4;

  // 眼白（圆角矩形）
  gfx->fillRoundRect(lx - eyeW / 2, ey - h / 2, eyeW, h, 14, color);
  gfx->fillRoundRect(rx - eyeW / 2, ey - h / 2, eyeW, h, 14, color);

  // 眼珠（睁开到一定程度才画）
  if (blink < 0.6f) {
    int pr = 12;
    gfx->fillCircle(lx + dx, ey + dy, pr, BLACK);
    gfx->fillCircle(rx + dx, ey + dy, pr, BLACK);
  }
}

// 眨一次眼（睁->闭->睁）
void blinkOnce(Mood mood) {
  for (float b = 0; b <= 1.0f; b += 0.25f) { drawEyes(mood, b, 0, 0); delay(18); }
  for (float b = 1.0f; b >= 0; b -= 0.25f) { drawEyes(mood, b, 0, 0); delay(18); }
}

void setup() {
  Serial.begin(115200);
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);       // 开背光
  if (!gfx->begin()) Serial.println("屏幕初始化失败：检查接线/引脚/库");
  gfx->fillScreen(BLACK);
  Serial.println("屏幕就绪，开始演示四种表情。");
}

void loop() {
  // 依次演示四种状态，每种维持一会儿并做点小动作
  // IDLE：定时眨眼
  drawEyes(IDLE, 0, 0, 0);
  for (int i = 0; i < 3; i++) { delay(900); blinkOnce(IDLE); }

  // LISTENING：睁大、轻微上看
  drawEyes(LISTENING, 0, 0, -6); delay(1500);

  // THINKING：眼珠左右来回看
  for (int i = 0; i < 2; i++) {
    for (int dx = -10; dx <= 10; dx += 5) { drawEyes(THINKING, 0, dx, 0); delay(80); }
    for (int dx = 10; dx >= -10; dx -= 5) { drawEyes(THINKING, 0, dx, 0); delay(80); }
  }

  // SPEAKING：眼睛上下轻动，模拟说话节奏
  for (int i = 0; i < 6; i++) {
    drawEyes(SPEAKING, 0, 0, -4); delay(120);
    drawEyes(SPEAKING, 0, 0,  4); delay(120);
  }
}
