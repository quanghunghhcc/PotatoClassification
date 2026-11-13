import os
import tempfile
os.environ.setdefault('MPLCONFIGDIR', os.path.join(tempfile.gettempdir(), 'matplotlib'))
import time
import torch
import torch.nn as nn
from torchvision import datasets, models, transforms
from torch.utils.data import DataLoader
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# ==========================================
# CẤU HÌNH ĐÁNH GIÁ (EVALUATION CONFIG)
# ==========================================
DATA_DIR = './dataset'
BATCH_SIZE = 16
IMG_SIZE = 224
MODEL_PATH = 'best_potato_model.pth'
OUTPUT_DIR = './outputs'

def get_eval_dataloader(data_dir, img_size, batch_size):
    """
    Tải tập dữ liệu đánh giá:
    Ưu tiên tập 'test' nếu có, nếu chưa có tập test sẽ dùng tập 'val'.
    """
    eval_transform = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                             std=[0.229, 0.224, 0.225])
    ])

    test_path = os.path.join(data_dir, 'test')
    val_path = os.path.join(data_dir, 'val')

    if os.path.exists(test_path) and len(os.listdir(test_path)) > 0:
        target_path = test_path
        dataset_name = "TEST SET (Tập kiểm thử độc lập)"
    elif os.path.exists(val_path):
        target_path = val_path
        dataset_name = "VALIDATION SET (Tập kiểm định)"
    else:
        raise FileNotFoundError(f"[!] Không tìm thấy thư mục '{test_path}' hoặc '{val_path}'.")

    eval_dataset = datasets.ImageFolder(target_path, eval_transform)
    num_workers = 2 if os.name != 'nt' else 0
    dataloader = DataLoader(eval_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    return dataloader, eval_dataset.classes, len(eval_dataset), dataset_name


def load_trained_model(model_path, num_classes, device):
    """
    Khởi tạo khung mô hình MobileNetV2 và nạp trọng số đã lưu.
    """
    if not os.path.exists(model_path):
        # Thử tìm trong thư mục models/ nếu file không nằm ở root
        alt_path = os.path.join('models', os.path.basename(model_path))
        if os.path.exists(alt_path):
            model_path = alt_path
        else:
            raise FileNotFoundError(f"[!] Không tìm thấy file trọng số '{model_path}'. Vui lòng chạy train.py trước!")

    # Khởi tạo kiến trúc MobileNetV2
    model = models.mobilenet_v2(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.2),
        nn.Linear(in_features, num_classes)
    )

    # Nạp weights vào đúng device (GPU/CPU)
    state_dict = torch.load(model_path, map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model = model.to(device)
    model.eval()
    print(f"--> [OK] Đã nạp thành công trọng số từ: {model_path}")
    return model


def plot_and_save_confusion_matrix(y_true, y_pred, class_names, output_dir):
    """
    Vẽ ma trận nhầm lẫn (Confusion Matrix) đẹp mắt, hiển thị cả số lượng và phần trăm.
    """
    os.makedirs(output_dir, exist_ok=True)
    cm = confusion_matrix(y_true, y_pred)
    
    # Tính ma trận chuẩn hóa theo phần trăm
    cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

    fig, ax = plt.subplots(figsize=(7, 6))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=class_names)
    disp.plot(cmap=plt.cm.Blues, ax=ax, values_format='d', colorbar=True)

    # Thêm tỷ lệ phần trăm vào từng ô
    for i in range(len(class_names)):
        for j in range(len(class_names)):
            percentage = cm_normalized[i, j] * 100
            current_text = ax.texts[i * len(class_names) + j].get_text()
            ax.texts[i * len(class_names) + j].set_text(f"{current_text}\n({percentage:.1f}%)")

    plt.title('Ma Trận Nhầm Lẫn (Confusion Matrix) - MobileNetV2', fontsize=13, fontweight='bold', pad=15)
    plt.xlabel('Nhãn Dự Đoán (Predicted Label)', fontsize=11, fontweight='bold')
    plt.ylabel('Nhãn Thực Tế (True Label)', fontsize=11, fontweight='bold')
    plt.tight_layout()

    save_path = os.path.join(output_dir, 'confusion_matrix.png')
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"--> [OK] Đã lưu hình ảnh Ma trận nhầm lẫn tại: {save_path}")


def evaluate():
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("=" * 70)
    print(" ĐÁNH GIÁ MÔ HÌNH PHÂN LOẠI KHOAI TÂY (EVALUATION REPORT)")
    print(f" Thiết bị kiểm thử (Device): {device}")
    print("=" * 70)

    # 1. Nạp dữ liệu kiểm thử
    dataloader, class_names, total_samples, dataset_name = get_eval_dataloader(DATA_DIR, IMG_SIZE, BATCH_SIZE)
    print(f"--> Đang đánh giá trên: {dataset_name}")
    print(f"--> Tổng số lượng ảnh: {total_samples}")
    print(f"--> Các nhãn phân loại: {class_names}\n")

    # 2. Nạp mô hình đã train
    model = load_trained_model(MODEL_PATH, num_classes=len(class_names), device=device)

    all_preds = []
    all_labels = []
    total_time = 0.0

    print("--> Đang tiến hành dự đoán trên toàn bộ tập dữ liệu...")

    with torch.no_grad():
        for inputs, labels in dataloader:
            inputs = inputs.to(device)

            start_t = time.time()
            outputs = model(inputs)
            if device.type == 'cuda':
                torch.cuda.synchronize()
            total_time += (time.time() - start_t)

            _, preds = torch.max(outputs, 1)

            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.numpy())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)

    # 3. Tính toán các chỉ số
    avg_latency = (total_time / total_samples) * 1000  # mili-giây trên mỗi ảnh
    accuracy = (all_preds == all_labels).sum() / total_samples

    print("\n" + "=" * 70)
    print(" KẾT QUẢ ĐÁNH GIÁ CHI TIẾT (METRICS REPORT)")
    print("=" * 70)
    print(f"[*] Độ chính xác tổng thể (Accuracy): {accuracy:.4f} ({accuracy*100:.2f}%)")
    print(f"[*] Độ trễ suy luận trung bình (Edge Latency): {avg_latency:.2f} ms / ảnh")
    print("-" * 70)
    print("BÁO CÁO PHÂN LOẠI (CLASSIFICATION REPORT):")
    print("-" * 70)
    report = classification_report(all_labels, all_preds, target_names=class_names, digits=4)
    print(report)

    # 4. Lưu và vẽ Confusion Matrix
    print("-" * 70)
    print("MA TRẬN NHẦM LẪN (CONFUSION MATRIX):")
    cm = confusion_matrix(all_labels, all_preds)
    print(cm)
    print("-" * 70)
    plot_and_save_confusion_matrix(all_labels, all_preds, class_names, OUTPUT_DIR)

    # 5. Lưu báo cáo dạng text để tiện trích xuất vào luận văn đồ án
    report_file_path = os.path.join(OUTPUT_DIR, 'evaluation_summary.txt')
    with open(report_file_path, 'w', encoding='utf-8') as f:
        f.write("=== KẾT QUẢ THỰC NGHIỆM ĐỒ ÁN IOT & AI ===\n")
        f.write(f"Tập dữ liệu: {dataset_name}\n")
        f.write(f"Tổng số ảnh: {total_samples}\n")
        f.write(f"Mô hình: MobileNetV2 (Transfer Learning)\n")
        f.write(f"Accuracy: {accuracy*100:.2f}%\n")
        f.write(f"Latency: {avg_latency:.2f} ms/ảnh\n\n")
        f.write("Chi tiết Precision - Recall - F1-score:\n")
        f.write(report)
        f.write("\nMa trận nhầm lẫn:\n")
        f.write(np.array2string(cm))
    print(f"--> [OK] Đã lưu tóm tắt số liệu ra file: {report_file_path}")
    print("=" * 70)


if __name__ == '__main__':
    evaluate()
