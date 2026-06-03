/*
 * 阶段4 · 第3步：INMP441 麦克风 I2S 录音自测
 * ---------------------------------------------------------------
 * 对标电脑端的 mic_test.py：录一段音，把"音量能量"打到串口，
 * 说话时数值应明显变大 —— 以此验证麦克风接线和 I2S 配置正确。
 * 这一步不联网；录到的数据先不发出去，确认录得到再说。
 *
 * 选项 B（联网上传，默认注释掉）：把录到的 WAV POST 给电脑保存，
 * 方便在电脑上用播放器听一耳朵。需要电脑端有一个接收 WAV 的接口
 * （服务端目前还没有，要我加再说）。见文件末尾说明。
 *
 * I2S 用 arduino-esp32 core 3.x 自带的 ESP_I2S 库（无需另装）。
 * ⚠️ 若串口能量一直≈0：先确认 L/R 接 GND、SD 接对、3V3 供电；
 *    再尝试把下面 begin 的 SLOT 从 MONO 左声道相关参数调一调。
 *
 * 开发板：ESP32S3 Dev Module（core 3.x）。
 */

#include <ESP_I2S.h>
#include "config.h"

I2SClass I2S;

void initMic() {
  // setPins(bclk, ws, dout(扬声器用,这里-1), din(麦克风输入), mclk)
  I2S.setPins(MIC_BCLK, MIC_WS, -1, MIC_SD, -1);
  // 标准 I2S，16kHz，16bit，单声道
  if (!I2S.begin(I2S_MODE_STD, MIC_SAMPLE_RATE,
                 I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("I2S(麦克风) 初始化失败！检查引脚/接线。");
    while (true) delay(1000);
  }
  Serial.println("麦克风 I2S 就绪。");
}

// 读一批样本，返回这批的最大绝对幅度（衡量音量）
int sampleLevel(int n = 1024) {
  int maxAmp = 0;
  for (int i = 0; i < n; i++) {
    int s = I2S.read();          // 返回一个 16bit 样本（int）
    if (s == -1 || s == 0x7fffffff) continue;   // 读失败/无数据
    int a = abs((int16_t)s);
    if (a > maxAmp) maxAmp = a;
  }
  return maxAmp;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== INMP441 麦克风自测 ===");
  initMic();
  Serial.println("开始监测音量：安静时应很小，说话/拍手时应明显变大。");
}

void loop() {
  int level = sampleLevel(1024);
  // 打成简单的条形图，直观看见音量
  int bars = level / 1000;
  if (bars > 40) bars = 40;
  Serial.printf("音量=%5d |", level);
  for (int i = 0; i < bars; i++) Serial.print('#');
  Serial.println();
  delay(120);
}

/*
 * 选项 B：把录音上传到电脑（需要服务端新增一个接收接口）
 * ---------------------------------------------------------------
 * ESP_I2S 提供便捷的 recordWAV：
 *
 *   size_t wavSize = 0;
 *   uint8_t *wav = I2S.recordWAV(3, &wavSize);   // 录 3 秒，返回带头的 WAV
 *   // 然后用 HTTPClient POST 给电脑：
 *   //   http.begin("http://你的电脑IP:8000/upload_wav");
 *   //   http.addHeader("Content-Type", "audio/wav");
 *   //   http.POST(wav, wavSize);
 *   free(wav);
 *
 * 服务端要相应加一个 /upload_wav 接口，把收到的字节存成 .wav 文件。
 * 目前 api_server.py 还没有这个接口 —— 需要的话我来加。
 */
