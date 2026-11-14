/*
  =============================================================================
  ĐỒ ÁN: HỆ THỐNG PHÂN LOẠI VÀ GIÁM SÁT CHẤT LƯỢNG NÔNG SẢN (EDGE AI & IOT)
  File: esp32_iot_node.ino
  Phần cứng: AI-Thinker ESP32-CAM
  Cấu hình chân theo đúng Mục 5 trong tài liệu đồ án:
    - OLED 0.96" SSD1306 (I2C): SDA -> GPIO14, SCL -> GPIO15
    - Cảm biến vật cản hồng ngoại (OUT): GPIO2 (kéo xuống LOW khi có vật)
    - Cảm biến môi trường DHT11 (DATA): GPIO13
    - Còi cảnh báo Buzzer: GPIO12
    - Đèn Flash trợ sáng: GPIO4
  =============================================================================
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include "esp_camera.h"

// 1. CẤU HÌNH WIFI & MÁY CHỦ BACKEND (SERVER)
const char* ssid = "P102";
const char* password = "12345678@";

// Địa chỉ IP máy tính chạy backend_server.py
const char* serverEnvUrl = "http://192.168.201.162:5000/api/env"; 
const char* serverResultUrl = "http://192.168.201.162:5000/api/result";
const char* classifierUrl = "http://192.168.201.162:5001/classify";

// 2. ĐỊNH NGHĨA CHÂN NGOẠI VI (THEO MỤC 5 FILE DOCX)
#define PIN_OLED_SDA   14
#define PIN_OLED_SCL   15
#define PIN_IR_SENSOR   2
#define PIN_DHT11      13
#define PIN_BUZZER     12
#define PIN_FLASH_LED   4

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
DHT dht(PIN_DHT11, DHT11);

unsigned long lastDhtTime = 0;
const unsigned long DHT_INTERVAL = 6000; // Đọc DHT11 mỗi 6 giây
bool itemWasPresent = false;
unsigned long lastCaptureTime = 0;
const unsigned long CAPTURE_COOLDOWN = 1200;

void sendEnvToServer(float t, float h);
void sendResultToServer(String quality, float confidence);

bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 5;
  config.pin_d1 = 18;
  config.pin_d2 = 19;
  config.pin_d3 = 21;
  config.pin_d4 = 36;
  config.pin_d5 = 39;
  config.pin_d6 = 34;
  config.pin_d7 = 35;
  config.pin_xclk = 0;
  config.pin_pclk = 22;
  config.pin_vsync = 25;
  config.pin_href = 23;
  config.pin_sccb_sda = 26;
  config.pin_sccb_scl = 27;
  config.pin_pwdn = 32;
  config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = psramFound() ? 2 : 1;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }
  return true;
}

bool classifyCapturedFrame(String& quality, float& confidence) {
  camera_fb_t* frame = esp_camera_fb_get();
  if (frame == nullptr) {
    Serial.println("Camera capture failed");
    return false;
  }

  HTTPClient http;
  http.setTimeout(12000);
  http.begin(classifierUrl);
  http.addHeader("Content-Type", "image/jpeg");
  int status = http.POST(frame->buf, frame->len);
  String response = status > 0 ? http.getString() : "";
  http.end();
  esp_camera_fb_return(frame);

  if (status != HTTP_CODE_OK) {
    Serial.printf("Classifier HTTP error: %d %s\n", status, response.c_str());
    return false;
  }

  int qualityKey = response.indexOf("\"quality\"");
  int confidenceKey = response.indexOf("\"confidence\"");
  int colon = response.indexOf(':', qualityKey);
  int quote1 = response.indexOf('\"', colon + 1);
  int quote2 = response.indexOf('\"', quote1 + 1);
  int confidenceColon = response.indexOf(':', confidenceKey);
  if (qualityKey < 0 || confidenceKey < 0 || colon < 0 || quote1 < 0 || quote2 < 0 || confidenceColon < 0) {
    Serial.println("Invalid classifier response");
    return false;
  }

  quality = response.substring(quote1 + 1, quote2);
  confidence = response.substring(confidenceColon + 1).toFloat();
  return (quality == "good" || quality == "not_good") && confidence >= 0.0 && confidence <= 1.0;
}

void setup() {
  Serial.begin(115200);

  // Cấu hình các chân GPIO
  pinMode(PIN_IR_SENSOR, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_FLASH_LED, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_FLASH_LED, LOW);

  // Khởi tạo màn hình OLED trên chân GPIO14 (SDA) và GPIO15 (SCL)
  Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("[!] Không tìm thấy màn hình OLED");
  } else {
    display.clearDisplay();
    display.setTextColor(WHITE);
    display.setTextSize(1);
    display.setCursor(10, 20);
    display.println("HE THONG IOT & AI");
    display.setCursor(10, 35);
    display.println("Dang ket noi WiFi...");
    display.display();
  }

  // Khởi tạo cảm biến nhiệt độ DHT11
  dht.begin();

  if (!initCamera()) {
    display.clearDisplay();
    display.setCursor(0, 20);
    display.println("Loi khoi tao camera");
    display.display();
  }

  // Kết nối mạng WiFi
  WiFi.begin(ssid, password);
  unsigned long startWifi = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startWifi < 15000)) {
    delay(500);
    Serial.print(".");
  }

  display.clearDisplay();
  display.setCursor(0, 10);
  display.println("KHOAI TAY PHAN LOAI");
  display.setCursor(0, 25);
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi da ket noi! IP: " + WiFi.localIP().toString());
    display.println("IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\nChua ket noi duoc WiFi");
    display.println("Loi ket noi WiFi");
  }
  display.setCursor(0, 45);
  display.println("San sang kiem tra!");
  display.display();

  // Bíp nhẹ 1 tiếng khởi động
  digitalWrite(PIN_BUZZER, HIGH);
  delay(120);
  digitalWrite(PIN_BUZZER, LOW);
}

void loop() {
  unsigned long now = millis();

  // Tự động kết nối lại WiFi nếu bị ngắt
  static unsigned long lastReconnectAttempt = 0;
  if (WiFi.status() != WL_CONNECTED && now - lastReconnectAttempt >= 10000) {
    lastReconnectAttempt = now;
    WiFi.reconnect();
  }

  // 1. ĐỊNH KỲ ĐỌC CẢM BIẾN DHT11 VÀ GỬI VỀ SERVER (Mục 6.4 trong docx)
  if (now - lastDhtTime >= DHT_INTERVAL) {
    lastDhtTime = now;
    float t = dht.readTemperature();
    float h = dht.readHumidity();

    if (!isnan(t) && !isnan(h)) {
      sendEnvToServer(t, h);

      // Cảnh báo nếu nhiệt độ > 32°C hoặc độ ẩm bất thường (Bíp lặp 3 lần)
      if (t > 32.0 || h < 50.0 || h > 85.0) {
        for (int i = 0; i < 3; i++) {
          digitalWrite(PIN_BUZZER, HIGH);
          delay(100);
          digitalWrite(PIN_BUZZER, LOW);
          delay(100);
        }
      }
    }
  }

  // 2. PHÁT HIỆN NÔNG SẢN ĐẶT VÀO KHAY BẰNG CẢM BIẾN VẬT CẢN (Mục 6.2 trong docx)
  // IR active LOW: ch?p m?t ?nh ? c?nh xu?ng, kh�ng ph�n lo?i ng?u nhi�n.
  bool itemPresent = digitalRead(PIN_IR_SENSOR) == LOW;
  if (itemPresent && !itemWasPresent && now - lastCaptureTime >= CAPTURE_COOLDOWN) {
    itemWasPresent = true;
    lastCaptureTime = now;
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(10, 25);
    display.println("DANG CHUP VA PHAN LOAI");
    display.display();

    digitalWrite(PIN_FLASH_LED, HIGH);
    delay(120);
    String quality;
    float confidence = 0.0;
    bool classified = classifyCapturedFrame(quality, confidence);
    digitalWrite(PIN_FLASH_LED, LOW);

    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 10);
    if (classified) {
      sendResultToServer(quality, confidence);
      display.println("KET QUA AI:");
      display.setTextSize(2);
      display.setCursor(10, 30);
      display.println(quality == "good" ? "GOOD" : "NOT GOOD");
      display.setTextSize(1);
      display.setCursor(10, 52);
      display.print("Tin cay: ");
      display.print(confidence * 100.0, 1);
      display.print("%");
      if (quality == "not_good") {
        digitalWrite(PIN_BUZZER, HIGH);
        delay(180);
        digitalWrite(PIN_BUZZER, LOW);
      }
    } else {
      display.println("LOI CAMERA / AI SERVER");
      Serial.println("Capture or classification failed; no result was recorded.");
    }
    display.display();
  }
  if (!itemPresent) {
    itemWasPresent = false;
  }
}

void sendResultToServer(String quality, float confidence) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverResultUrl);
    http.addHeader("Content-Type", "application/json");

    String json = "{\"device\":\"esp32-cam-01\",\"quality\":\"" + quality + "\",\"confidence\":" + String(confidence, 4) + "}";
    int httpCode = http.POST(json);
    Serial.print("--> Gui ket qua kiem dinh ve Server. Ma HTTP: ");
    Serial.println(httpCode);
    http.end();
  }
}

void sendEnvToServer(float t, float h) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverEnvUrl);
    http.addHeader("Content-Type", "application/json");

    String json = "{\"device\":\"esp32-cam-01\",\"temp\":" + String(t, 1) + ",\"hum\":" + String(h, 1) + "}";
    int httpCode = http.POST(json);
    Serial.print("--> Gui nhiet do/do am ve Server. Ma HTTP: ");
    Serial.println(httpCode);
    http.end();
  }
}
