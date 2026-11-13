import os
import time
import json
import urllib.request
import cv2
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import numpy as np

# Thử import serial nếu có kết nối Arduino / ESP32 qua cổng USB
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# ==========================================
# CẤU HÌNH THỜI GIAN THỰC (REALTIME EDGE CONFIG)
# ==========================================
MODEL_PATH = 'best_potato_model.pth'
IMG_SIZE = 224
CLASS_NAMES = ['good', 'not_good']
CONFIDENCE_THRESHOLD = 0.75  # Ngưỡng tin cậy tối thiểu để kích hoạt cơ cấu gạt (75%)

# Cấu hình nguồn Video:
# - Số 0: Webcam máy tính
# - Hoặc chuỗi URL luồng video từ ESP32-CAM: "http://192.168.1.100:81/stream"
VIDEO_SOURCE = 0 

# Cấu hình cổng Serial kết nối vi điều khiển (Arduino/ESP32):
ENABLE_IOT_SERIAL = False    # Bật True khi nối ESP32 hoặc Arduino với máy tính
SERIAL_PORT = 'COM3'         # Đổi theo cổng COM trên máy của bạn (ví dụ: COM3, COM4)
SERIAL_TARGET = 'esp32'      # 'esp32' để ghi dashboard qua firmware, hoặc 'arduino' để điều khiển sorter
BAUD_RATE = 115200 if SERIAL_TARGET == 'esp32' else 9600

def init_serial():
    if not ENABLE_IOT_SERIAL or not SERIAL_AVAILABLE:
        return None
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        time.sleep(2) # Chờ Arduino khởi động lại sau kết nối Serial
        print(f"--> [OK] Đã kết nối với vi điều khiển IoT trên cổng {SERIAL_PORT}")
        return ser
    except Exception as e:
        print(f"[!] Không thể mở cổng Serial {SERIAL_PORT}: {e}")
        return None

def send_actuator_signal(ser, label, confidence):
    """
    Gửi tín hiệu điều khiển cơ cấu chấp hành:
    - '1': Khoai tây hỏng (Kích hoạt Servo gạt bỏ củ khoai lỗi)
    - '0': Khoai tây tốt (Cho phép đi qua)
    """
    if ser is not None and ser.is_open:
        if SERIAL_TARGET == 'esp32':
            # ESP32 nhận định dạng quality,confidence; ví dụ: not_good,0.91
            command = f"{label},{confidence:.4f}\n".encode('ascii')
        else:
            # Arduino sorter.ino nhận '1' để gạt và '0' để cho qua.
            command = b'1\n' if label == 'not_good' else b'0\n'
        try:
            ser.write(command)
            return True
        except serial.SerialException as exc:
            print(f"[!] Không gửi được kết quả tới ESP32: {exc}")
    return False

def sync_to_backend(label, confidence):
    """Đồng bộ kết quả kiểm định lên Backend Server và Web Dashboard (theo file docx)"""
    try:
        url = "http://localhost:5000/api/result"
        payload = json.dumps({
            "device": "edge-ai-camera-01",
            "quality": label,
            "confidence": round(confidence, 4)
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=1.0) as res:
            print(f"--> [OK Web] Đã ghi nhận củ khoai: {label.upper()} ({confidence*100:.1f}%) lên Dashboard!")
    except Exception:
        print(f"--> [!] Chưa kết nối được Web: Bạn cần chạy lệnh 'python backend_server.py' ở 1 tab Terminal khác!")

def load_model(model_path, device):
    if not os.path.exists(model_path):
        alt = os.path.join('models', os.path.basename(model_path))
        if os.path.exists(alt):
            model_path = alt
        else:
            raise FileNotFoundError(f"[!] Không tìm thấy file trọng số '{model_path}'. Hãy chạy train.py trước!")

    model = models.mobilenet_v2(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.2),
        nn.Linear(in_features, len(CLASS_NAMES))
    )
    state_dict = torch.load(model_path, map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model = model.to(device)
    model.eval()
    print(f"--> [OK] Nạp thành công mô hình từ: {model_path}")
    return model

def main():
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("=" * 65)
    print(" HỆ THỐNG PHÂN LOẠI KHOAI TÂY THỜI GIAN THỰC (REAL-TIME VISION)")
    print(f" Thiết bị chạy AI: {device}")
    print(" Nhấn phím 'Q' trên cửa sổ Camera để thoát chương trình.")
    print("=" * 65)

    try:
        model = load_model(MODEL_PATH, device)
    except FileNotFoundError as e:
        print(e)
        return

    preprocess = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                             std=[0.229, 0.224, 0.225])
    ])

    ser = init_serial()

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        print(f"[!] Lỗi: Không thể mở nguồn video ({VIDEO_SOURCE}).")
        if ser is not None and ser.is_open:
            ser.close()
        return

    prev_time = time.time()
    last_actuator_time = 0
    COOLDOWN_TIME = 1.0 # Khoảng cách tối thiểu giữa 2 lần gạt cơ cấu (1 giây)
    classification_armed = True
    below_threshold_frames = 0
    REARM_FRAMES = 8

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[!] Không nhận được khung hình từ camera.")
            break

        h, w, _ = frame.shape

        # Xác định vùng kiểm tra trung tâm (Region of Interest - ROI trên băng chuyền)
        box_size = int(min(h, w) * 0.6)
        x1 = (w - box_size) // 2
        y1 = (h - box_size) // 2
        x2 = x1 + box_size
        y2 = y1 + box_size

        roi = frame[y1:y2, x1:x2]
        
        # Chuyển đổi màu BGR (OpenCV) sang RGB (PyTorch)
        rgb_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_roi)
        input_tensor = preprocess(pil_img).unsqueeze(0).to(device)

        # Suy luận dự đoán
        with torch.no_grad():
            output = model(input_tensor)
            probs = torch.softmax(output, dim=1)[0]
            confidence, pred_idx = torch.max(probs, 0)

        label = CLASS_NAMES[pred_idx.item()]
        conf_val = confidence.item()

        # Tính FPS
        curr_time = time.time()
        fps = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
        prev_time = curr_time

        # Quy định màu sắc hiển thị
        if label == 'good':
            color = (0, 255, 0) # Xanh lá: Khoai tây đạt chuẩn
            status_text = f"GOOD (Dat chuan): {conf_val*100:.1f}%"
        else:
            color = (0, 0, 255) # Đỏ: Khoai tây lỗi/hỏng
            status_text = f"NOT GOOD (Hong): {conf_val*100:.1f}%"

        # Kích hoạt gửi lệnh IoT và đồng bộ lên Backend Dashboard khi đạt ngưỡng tin cậy
        if conf_val < CONFIDENCE_THRESHOLD:
            below_threshold_frames += 1
            if below_threshold_frames >= REARM_FRAMES:
                classification_armed = True
        else:
            below_threshold_frames = 0

        if conf_val >= CONFIDENCE_THRESHOLD and classification_armed:
            if curr_time - last_actuator_time > COOLDOWN_TIME:
                sent_to_device = send_actuator_signal(ser, label, conf_val)
                # ESP32 tự ghi kết quả lên backend khi nhận Serial; tránh ghi trùng.
                if not sent_to_device or SERIAL_TARGET != 'esp32':
                    sync_to_backend(label, conf_val)
                last_actuator_time = curr_time
                classification_armed = False
                if label == 'not_good':
                    cv2.putText(frame, ">>> DANG GAT LOAI BO! <<<", (x1, y2 + 35), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # Vẽ khung ROI và hiển thị thông tin
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        cv2.putText(frame, status_text, (x1, y1 - 12), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
        cv2.putText(frame, f"FPS: {fps:.1f}", (20, 40), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
        cv2.putText(frame, "Vung phan loai tren bang chuyen", (x1, y1 - 35), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        cv2.imshow("Potato Quality Classification System - Edge AI", frame)

        # Nhấn 'Q' để thoát
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    if ser is not None and ser.is_open:
        ser.close()
    cv2.destroyAllWindows()
    print("--> Đã đóng hệ thống phân loại thời gian thực.")

if __name__ == '__main__':
    main()
