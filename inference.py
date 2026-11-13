import os
import sys
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

# ==========================================
# CẤU HÌNH DỰ ĐOÁN ĐƠN LẺ (SINGLE INFERENCE)
# ==========================================
IMG_SIZE = 224
MODEL_PATH = 'best_potato_model.pth'
CLASS_NAMES = ['good', 'not_good']

def load_inference_model(model_path, device):
    if not os.path.exists(model_path):
        alt = os.path.join('models', os.path.basename(model_path))
        if os.path.exists(alt):
            model_path = alt
        else:
            raise FileNotFoundError(f"Không tìm thấy file trọng số '{model_path}'.")

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
    return model

def predict_single_image(image_path, model_path=MODEL_PATH):
    if not os.path.exists(image_path):
        print(f"[!] Không tìm thấy ảnh: {image_path}")
        return

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = load_inference_model(model_path, device)

    # Tiền xử lý đúng chuẩn MobileNetV2
    transform = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                             std=[0.229, 0.224, 0.225])
    ])

    image = Image.open(image_path).convert('RGB')
    input_tensor = transform(image).unsqueeze(0).to(device)

    with torch.no_grad():
        outputs = model(input_tensor)
        probabilities = torch.softmax(outputs, dim=1)[0]
        confidence, predicted_idx = torch.max(probabilities, 0)

    predicted_label = CLASS_NAMES[predicted_idx.item()]
    conf_percent = confidence.item() * 100

    print("=" * 50)
    print(" KẾT QUẢ DỰ ĐOÁN PHÂN LOẠI KHOAI TÂY (EDGE INFERENCE)")
    print("=" * 50)
    print(f"Ảnh đầu vào: {image_path}")
    print(f"Nhãn dự đoán: {predicted_label.upper()} ({'Khoai tây đạt chuẩn' if predicted_label == 'good' else 'Khoai tây hỏng / không đạt'})")
    print(f"Độ tin cậy: {conf_percent:.2f}%")
    print("Xác suất chi tiết:")
    for idx, name in enumerate(CLASS_NAMES):
        print(f"  - {name}: {probabilities[idx].item() * 100:.2f}%")
    print("=" * 50)

    return predicted_label, conf_percent

if __name__ == '__main__':
    # Hướng dẫn: Chạy 'python inference.py <đường_dẫn_ảnh>'
    if len(sys.argv) > 1:
        test_img = sys.argv[1]
    else:
        # Mặc định lấy thử 1 ảnh nếu có
        sample_path = 'dataset/good/good_1.jpg'
        test_img = sample_path if os.path.exists(sample_path) else 'sample.jpg'
    
    predict_single_image(test_img)
