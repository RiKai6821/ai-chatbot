// ── 把下面三项改成你自己的，然后再烧录 ──────────────────────
//
// 安全提醒：这里只放 WiFi 和"你电脑的地址"，绝不放大模型 API Key！
// Key 永远只在电脑/服务器的 .env 里，设备是"瘦客户端"，不碰 Key。

#pragma once

// 1) 你的 WiFi（ESP32 多数只支持 2.4GHz，连不上先确认不是 5GHz）
#define WIFI_SSID   "你的WiFi名称"
#define WIFI_PASS   "你的WiFi密码"

// 2) 你电脑（跑 api_server.py 的那台）在局域网里的地址。
//    查 IP：Windows 上 PowerShell 运行  ipconfig  看 IPv4 地址（如 192.168.1.10）。
//    启动服务端要带 --host 0.0.0.0 ，否则设备连不上：
//      uvicorn api_server:app --host 0.0.0.0 --port 8000
#define SERVER_URL  "http://192.168.1.10:8000/chat"

// 3) 这台设备的会话 id（不同设备用不同 id，记忆互不串）
#define SESSION_ID  "esp32-1"
