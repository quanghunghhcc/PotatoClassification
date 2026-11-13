import os
import json
import sqlite3
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse

# ==========================================
# CẤU HÌNH BACKEND SERVER & IOT (THEO FILE DOCX)
# ==========================================
PORT = 5000
DB_FILE = 'iot_agriculture.db'

# Cấu hình Telegram Bot (Điền token và chat_id của bạn nếu muốn nhận tin nhắn cảnh báo)
ENABLE_TELEGRAM = False
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

# Ngưỡng cảnh báo môi trường (Mục 6.4 trong file docx)
TEMP_THRESHOLD = 32.0  # > 32°C cảnh báo nhiệt độ cao
HUM_MIN_THRESHOLD = 50.0  # < 50% cảnh báo độ ẩm thấp
HUM_MAX_THRESHOLD = 85.0  # > 85% cảnh báo độ ẩm quá cao

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Bảng kết quả kiểm định chất lượng (Mục 8 trong docx)
    c.execute('''CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device TEXT,
                    quality TEXT,
                    confidence REAL,
                    ts TEXT
                )''')
    # Bảng dữ liệu môi trường DHT11
    c.execute('''CREATE TABLE IF NOT EXISTS env_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device TEXT,
                    temp REAL,
                    hum REAL,
                    ts TEXT
                )''')
    # Bảng cảnh báo bất thường
    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device TEXT,
                    type TEXT,
                    value REAL,
                    threshold REAL,
                    ts TEXT
                )''')
    conn.commit()
    conn.close()

def send_telegram_alert(message):
    if not ENABLE_TELEGRAM or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': message}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        print(f"[!] Lỗi gửi Telegram: {e}")

class IoTRequestHandler(BaseHTTPRequestHandler):
    def _send_response(self, data, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        if isinstance(data, str):
            self.wfile.write(data.encode('utf-8'))
        else:
            self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        self._send_response({}, status=200)

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == '/' or path == '/dashboard':
            # Phục vụ giao diện Web Dashboard
            html_content = self.get_dashboard_html()
            self._send_response(html_content, status=200, content_type='text/html; charset=utf-8')

        elif path == '/api/stats':
            # Lấy thống kê tổng quan
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM results WHERE LOWER(quality) IN ('good', 'healthy')")
            healthy_count = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM results WHERE LOWER(quality) IN ('not_good', 'rotten', 'bad')")
            rotten_count = c.fetchone()[0]

            # Lấy số đo nhiệt độ/độ ẩm mới nhất
            c.execute("SELECT temp, hum, ts FROM env_readings ORDER BY id DESC LIMIT 1")
            env_row = c.fetchone()
            current_temp = env_row[0] if env_row else 26.5
            current_hum = env_row[1] if env_row else 65.0
            last_env_ts = env_row[2] if env_row else "Chưa có dữ liệu"

            # Lấy 10 cảnh báo mới nhất
            c.execute("SELECT type, value, threshold, ts FROM alerts ORDER BY id DESC LIMIT 5")
            alerts = [{"type": r[0], "value": r[1], "threshold": r[2], "ts": r[3]} for r in c.fetchall()]

            # Lấy 10 kết quả kiểm tra gần nhất
            c.execute("SELECT quality, confidence, ts FROM results ORDER BY id DESC LIMIT 10")
            recent_results = [{"quality": r[0], "confidence": round(r[1]*100, 1), "ts": r[2]} for r in c.fetchall()]

            # Lấy dữ liệu 20 điểm đo môi trường gần nhất để vẽ biểu đồ
            c.execute("SELECT temp, hum, strftime('%H:%M:%S', ts) FROM env_readings ORDER BY id DESC LIMIT 20")
            history_rows = c.fetchall()
            history_rows.reverse()
            env_history = {
                "labels": [r[2] for r in history_rows],
                "temp": [r[0] for r in history_rows],
                "hum": [r[1] for r in history_rows]
            }

            conn.close()

            total = healthy_count + rotten_count
            pass_rate = round((healthy_count / total * 100), 1) if total > 0 else 0.0

            stats = {
                "total": total,
                "healthy": healthy_count,
                "rotten": rotten_count,
                "pass_rate": pass_rate,
                "current_temp": current_temp,
                "current_hum": current_hum,
                "last_env_ts": last_env_ts,
                "alerts": alerts,
                "recent_results": recent_results,
                "env_history": env_history
            }
            self._send_response(stats)

        else:
            self._send_response({"error": "Endpoint not found"}, status=404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            payload = json.loads(post_data.decode('utf-8'))
        except Exception:
            payload = {}

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        device_id = payload.get("device", "esp32-cam-01")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        if self.path == '/api/result':
            # Nhận kết quả kiểm định: {"device": "...", "quality": "good"/"not_good", "confidence": 0.95}
            quality = payload.get("quality", "unknown")
            confidence = float(payload.get("confidence", 0.0))
            ts = payload.get("ts", now_str)

            c.execute("INSERT INTO results (device, quality, confidence, ts) VALUES (?, ?, ?, ?)",
                      (device_id, quality, confidence, ts))
            conn.commit()

            print(f"[KIỂM ĐỊNH] Thiết bị: {device_id} | Phân loại: {quality.upper()} ({confidence*100:.1f}%) | Thời gian: {ts}")

            if "not_good" in quality.lower() or "rotten" in quality.lower():
                send_telegram_alert(f"⚠️ [CẢNH BÁO NÔNG SẢN HỎNG]\nThiết bị: {device_id}\nPhát hiện: {quality}\nĐộ tin cậy: {confidence*100:.1f}%\nThời gian: {ts}")

            self._send_response({"status": "success", "message": "Result recorded"})

        elif self.path == '/api/env':
            # Nhận số liệu môi trường DHT11: {"device": "...", "temp": 28.5, "hum": 70.2}
            temp = float(payload.get("temp", 0.0))
            hum = float(payload.get("hum", 0.0))
            ts = payload.get("ts", now_str)

            c.execute("INSERT INTO env_readings (device, temp, hum, ts) VALUES (?, ?, ?, ?)",
                      (device_id, temp, hum, ts))

            # Kiểm tra ngưỡng cảnh báo nhiệt độ / độ ẩm
            alert_msg = None
            if temp > TEMP_THRESHOLD:
                c.execute("INSERT INTO alerts (device, type, value, threshold, ts) VALUES (?, ?, ?, ?, ?)",
                          (device_id, "Nhiệt độ cao", temp, TEMP_THRESHOLD, ts))
                alert_msg = f"🔥 [CẢNH BÁO NHIỆT ĐỘ]\nNhiệt độ đo được: {temp}°C (Ngưỡng: >{TEMP_THRESHOLD}°C)\nThiết bị: {device_id}"
            elif hum < HUM_MIN_THRESHOLD or hum > HUM_MAX_THRESHOLD:
                threshold_val = HUM_MIN_THRESHOLD if hum < HUM_MIN_THRESHOLD else HUM_MAX_THRESHOLD
                c.execute("INSERT INTO alerts (device, type, value, threshold, ts) VALUES (?, ?, ?, ?, ?)",
                          (device_id, "Độ ẩm bất thường", hum, threshold_val, ts))
                alert_msg = f"💧 [CẢNH BÁO ĐỘ ẨM]\nĐộ ẩm đo được: {hum}% (Giới hạn chuẩn: 50% - 85%)\nThiết bị: {device_id}"

            conn.commit()

            if alert_msg:
                print(alert_msg)
                send_telegram_alert(alert_msg)

            self._send_response({"status": "success", "message": "Environment logged"})

        else:
            self._send_response({"error": "Unknown POST route"}, status=404)

        conn.close()

    def get_dashboard_html(self):
        return """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Hệ Thống Giám Sát Chất Lượng Nông Sản - Edge AI & IoT</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: #f0f2f5; color: #333; padding: 20px; }
        .header { background: linear-gradient(135deg, #1e3c72, #2a5298); color: white; padding: 20px 30px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .header h1 { font-size: 24px; font-weight: 600; margin-bottom: 5px; }
        .header p { font-size: 14px; opacity: 0.9; }
        .grid-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 25px; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); text-align: center; border-left: 5px solid #2a5298; }
        .card.green { border-left-color: #2ecc71; }
        .card.red { border-left-color: #e74c3c; }
        .card.orange { border-left-color: #e67e22; }
        .card.blue { border-left-color: #3498db; }
        .card .title { font-size: 13px; font-weight: 600; color: #7f8c8d; text-transform: uppercase; margin-bottom: 10px; }
        .card .value { font-size: 32px; font-weight: bold; color: #2c3e50; }
        .card .unit { font-size: 14px; color: #95a5a6; }
        .grid-charts { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 25px; }
        @media(max-width: 900px) { .grid-charts { grid-template-columns: 1fr; } }
        .chart-container, .table-container { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .section-title { font-size: 16px; font-weight: bold; margin-bottom: 15px; color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid #ecf0f1; }
        th { background: #f8f9fa; color: #7f8c8d; }
        .badge { padding: 4px 8px; border-radius: 20px; font-size: 11px; font-weight: bold; text-transform: uppercase; }
        .badge.good { background: #d4edda; color: #155724; }
        .badge.bad { background: #f8d7da; color: #721c24; }
        .badge.alert { background: #fff3cd; color: #856404; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🌾 HỆ THỐNG PHÂN LOẠI & GIÁM SÁT CHẤT LƯỢNG NÔNG SẢN (EDGE AI & IOT)</h1>
        <p>Báo cáo đồ án tốt nghiệp - Giám sát chất lượng nông sản thời gian thực và quản lý môi trường bảo quản (DHT11 + MobileNetV2 + MQTT)</p>
    </div>

    <div class="grid-cards">
        <div class="card blue">
            <div class="title">Tổng số kiểm định</div>
            <div class="value" id="total_count">0</div>
            <div class="unit">Sản phẩm</div>
        </div>
        <div class="card green">
            <div class="title">Đạt chuẩn (Healthy/Good)</div>
            <div class="value" id="healthy_count">0</div>
            <div class="unit">Sản phẩm</div>
        </div>
        <div class="card red">
            <div class="title">Bị hỏng (Rotten/Bad)</div>
            <div class="value" id="rotten_count">0</div>
            <div class="unit">Sản phẩm</div>
        </div>
        <div class="card green">
            <div class="title">Tỷ lệ đạt chuẩn</div>
            <div class="value" id="pass_rate">0%</div>
            <div class="unit">Pass Rate</div>
        </div>
        <div class="card orange">
            <div class="title">Nhiệt độ kho (DHT11)</div>
            <div class="value" id="curr_temp">--</div>
            <div class="unit">°C (Chuẩn: &le;32°C)</div>
        </div>
        <div class="card blue">
            <div class="title">Độ ẩm kho (DHT11)</div>
            <div class="value" id="curr_hum">--</div>
            <div class="unit">% (Chuẩn: 50% - 85%)</div>
        </div>
    </div>

    <div class="grid-charts">
        <div class="chart-container">
            <div class="section-title">📈 BIỂU ĐỒ GIÁM SÁT MÔI TRƯỜNG THỜI GIAN THỰC (DHT11)</div>
            <canvas id="envChart" height="120"></canvas>
        </div>
        <div class="table-container">
            <div class="section-title">🚨 NHẬT KÝ CẢNH BÁO BẤT THƯỜNG</div>
            <table id="alert_table">
                <thead>
                    <tr><th>Loại cảnh báo</th><th>Giá trị</th><th>Thời gian</th></tr>
                </thead>
                <tbody>
                    <tr><td colspan="3" style="text-align:center; color:#95a5a6;">Hệ thống ổn định, không có cảnh báo.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <div class="table-container">
        <div class="section-title">🔍 LỊCH SỬ KIỂM ĐỊNH NÔNG SẢN GẦN NHẤT</div>
        <table id="results_table">
            <thead>
                <tr><th>Thời gian</th><th>Kết quả phân loại</th><th>Độ tin cậy</th><th>Trạng thái</th></tr>
            </thead>
            <tbody>
                <tr><td colspan="4" style="text-align:center; color:#95a5a6;">Chưa có dữ liệu kiểm định. Đặt quả lên khay để bắt đầu.</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        let chart = null;

        function initChart() {
            const ctx = document.getElementById('envChart').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Nhiệt độ (°C)', data: [], borderColor: '#e67e22', backgroundColor: 'rgba(230,126,34,0.1)', tension: 0.3, fill: true },
                        { label: 'Độ ẩm (%)', data: [], borderColor: '#3498db', backgroundColor: 'rgba(52,152,219,0.1)', tension: 0.3, fill: true }
                    ]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: { beginAtZero: false, suggestedMin: 20, suggestedMax: 90 }
                    }
                }
            });
        }

        async function updateDashboard() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                document.getElementById('total_count').innerText = data.total;
                document.getElementById('healthy_count').innerText = data.healthy;
                document.getElementById('rotten_count').innerText = data.rotten;
                document.getElementById('pass_rate').innerText = data.pass_rate + '%';
                document.getElementById('curr_temp').innerText = data.current_temp.toFixed(1);
                document.getElementById('curr_hum').innerText = data.current_hum.toFixed(1);

                // Cập nhật biểu đồ
                if (chart && data.env_history) {
                    chart.data.labels = data.env_history.labels;
                    chart.data.datasets[0].data = data.env_history.temp;
                    chart.data.datasets[1].data = data.env_history.hum;
                    chart.update('none');
                }

                // Cập nhật cảnh báo
                const alertTbody = document.querySelector('#alert_table tbody');
                if (data.alerts && data.alerts.length > 0) {
                    alertTbody.innerHTML = data.alerts.map(a => `
                        <tr>
                            <td><span class="badge alert">${a.type}</span></td>
                            <td><b>${a.value}</b> (Ngưỡng: ${a.threshold})</td>
                            <td>${a.ts.split(' ')[1] || a.ts}</td>
                        </tr>
                    `).join('');
                } else {
                    alertTbody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:#2ecc71;">✅ Môi trường đạt chuẩn an toàn</td></tr>`;
                }

                // Cập nhật lịch sử kiểm định
                const resultsTbody = document.querySelector('#results_table tbody');
                if (data.recent_results && data.recent_results.length > 0) {
                    resultsTbody.innerHTML = data.recent_results.map(r => {
                        const normalizedQuality = r.quality.toLowerCase();
                        const isGood = ['good', 'healthy'].includes(normalizedQuality);
                        return `
                            <tr>
                                <td>${r.ts}</td>
                                <td><b>${r.quality.toUpperCase()}</b></td>
                                <td>${r.confidence}%</td>
                                <td><span class="badge ${isGood ? 'good' : 'bad'}">${isGood ? 'ĐẠT CHUẨN' : 'LOẠI BỎ'}</span></td>
                            </tr>
                        `;
                    }).join('');
                }
            } catch (err) {
                console.error("Lỗi cập nhật dashboard:", err);
            }
        }

        window.onload = () => {
            initChart();
            updateDashboard();
            setInterval(updateDashboard, 2000); // Tự động làm mới mỗi 2 giây
        };
    </script>
</body>
</html>"""

def run_server():
    init_db()
    server_address = ('0.0.0.0', PORT)
    httpd = HTTPServer(server_address, IoTRequestHandler)
    print("=" * 65)
    print(f" IOT & EDGE AI BACKEND SERVER ĐANG CHẠY TRÊN CỔNG {PORT}")
    print(f" Mở trình duyệt Web tại: http://localhost:{PORT}")
    print(" Các API sẵn sàng:")
    print(f"  - GET  /dashboard       : Giao diện giám sát Web thời gian thực")
    print(f"  - POST /api/result      : Nhận kết quả AI từ Camera/ESP32-CAM")
    print(f"  - POST /api/env         : Nhận số liệu nhiệt độ/độ ẩm từ DHT11")
    print(f"  - GET  /api/stats       : Trả về số liệu thống kê JSON")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n--> Đang dừng Backend Server.")
        httpd.server_close()

if __name__ == '__main__':
    run_server()
