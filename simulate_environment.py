import time
import json
import random
import urllib.request

URL = "http://localhost:5000/api/env"

print("=" * 60)
print(" CHƯƠNG TRÌNH GIẢ LẬP CẢM BIẾN MÔI TRƯỜNG DHT11 (DEMO IOT)")
print(f" Đang định kỳ gửi số liệu về: {URL}")
print(" Nhấn Ctrl + C để dừng.")
print("=" * 60)

# Ban đầu môi trường bình thường (26°C - 29°C, ẩm 65% - 75%)
temp = 27.5
hum = 68.0

step = 0

while True:
    step += 1
    
    # Biến thiên nhiệt độ, độ ẩm ngẫu nhiên
    temp += random.uniform(-0.3, 0.4)
    hum += random.uniform(-0.8, 0.8)

    # Thỉnh thoảng mô phỏng tình huống bất thường (Mục 9 trong docx: giả lập vượt ngưỡng)
    if step % 8 == 0:
        temp = random.uniform(32.5, 34.0) # Vượt ngưỡng 32°C
        print(f"\n[!] GIẢ LẬP CẢNH BÁO: Nhiệt độ kho vượt ngưỡng an toàn ({temp:.1f}°C)!")

    payload = json.dumps({
        "device": "esp32-cam-dht11",
        "temp": round(temp, 1),
        "hum": round(hum, 1)
    }).encode('utf-8')

    try:
        req = urllib.request.Request(URL, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as response:
            status = response.getcode()
            print(f"[{time.strftime('%H:%M:%S')}] Đã gửi: Nhiệt độ = {temp:.1f}°C | Độ ẩm = {hum:.1f}% -> Status: {status}")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Không thể kết nối tới backend_server.py (Hãy chạy 'python backend_server.py' trước!)")

    time.sleep(3) # Gửi mỗi 3 giây
