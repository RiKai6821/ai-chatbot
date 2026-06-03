/*
 * 阶段4 · 第5步：整合版语音助手（按键唤醒 → 录音 → 上传 → 播放 → 表情同步）
 * ================================================================
 * 完整链路（设备只做瘦客户端，大脑在电脑）：
 *   按 BOOT 键  → 表情[听] + 录音 RECORD_SECONDS 秒
 *              → 表情[想] + 把 WAV POST 给电脑 /voice
 *              → 收到回复音频(WAV) → 表情[说] + 播放
 *              → 回到 表情[待机]
 *
 * 依赖：
 *   - 屏幕库 "GFX Library for Arduino" (Arduino_GFX)
 *   - I2S：arduino-esp32 core 3.x 自带 ESP_I2S（无需另装）
 *   - WiFi.h / HTTPClient.h（core 自带）
 *
 * ⚠️ 服务端契约（电脑端需新增 /voice 接口，目前还没有，要我加再说）：
 *   POST {VOICE_URL}
 *     Header: X-Session-Id: <SESSION_ID>
 *     Body  : WAV 音频（16kHz/16bit/单声道）——设备录的音
 *   返回:
 *     Body  : WAV 音频（16kHz/16bit/单声道）——小智回复的语音
 *     (可选) Header: X-Reply-Text 文本，X-Emotion 情绪
 *   服务端内部 = STT(Paraformer) → 大模型 → TTS(返回16k PCM)。
 *
 * ⚠️ 本固件未在真实硬件验证；I2S 双口、引脚、WAV 头解析是最可能要调的地方。
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP_I2S.h>
#include <Arduino_GFX_Library.h>
#include "config.h"

// ── 屏幕 ──────────────────────────────────────────────────
Arduino_DataBus *bus = new Arduino_ESP32SPI(
    TFT_DC, TFT_CS, TFT_SCLK, TFT_MOSI, GFX_NOT_DEFINED);
Arduino_GFX *gfx = new Arduino_GC9A01(bus, TFT_RST, 0, true);

enum Mood { IDLE, LISTENING, THINKING, SPEAKING };

void drawEyes(Mood mood) {
  gfx->fillScreen(BLACK);
  uint16_t color = WHITE; int eyeH = 64; int dy = 0;
  switch (mood) {
    case LISTENING: color = CYAN;   eyeH = 72; dy = -6; break;
    case THINKING:  color = YELLOW; eyeH = 50; break;
    case SPEAKING:  color = GREEN;  eyeH = 60; break;
    default:        color = WHITE;  eyeH = 64; break;
  }
  int eyeW = 46, gap = 24;
  int lx = 120 - gap - eyeW / 2, rx = 120 + gap + eyeW / 2, ey = 120;
  gfx->fillRoundRect(lx - eyeW / 2, ey - eyeH / 2, eyeW, eyeH, 14, color);
  gfx->fillRoundRect(rx - eyeW / 2, ey - eyeH / 2, eyeW, eyeH, 14, color);
  gfx->fillCircle(lx, ey + dy, 12, BLACK);
  gfx->fillCircle(rx, ey + dy, 12, BLACK);
}

// ── 两个 I2S 实例：麦克风(收) 与 功放(发) ──────────────────
// ESP32-S3 有两个 I2S 端口，两实例应分别占用。若上板报端口冲突，
// 改成"录音前 begin 麦克风、播放前 begin 功放、用完 end()"的分时方案。
I2SClass i2sMic;
I2SClass i2sSpk;

void initAudio() {
  i2sMic.setPins(MIC_BCLK, MIC_WS, -1, MIC_SD, -1);
  if (!i2sMic.begin(I2S_MODE_STD, SAMPLE_RATE,
                    I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO))
    Serial.println("麦克风 I2S 初始化失败");

  i2sSpk.setPins(SPK_BCLK, SPK_LRC, SPK_DIN, -1, -1);
  if (!i2sSpk.begin(I2S_MODE_STD, SAMPLE_RATE,
                    I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO))
    Serial.println("功放 I2S 初始化失败");
}

// ── WiFi ──────────────────────────────────────────────────
void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("连接 WiFi：%s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t < 20000) { delay(400); Serial.print('.'); }
  Serial.println(WiFi.status() == WL_CONNECTED
                 ? "\n已连接，IP=" + WiFi.localIP().toString() : "\n连接失败");
}

// ── 一轮对话 ──────────────────────────────────────────────
void doOneTurn() {
  // 1) 听：录音
  drawEyes(LISTENING);
  Serial.printf("录音 %d 秒…\n", RECORD_SECONDS);
  size_t wavSize = 0;
  uint8_t *wav = i2sMic.recordWAV(RECORD_SECONDS, &wavSize);   // 带 WAV 头
  if (!wav || wavSize == 0) { Serial.println("录音失败"); drawEyes(IDLE); return; }

  // 2) 想：上传，等回复音频
  drawEyes(THINKING);
  ensureWiFi();
  if (WiFi.status() != WL_CONNECTED) { free(wav); drawEyes(IDLE); return; }

  HTTPClient http;
  http.begin(VOICE_URL);
  http.addHeader("Content-Type", "audio/wav");
  http.addHeader("X-Session-Id", SESSION_ID);
  http.setTimeout(30000);
  int code = http.POST(wav, wavSize);
  free(wav);

  if (code != 200) {
    Serial.printf("[/voice 返回 %d] %s\n", code, http.getString().c_str());
    http.end(); drawEyes(IDLE); return;
  }

  // 3) 说：把回复音频流式播给功放
  drawEyes(SPEAKING);
  WiFiClient *stream = http.getStreamPtr();
  int total = http.getSize();          // 可能为 -1（chunked）
  uint8_t buf[1024];
  bool headerSkipped = false;
  int got = 0;
  while (http.connected() && (total < 0 || got < total)) {
    size_t avail = stream->available();
    if (avail) {
      int n = stream->readBytes(buf, min(avail, sizeof(buf)));
      got += n;
      int off = 0;
      if (!headerSkipped) {            // 跳过 44 字节 WAV 头（服务端若返回裸 PCM 则设为 0）
        off = min(n, 44);
        headerSkipped = true;
      }
      if (n - off > 0) i2sSpk.write(buf + off, n - off);
    } else {
      delay(2);
    }
  }
  http.end();

  // 4) 回到待机
  drawEyes(IDLE);
  Serial.println("本轮结束。");
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(BTN_PIN, INPUT_PULLUP);
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);
  gfx->begin();
  drawEyes(IDLE);
  Serial.println("\n=== 小智 语音助手 ===");
  ensureWiFi();
  initAudio();
  Serial.println("就绪：按 BOOT 键说话。");
}

void loop() {
  // 按下 BOOT（低电平）触发一轮对话；做个简单去抖
  if (digitalRead(BTN_PIN) == LOW) {
    delay(30);
    if (digitalRead(BTN_PIN) == LOW) {
      doOneTurn();
      while (digitalRead(BTN_PIN) == LOW) delay(10);   // 等松手
    }
  }
  // 待机时偶尔眨个眼，更生动
  static uint32_t last = 0;
  if (millis() - last > 3000) { last = millis(); /* 可在此加眨眼动画 */ }
}
