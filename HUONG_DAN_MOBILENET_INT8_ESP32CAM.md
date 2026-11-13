# Thử model MobileNetV2 INT8 trên ESP32-CAM

Firmware thử nghiệm riêng nằm ở `esp32_iot_system/mobilenet_idf`; project TinyML 96×96 cũ vẫn nằm ở `tinyml_idf`.

Model được đánh giá trên máy là full-integer uint8, input `[1,224,224,3]`, output `[1,2]`, kích thước xấp xỉ 2.6 MiB. Firmware mới dùng trực tiếp binary TFLite nhúng trong app image, đăng ký các builtin ops `ADD`, `CONV_2D`, `DEPTHWISE_CONV_2D`, `FULLY_CONNECTED`, `MEAN`, `PAD`, `QUANTIZE`, và cấp tensor arena 2.5 MiB trong PSRAM. `DELEGATE` trong danh sách từ TensorFlow Lite Interpreter là XNNPACK delegate trên máy tính, không phải operator của model cần đăng ký vào TFLite Micro.

## Chép model sang project firmware

Từ Ubuntu/WSL:

```bash
cp ~/PotatoTinyML/models/best_potato_model_from_pth_int8.tflite \
  "/mnt/d/ki 1 nam 4/PotatoClassification/esp32_iot_system/mobilenet_idf/main/"
```

Trong `esp32_iot_system/mobilenet_idf/main/user_config.h`, điền Wi-Fi và URL backend nếu muốn gửi kết quả lên dashboard. Model dùng MobileNet preprocessing: resize 224×224, chuẩn hóa ImageNet RGB, rồi lượng tử hóa theo quantization parameters từ tensor đầu vào. Output là hai logits lượng tử hóa; firmware chọn argmax và tính softmax để báo confidence.

## Build và nạp thử

Trong ESP-IDF PowerShell:

```powershell
cd "D:\ki 1 nam 4\PotatoClassification\esp32_iot_system\mobilenet_idf"
idf.py set-target esp32
idf.py build
idf.py -p COMx flash monitor
```

Thay `COMx` bằng cổng board. Firmware yêu cầu AI-Thinker ESP32-CAM có PSRAM và IR active-LOW tại GPIO2. Khi nạp, GPIO0 có thể cần kéo xuống GND để vào bootloader.

## Giới hạn cần kiểm tra trên board

Đây là bản thử. Kết quả build sẽ cho biết model 2.6 MiB cộng firmware có vừa phân vùng app 4 MiB không. Khi chạy, `AllocateTensors` có thể báo thiếu arena; arena hiện đặt 2.5 MiB PSRAM và camera khởi tạo sau đó để ưu tiên cấp vùng nhớ liên tục cho model. Nếu app không vừa flash hoặc arena không đủ, dùng model TinyML 96×96 là lựa chọn phù hợp hơn ESP32-CAM cổ điển.

Thời gian inference trên máy tính không đại diện cho thời gian trên ESP32. Cần đo qua Serial sau khi nạp thực tế.
