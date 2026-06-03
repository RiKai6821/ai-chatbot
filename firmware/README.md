# 固件（阶段4）· ESP32-S3

设备是"瘦客户端"：它只负责**收输入 → WiFi 发 HTTP → 显示/播报回复**，大脑（大模型）在你电脑上的 `api_server.py` 里。API Key 永远不进设备。

## 目录

- `esp32_chat/` —— **第1步：联网 + 调通 `/chat`**，在串口里打字和小智对话。
  - `esp32_chat.ino` —— 主程序
  - `config.h` —— 你的 WiFi 和电脑 IP（**烧录前必须改**）

> 路线图后续步骤（点屏 LVGL 表情 → INMP441 录音 → MAX98357A 播放 → 全链路语音）见根目录 README 第7节，后面再逐个加。

---

## 跑通第1步（串口文字对话）

### 1. 装开发环境（Arduino IDE，最省事）
1. 装 [Arduino IDE 2.x](https://www.arduino.cc/en/software)。
2. **开发板**：`文件 → 首选项 → 附加开发板管理器网址` 填
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`，
   再到 `工具 → 开发板 → 开发板管理器` 搜 **esp32** 安装。
3. **库**：`工具 → 管理库`，搜 **ArduinoJson**（作者 Benoit Blanchon）安装。
   （`WiFi.h`、`HTTPClient.h` 是 esp32 板子自带，无需另装。）

### 2. 启动电脑上的服务端（关键：要带 `--host 0.0.0.0`）
```powershell
# 在项目根目录
uvicorn api_server:app --host 0.0.0.0 --port 8000
```
查你电脑的局域网 IP：
```powershell
ipconfig   # 看 "IPv4 地址"，形如 192.168.1.10
```
先在电脑自己测一下接口活着：浏览器开 `http://127.0.0.1:8000/docs`。

### 3. 改 `config.h`
```c
#define WIFI_SSID   "你的WiFi名称"      // 必须 2.4GHz
#define WIFI_PASS   "你的WiFi密码"
#define SERVER_URL  "http://192.168.1.10:8000/chat"   // 换成你电脑的 IP
```

### 4. 烧录 + 打开串口
1. 开发板选 **ESP32S3 Dev Module**，选对端口，点上传。
2. 打开 `工具 → 串口监视器`，波特率 **115200**，右下角行结束符选 **换行(NL)**。
3. 开机会自动问一句"你好"做自检；之后在顶部输入框打字回车即可对话。

预期串口输出：
```
=== 小智 · ESP32 串口对话 ===
正在连接 WiFi：xxx ....
已连接，设备 IP：192.168.1.23
[自检] 发送一句『你好』测试链路…
小智：你好呀，我是小智……
```

---

## 排错清单

| 现象 | 原因 / 解决 |
|------|------|
| 一直 `连接失败` | WiFi 名/密码错；或路由器是 5GHz——ESP32 多数只支持 2.4GHz |
| `[网络错误] connection refused` | 服务端没带 `--host 0.0.0.0`；或 IP/端口写错 |
| 连得上 WiFi 但请求超时 | 电脑防火墙挡了 8000 端口；或手机热点做了 AP 隔离，换同一路由器 |
| 串口中文乱码 | 监视器波特率不是 115200 |
| `[服务端返回 400]` | message 为空——别发空行 |
| `[服务端返回 502]` | 电脑端 `.env` 的大模型 Key 失效/欠费 |

---

## 说明

- 本固件已按服务端 `ChatRequest`（`{"session_id","message"}` → `{"reply"}`）对齐，用 ArduinoJson 拼/解 JSON，能正确处理中文和引号转义。
- ⚠️ 这段代码**尚未在真实 ESP32-S3 上烧录验证过**（开发机上没有硬件和编译工具链）。逻辑和接口对齐是对的，但首次上板若有编译/管脚细节问题，把串口报错发我，我来调。
- 想换成"能办事"的版本：把 `config.h` 的 `SERVER_URL` 末尾从 `/chat` 改成 `/agent` 即可，设备代码不用动（不过 `/agent` 返回里多了 `tools_used` 字段，当前固件只取 `reply`，也能正常用）。
