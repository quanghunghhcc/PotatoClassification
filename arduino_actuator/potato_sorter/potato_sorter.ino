/*
  =============================================================================
  ĐỒ ÁN TỐT NGHIỆP: HỆ THỐNG PHÂN LOẠI KHOAI TÂY TỰ ĐỘNG (IoT & AI)
  File: potato_sorter.ino
  Phần cứng: Arduino Uno / Nano hoặc ESP32
  Chức năng: Nhận tín hiệu từ mô hình AI (qua cổng Serial/UART) để điều khiển:
             - Servo Motor: Gạt củ khoai tây hỏng ra khỏi băng chuyền
             - Còi Buzzer: Bíp cảnh báo khi phát hiện sản phẩm lỗi
             - Đèn LED: Xanh (Đạt chuẩn) / Đỏ (Hỏng)
  =============================================================================
*/

#include <Servo.h>

// Định nghĩa chân kết nối phần cứng (Pin Configuration)
const int SERVO_PIN  = 9;    // Chân tín hiệu điều khiển Servo gạt
const int LED_GOOD   = 4;    // LED xanh lá: Khoai tây đạt chuẩn
const int LED_BAD    = 5;    // LED đỏ: Khoai tây hỏng
const int BUZZER_PIN = 6;    // Chân điều khiển Còi cảnh báo

// Góc xoay Servo
const int ANGLE_REST = 0;    // Vị trí nghỉ (không cản băng chuyền)
const int ANGLE_KICK = 85;   // Vị trí gạt khoai tây lỗi

Servo sorterServo;

void setup() {
  // Khởi tạo giao tiếp nối tiếp Serial tốc độ 9600 baud (khớp với file Python)
  Serial.begin(9600);

  // Cấu hình các chân I/O
  pinMode(LED_GOOD, OUTPUT);
  pinMode(LED_BAD, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  // Gắn chân Servo và đưa về vị trí nghỉ ban đầu
  sorterServo.attach(SERVO_PIN);
  sorterServo.write(ANGLE_REST);

  // Bật đèn xanh báo hiệu hệ thống sẵn sàng hoạt động
  digitalWrite(LED_GOOD, HIGH);
  digitalWrite(LED_BAD, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  // Test còi khởi động (bíp nhẹ 1 tiếng)
  digitalWrite(BUZZER_PIN, HIGH);
  delay(150);
  digitalWrite(BUZZER_PIN, LOW);
}

void loop() {
  // Kiểm tra xem có dữ liệu gửi từ máy tính/Edge AI qua cổng Serial hay không
  if (Serial.available() > 0) {
    char command = Serial.read();

    if (command == '1') {
      // === PHÁT HIỆN KHOAI TÂY HỎNG (NOT GOOD) ===
      digitalWrite(LED_GOOD, LOW);
      digitalWrite(LED_BAD, HIGH);
      digitalWrite(BUZZER_PIN, HIGH); // Bật còi báo động

      // 1. Xoay Servo để gạt củ khoai hỏng ra ngoài
      sorterServo.write(ANGLE_KICK);
      delay(400); // Thời gian gạt

      // 2. Thu cánh tay gạt về vị trí ban đầu
      sorterServo.write(ANGLE_REST);
      digitalWrite(BUZZER_PIN, LOW); // Tắt còi

      delay(300);
      digitalWrite(LED_BAD, LOW);
      digitalWrite(LED_GOOD, HIGH); // Trả lại trạng thái đèn xanh

    } else if (command == '0') {
      // === KHOAI TÂY ĐẠT CHUẨN (GOOD) ===
      digitalWrite(LED_GOOD, HIGH);
      digitalWrite(LED_BAD, LOW);
      digitalWrite(BUZZER_PIN, LOW);
      // Không cần gạt, khoai tiếp tục chạy trên băng chuyền
    }
  }
}
