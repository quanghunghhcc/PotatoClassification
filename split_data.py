import os
import shutil
import random
from pathlib import Path

# Cấu hình tỷ lệ chia tập dữ liệu (Chuẩn cho đồ án AI: 80% Train, 10% Val, 10% Test)
# Nếu bạn chỉ muốn Train và Val, có thể đổi TEST_RATIO = 0.0 và VAL_RATIO = 0.2
TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
TEST_RATIO = 0.1
RANDOM_SEED = 42

DATASET_DIR = Path("./dataset")
CLASSES = ["good", "not_good"]

def split_dataset():
    if any(ratio < 0 for ratio in (TRAIN_RATIO, VAL_RATIO, TEST_RATIO)):
        raise ValueError("Các tỷ lệ chia tập không được âm.")
    if abs(TRAIN_RATIO + VAL_RATIO + TEST_RATIO - 1.0) > 1e-9:
        raise ValueError("TRAIN_RATIO + VAL_RATIO + TEST_RATIO phải bằng 1.")

    random.seed(RANDOM_SEED)

    # Kiểm tra xem thư mục nguồn có tồn tại không
    for cls in CLASSES:
        cls_dir = DATASET_DIR / cls
        if not cls_dir.exists() or not cls_dir.is_dir():
            print(f"[!] Lỗi: Không tìm thấy thư mục gốc '{cls_dir}'. Vui lòng kiểm tra lại cấu trúc dataset.")
            return

    # Tạo các thư mục đích: dataset/train, dataset/val, dataset/test
    splits = ["train", "val"]
    if TEST_RATIO > 0:
        splits.append("test")

    # Xóa nội dung chia cũ theo đúng hai lớp đã biết để không sót ảnh khi chạy lại.
    # Không đụng đến thư mục nguồn dataset/good và dataset/not_good.
    for split in ("train", "val", "test"):
        for cls in CLASSES:
            target_dir = DATASET_DIR / split / cls
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(" BẮT ĐẦU PHÂN CHIA TẬP DỮ LIỆU KHOAI TÂY (TRAIN / VAL / TEST)")
    print(f" Tỷ lệ: Train = {TRAIN_RATIO*100:.0f}%, Val = {VAL_RATIO*100:.0f}%, Test = {TEST_RATIO*100:.0f}%")
    print("=" * 60)

    for cls in CLASSES:
        src_dir = DATASET_DIR / cls
        # Lấy tất cả ảnh hợp lệ (.jpg, .jpeg, .png, .bmp)
        images = [f for f in src_dir.iterdir() if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]]
        random.shuffle(images)

        total_imgs = len(images)
        train_end = int(total_imgs * TRAIN_RATIO)
        val_end = train_end + int(total_imgs * VAL_RATIO)

        train_imgs = images[:train_end]
        val_imgs = images[train_end:val_end]
        test_imgs = images[val_end:] if TEST_RATIO > 0 else []

        # Hàm copy ảnh
        def copy_files(file_list, split_name):
            for file_path in file_list:
                dst = DATASET_DIR / split_name / cls / file_path.name
                shutil.copy2(file_path, dst)

        copy_files(train_imgs, "train")
        copy_files(val_imgs, "val")
        if TEST_RATIO > 0:
            copy_files(test_imgs, "test")

        print(f"Lớp '{cls}': Tổng {total_imgs} ảnh -> Train: {len(train_imgs)} | Val: {len(val_imgs)} | Test: {len(test_imgs)}")

    print("=" * 60)
    print("[v] Phân chia hoàn tất thành công! Dữ liệu đã sẵn sàng trong thư mục 'dataset/train', 'dataset/val', 'dataset/test'.")
    print("=" * 60)

if __name__ == "__main__":
    split_dataset()
