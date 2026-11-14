# Hướng dẫn huấn luyện và nạp model lên ESP32-CAM

> Tài liệu này dùng **CNN TinyML 96×96, INT8** trong `esp32_iot_system/tinyml_idf`. Model chạy trên ESP32-CAM; backend chỉ nhận kết quả để hiển thị. Không dùng sketch Arduino cũ để chạy model này.

## 1. Project cần những gì?

- Board AI-Thinker ESP32-CAM có PSRAM và camera OV2640.
- Cảm biến IR digital, đầu ra active LOW.
- Máy tính cài WSL Ubuntu để train model và Windows cài ESP-IDF để build/nạp firmware.
- Dataset nguồn nằm trong `dataset/good` và `dataset/not_good`.

Model dùng input RGB 96×96, nhãn `good=0`, `not_good=1`. Khi cảm biến IR ở GPIO2 chuyển LOW, camera chụp ảnh, ESP32 resize ảnh và phân loại ngay trên chip. Wi-Fi chỉ dùng để gửi kết quả lên backend; mất Wi-Fi không ngăn inference.

## 2. Train model (chỉ làm khi muốn huấn luyện lại)

Nếu đã có file `esp32_iot_system/tinyml_idf/main/potato_tiny_model_data.h` từ Git thì có thể bỏ qua bước này và đi đến phần 3.

Mở Ubuntu/WSL, vào thư mục project. Ví dụ nếu clone mới:

```bash
cd ~
git clone https://github.com/quanghunghhcc/PotatoClassification.git
cd PotatoClassification
```

Tạo môi trường Python và cài thư viện một lần:

```bash
python3 -m venv .venv-tinyml
source .venv-tinyml/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements_tinyml.txt
```

Train và export model:

```bash
python train_tinyml.py
```

Script tự chia ảnh train/validation/test, train tối đa 50 epoch (có early stopping), đánh giá model INT8 và ghi header C++ mà firmware nhúng vào flash. Train xong cần thấy dòng `Generated firmware model header` và file:

```text
esp32_iot_system/tinyml_idf/main/potato_tiny_model_data.h
```

Các model và báo cáo trung gian nằm trong `models/tinyml/`; thư mục này không cần đưa lên Git để nạp chip. Nếu train trong một bản clone WSL khác, hãy chép `potato_tiny_model_data.h` sang đúng thư mục `main` của bản project Windows trước khi build.

## 3. Cấu hình Wi-Fi và backend (tùy chọn)

Mở `esp32_iot_system/tinyml_idf/main/user_config.h`, sửa:

```cpp
#define WIFI_SSID "TEN_WIFI_2.4G"
#define WIFI_PASSWORD "MAT_KHAU_WIFI"
#define BACKEND_RESULT_URL "http://IP_MAY_TINH:5000/api/result"
```

ESP32-CAM và máy chạy backend phải cùng mạng Wi-Fi 2.4 GHz. Lấy IPv4 của máy chạy backend bằng `ipconfig`, dùng địa chỉ IPv4 của adapter Wi-Fi/LAN thay cho `IP_MAY_TINH`; không dùng `localhost` hoặc `127.0.0.1` trong URL của ESP32.

Nếu cần dashboard, chạy backend trên Windows để ESP32-CAM truy cập được trong mạng LAN. Mở PowerShell ở thư mục project. Backend chỉ dùng thư viện có sẵn của Python, không cần cài thêm package:

```powershell
py -3.11 backend_server.py
```

Dashboard trên máy đó: `http://localhost:5000/dashboard`. Cho phép Python nhận kết nối trên mạng Private nếu Windows Firewall hỏi. Nếu chỉ muốn thử model trên chip, có thể bỏ qua backend; firmware vẫn phân loại cục bộ. Trước khi commit/push, khôi phục placeholder trong `user_config.h` để không tải mật khẩu Wi-Fi lên Git:

```powershell
git restore esp32_iot_system/tinyml_idf/main/user_config.h
```

## 4. Kết nối board

ESP32-CAM thường cần USB-to-UART 3.3 V để nạp chương trình:

| USB-to-UART | AI-Thinker ESP32-CAM |
|---|---|
| TXD | U0R / GPIO3 |
| RXD | U0T / GPIO1 |
| GND | GND |
| 5 V ổn định | 5V |

Dùng nguồn 5 V ổn định cho board; không đưa tín hiệu UART 5 V vào ESP32. Cảm biến IR nối VCC theo thông số module, GND chung với ESP32-CAM, OUT nối GPIO2. GPIO2 cũng là chân strapping; nếu board boot lỗi, tháo OUT khỏi GPIO2 lúc reset rồi nối lại sau khi firmware đã chạy.

Để vào chế độ nạp UART khi board không tự reset: nối GPIO0 xuống GND, reset/cấp nguồn, nạp xong thì tháo GPIO0 khỏi GND và reset lại.

## 5. Build và nạp bằng ESP-IDF

Cài ESP-IDF cho Windows (ESP-IDF 5.x, target `esp32`) theo hướng dẫn của Espressif, sau đó mở **ESP-IDF PowerShell** từ Start Menu. Arduino IDE không build trực tiếp project TFLite Micro này.

Trong ESP-IDF PowerShell:

```powershell
cd "D:\duong-dan-den\PotatoClassification\esp32_iot_system\tinyml_idf"
idf.py set-target esp32
idf.py build
idf.py -p COM5 flash monitor
```

Thay đường dẫn project và `COM5` bằng vị trí/cổng thật. Có thể tìm cổng trong Device Manager → Ports (COM & LPT). Build lần đầu cần Internet để ESP-IDF tải các component khai báo trong `idf_component.yml`. Nếu đã build một lần, các lần sau chỉ cần `idf.py build` rồi flash.

## 6. Xác nhận hoạt động

Trong Serial Monitor (115200 baud), chờ log `Ready. Place an item...`. Đưa vật qua cảm biến IR; firmware phải in kết quả dạng `AI result=good` hoặc `AI result=not_good`. Nếu cấu hình backend đúng, log còn có trạng thái POST/dashboard.

- Không có log `Ready`: xem các lỗi khởi tạo model, camera hoặc PSRAM ở phía trên.
- Không nhận khi che IR: kiểm tra OUT, GND chung, mức active LOW và GPIO2.
- Có kết quả trên Serial nhưng dashboard không cập nhật: kiểm tra URL, IP máy chủ, firewall và đảm bảo máy cùng mạng.
- Không thấy `potato_tiny_model_data.h`: chạy lại `train_tinyml.py` hoặc lấy header đã commit từ Git.

## Lưu ý về kết quả

Độ chính xác trên tập test là kết quả đánh giá của tập ảnh hiện tại, không đảm bảo tương tự với camera, ánh sáng và khoảng cách sử dụng thực tế. Cần thử board với khoai thật và ghi nhận kết quả Serial. Các ảnh trong dataset có thể gồm nhiều góc của cùng một củ, nên độ chính xác test có thể lạc quan nếu ảnh tương tự xuất hiện ở nhiều split.
