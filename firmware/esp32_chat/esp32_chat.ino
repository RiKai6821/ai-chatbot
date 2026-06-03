/*
 * 阶段4 · 第1步：ESP32-S3 联网 + 调通服务端 /chat（C/C++ 固件）
 * ---------------------------------------------------------------
 * 这一步只验证一件事：设备能通过 WiFi 把你打的字发给电脑上的 Python 接口，
 * 并在串口监视器里打印出大模型的回复。屏幕、麦克风、喇叭都还没上。
 *
 * 关键认知（README 第7节）：单片机不跑大模型、不跑 Python，它只负责
 * 收输入 → 用 WiFi 发 HTTP → 拿回回复显示/播报。大脑在服务器。
 *
 * 用法：
 *   1) 改 config.h 里的 WIFI_SSID / WIFI_PASS / SERVER_URL。
 *   2) 电脑上启动服务端（务必带 --host 0.0.0.0）：
 *        uvicorn api_server:app --host 0.0.0.0 --port 8000
 *      并确认手机/电脑和 ESP32 在同一个 WiFi。
 *   3) 烧录本固件，打开串口监视器（波特率 115200，行结束符设为"换行"）。
 *   4) 在串口监视器顶部输入框打字回车 → 看小智的回复。
 *
 * 依赖库（Arduino IDE 库管理器里装）：
 *   - ArduinoJson  by Benoit Blanchon（用于安全地拼/解 JSON，避免手动转义出错）
 *   开发板管理器里装 "esp32 by Espressif Systems"，开发板选 ESP32S3 Dev Module。
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"

// ── 连接 WiFi（带重连）──────────────────────────────────────
void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("正在连接 WiFi：%s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(400);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n已连接，设备 IP：%s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n连接失败：检查 WiFi 名称/密码，且必须是 2.4GHz。");
  }
}

// ── 发一句话给 /chat，返回小智的回复（失败返回空串）──────────
String askXiaozhi(const String &message) {
  ensureWiFi();
  if (WiFi.status() != WL_CONNECTED) return "";

  // 1) 用 ArduinoJson 构造请求体，自动处理引号/中文等转义
  JsonDocument reqDoc;
  reqDoc["session_id"] = SESSION_ID;
  reqDoc["message"] = message;
  String body;
  serializeJson(reqDoc, body);

  // 2) 发 POST
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(30000);            // 大模型生成可能要几秒，给足超时
  int code = http.POST(body);

  if (code <= 0) {
    Serial.printf("[网络错误] %s —— 检查电脑IP、端口、是否带 --host 0.0.0.0\n",
                  http.errorToString(code).c_str());
    http.end();
    return "";
  }
  String resp = http.getString();
  http.end();

  if (code != 200) {
    Serial.printf("[服务端返回 %d] %s\n", code, resp.c_str());
    return "";
  }

  // 3) 解析 {"reply": "..."}
  JsonDocument respDoc;
  DeserializationError err = deserializeJson(respDoc, resp);
  if (err) {
    Serial.printf("[JSON 解析失败] %s\n原始内容：%s\n", err.c_str(), resp.c_str());
    return "";
  }
  return String((const char *)(respDoc["reply"] | ""));
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== 小智 · ESP32 串口对话 ===");
  ensureWiFi();

  // 开机自检：先自动问一句，确认整条链路通
  Serial.println("\n[自检] 发送一句『你好』测试链路…");
  String hello = askXiaozhi("你好，用一句话介绍你自己");
  if (hello.length()) Serial.printf("小智：%s\n", hello.c_str());

  Serial.println("\n现在可以在上面的输入框打字（回车发送）开始对话：");
}

void loop() {
  // 从串口读一行（在串口监视器输入框打字 + 回车）
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) return;

    Serial.printf("你：%s\n", line.c_str());
    String reply = askXiaozhi(line);
    if (reply.length()) {
      Serial.printf("小智：%s\n", reply.c_str());
    } else {
      Serial.println("（没拿到回复，看上面的错误提示排查）");
    }
  }
}
