import os
import tempfile
os.environ.setdefault('MPLCONFIGDIR', os.path.join(tempfile.gettempdir(), 'matplotlib'))
import time
import copy
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, models, transforms
from torch.utils.data import DataLoader
import matplotlib
matplotlib.use('Agg') # Tránh lỗi GUI khi chạy không có màn hình hiển thị
import matplotlib.pyplot as plt

# ==========================================
# CẤU HÌNH SIÊU THAM SỐ (HYPERPARAMETERS)
# ==========================================
DATA_DIR = './dataset'
BATCH_SIZE = 16
NUM_EPOCHS = 15
IMG_SIZE = 224        # Chuẩn mặc định cho MobileNetV2 (có thể hạ xuống 128 cho thiết bị IoT rất yếu)
LEARNING_RATE = 0.0005
MODEL_SAVE_PATH = 'best_potato_model.pth'
BACKUP_SAVE_PATH = os.path.join('models', 'best_potato_model.pth')
OUTPUT_DIR = './outputs'

def get_data_loaders(data_dir, batch_size, img_size):
    """
    Tiền xử lý và tăng cường dữ liệu (Data Augmentation) cho bài toán Edge AI.
    - Train: Tăng cường xoay, lật, chỉnh màu nhẹ để mô hình thích ứng với ánh sáng IoT.
    - Val: Chỉ chuẩn hóa và resize kích thước chuẩn.
    """
    data_transforms = {
        'train': transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomVerticalFlip(p=0.2),
            transforms.RandomRotation(degrees=20),
            transforms.ColorJitter(brightness=0.1, contrast=0.1),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                                 std=[0.229, 0.224, 0.225])
        ]),
        'val': transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                                 std=[0.229, 0.224, 0.225])
        ]),
    }

    train_path = os.path.join(data_dir, 'train')
    val_path = os.path.join(data_dir, 'val')

    if not os.path.exists(train_path) or not os.path.exists(val_path):
        raise FileNotFoundError(
            f"\n[!] Không tìm thấy thư mục '{train_path}' hoặc '{val_path}'.\n"
            f"--> Hãy đảm bảo bạn đã chạy file 'split_data.py' để phân chia dữ liệu train/val/test trước!"
        )

    image_datasets = {
        'train': datasets.ImageFolder(train_path, data_transforms['train']),
        'val': datasets.ImageFolder(val_path, data_transforms['val'])
    }

    # Trên Windows, num_workers=0 hoặc 2 được bọc trong main() để tránh lỗi multiprocessing
    num_workers = 2 if os.name != 'nt' else 0

    dataloaders = {
        'train': DataLoader(image_datasets['train'], batch_size=batch_size, shuffle=True, num_workers=num_workers),
        'val': DataLoader(image_datasets['val'], batch_size=batch_size, shuffle=False, num_workers=num_workers)
    }

    dataset_sizes = {x: len(image_datasets[x]) for x in ['train', 'val']}
    class_names = image_datasets['train'].classes

    return dataloaders, dataset_sizes, class_names


def build_mobilenet_v2(num_classes):
    """
    Khởi tạo MobileNetV2 Pretrained và thay thế lớp phân loại cuối cùng (Classifier Head).
    MobileNetV2 là kiến trúc tối ưu nhất cho thiết bị biên (Edge AI) nhờ Depthwise Separable Convolutions.
    """
    weights = models.MobileNet_V2_Weights.DEFAULT
    model = models.mobilenet_v2(weights=weights)

    # Thay đổi lớp Dropout và Linear cuối cùng cho phù hợp với 2 lớp (good, not_good)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.2),
        nn.Linear(in_features, num_classes)
    )
    return model


def plot_training_history(history, output_dir):
    """
    Vẽ và lưu đồ thị huấn luyện Loss và Accuracy để làm báo cáo đồ án.
    """
    os.makedirs(output_dir, exist_ok=True)
    epochs = range(1, len(history['train_loss']) + 1)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Đồ thị Loss
    axes[0].plot(epochs, history['train_loss'], 'b-o', label='Training Loss')
    axes[0].plot(epochs, history['val_loss'], 'r-s', label='Validation Loss')
    axes[0].set_title('Mất mát qua từng Epoch (Loss Curve)', fontsize=13, fontweight='bold')
    axes[0].set_xlabel('Epochs')
    axes[0].set_ylabel('Loss')
    axes[0].legend()
    axes[0].grid(True)

    # Đồ thị Accuracy
    axes[1].plot(epochs, history['train_acc'], 'b-o', label='Training Accuracy')
    axes[1].plot(epochs, history['val_acc'], 'r-s', label='Validation Accuracy')
    axes[1].set_title('Độ chính xác qua từng Epoch (Accuracy Curve)', fontsize=13, fontweight='bold')
    axes[1].set_xlabel('Epochs')
    axes[1].set_ylabel('Accuracy')
    axes[1].legend()
    axes[1].grid(True)

    save_fig_path = os.path.join(output_dir, 'training_history.png')
    plt.tight_layout()
    plt.savefig(save_fig_path, dpi=300)
    plt.close()
    print(f"--> [OK] Biểu đồ huấn luyện đã được lưu tại: {save_fig_path}")


def train_model():
    # 1. Tự động nhận diện phần cứng (GPU CUDA hoặc CPU)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("=" * 65)
    print(" HỆ THỐNG PHÂN LOẠI KHOAI TÂY CHẤT LƯỢNG CAO (EDGE AI - PYTORCH)")
    print(f" Thiết bị huấn luyện (Device): {device}")
    if torch.cuda.is_available():
        print(f" Tên GPU: {torch.cuda.get_device_name(0)}")
    print("=" * 65)

    # 2. Tải DataLoaders
    dataloaders, dataset_sizes, class_names = get_data_loaders(DATA_DIR, BATCH_SIZE, IMG_SIZE)
    print(f"--> Các lớp đối tượng (Classes): {class_names}")
    print(f"--> Số lượng ảnh: Tập Train = {dataset_sizes['train']} | Tập Val = {dataset_sizes['val']}\n")

    # 3. Khởi tạo mô hình
    model = build_mobilenet_v2(num_classes=len(class_names))
    model = model.to(device)

    # 4. Hàm mất mát và Tối ưu hóa (Loss & Optimizer)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)
    # Giảm Learning Rate khi Val Loss đi ngang (Plateau)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=2)

    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    history = {
        'train_loss': [], 'train_acc': [],
        'val_loss': [], 'val_acc': []
    }

    start_time = time.time()

    # 5. Vòng lặp huấn luyện (Training Loop)
    for epoch in range(NUM_EPOCHS):
        print(f"Epoch {epoch + 1:02d}/{NUM_EPOCHS:02d}")
        print("-" * 35)

        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()
            else:
                model.eval()

            running_loss = 0.0
            running_corrects = 0

            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                optimizer.zero_grad()

                # Forward pass (tính gradient chỉ khi ở phase train)
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = (running_corrects.double() / dataset_sizes[phase]).item()

            history[f'{phase}_loss'].append(epoch_loss)
            history[f'{phase}_acc'].append(epoch_acc)

            print(f"[{phase.upper():^5}] Loss: {epoch_loss:.4f} | Acc: {epoch_acc:.4f}")

            # Lưu lại model tốt nhất dựa trên Validation Accuracy
            if phase == 'val':
                scheduler.step(epoch_loss)
                if epoch_acc > best_acc:
                    best_acc = epoch_acc
                    best_model_wts = copy.deepcopy(model.state_dict())
                    print(f"  --> [*] Đạt kỷ lục Val Acc mới: {best_acc:.4f}! Đang lưu trọng số tốt nhất...")

        print()

    time_elapsed = time.time() - start_time
    print("=" * 65)
    print(f"Huấn luyện hoàn tất trong: {time_elapsed // 60:.0f}m {time_elapsed % 60:.0f}s")
    print(f"Độ chính xác trên tập Validation cao nhất (Best Val Acc): {best_acc:.4f} ({best_acc*100:.2f}%)")
    print("=" * 65)

    # 6. Lưu file trọng số tốt nhất
    os.makedirs('models', exist_ok=True)
    torch.save(best_model_wts, MODEL_SAVE_PATH)
    torch.save(best_model_wts, BACKUP_SAVE_PATH)
    print(f"--> [OK] Đã lưu trọng số vào: '{MODEL_SAVE_PATH}' và '{BACKUP_SAVE_PATH}'")

    # 7. Vẽ biểu đồ học tập
    plot_training_history(history, OUTPUT_DIR)


if __name__ == '__main__':
    train_model()
