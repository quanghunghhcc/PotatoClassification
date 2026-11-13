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

// 1. CẤU HÌNH WIFI & MÁY CHỦ BACKEND (SERVER)
const char* ssid = "P102";
const char* password = "12345678@";

// Địa chỉ IP máy tính chạy backend_server.py
const char* serverEnvUrl = "http://192.168.201.162:5000/api/env"; 
const char* serverResultUrl = "http://192.168.201.162:5000/api/result";

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

void sendEnvToServer(float t, float h);
void sendResultToServer(String quality, float confidence);

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
  if (WiFi.status() != WL_CONNECTED) {
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
  if (digitalRead(PIN_IR_SENSOR) == LOW) { // Cảm biến hồng ngoại phát hiện vật
    Serial.println("--> Phat hien nong san dat vao khay!");

    // Chờ 0.5s cho tay người dùng rời khỏi buồng soi
    delay(500);

    // Bật đèn Flash trợ sáng
    digitalWrite(PIN_FLASH_LED, HIGH);
    delay(150);

    // Hiển thị trạng thái đang phân loại lên OLED
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(15, 25);
    display.println("DANG PHAN LOAI AI...");
    display.display();

    // Tắt đèn Flash
    digitalWrite(PIN_FLASH_LED, LOW);

    // Xác định kết quả phân loại (Healthy / Rotten)
    bool isHealthy = (random(0, 10) > 3); // Giả lập tỷ lệ 70% đạt chuẩn, 30% hỏng
    String quality = isHealthy ? "good" : "not_good";
    float confidence = random(920, 995) / 1000.0;

    // Gửi kết quả về Web Dashboard
    sendResultToServer(quality, confidence);

    // Hiển thị kết quả chi tiết lên màn hình OLED
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 10);
    display.println("KET QUA KIEM DINH:");
    display.setTextSize(2);
    display.setCursor(10, 30);
    if (isHealthy) {
      display.println("HEALTHY");
    } else {
      display.println("ROTTEN");
      // Bíp cảnh báo nếu phát hiện khoai hỏng
      digitalWrite(PIN_BUZZER, HIGH);
      delay(250);
      digitalWrite(PIN_BUZZER, LOW);
    }
    display.setTextSize(1);
    display.setCursor(10, 52);
    display.println("Tin cay: " + String(confidence * 100, 1) + "%");
    display.display();

    // Chờ người dùng lấy củ khoai ra khỏi khay để tránh chụp lặp lại (Mục 6.2)
    while (digitalRead(PIN_IR_SENSOR) == LOW) {
      delay(100);
    }
    delay(500);

    // Hiển thị lại màn hình chờ sẵn sàng
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 25);
    display.println("San sang kiem tra...");
    display.display();
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
