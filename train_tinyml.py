"""Train a compact 96x96 depthwise-separable CNN and export full-int8 TFLite."""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import tensorflow as tf
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent
DATASET_DIR = ROOT / "dataset"
OUTPUT_DIR = ROOT / "models" / "tinyml"
IDF_MAIN_DIR = ROOT / "esp32_iot_system" / "tinyml_idf" / "main"
IMAGE_SIZE = 96
SEED = 42
BATCH_SIZE = 32
MAX_EPOCHS = 50
CLASS_DIRS = (("good", 0), ("not_good", 1))  # paper: good=0, poor=1
VALID_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def collect_images():
    paths, labels = [], []
    for class_name, label in CLASS_DIRS:
        class_dir = DATASET_DIR / class_name
        if not class_dir.is_dir():
            raise FileNotFoundError(f"Missing source class directory: {class_dir}")
        class_paths = sorted(
            p for p in class_dir.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_SUFFIXES
        )
        if not class_paths:
            raise ValueError(f"No images found in {class_dir}")
        paths.extend(str(p) for p in class_paths)
        labels.extend([label] * len(class_paths))
    return np.asarray(paths), np.asarray(labels, dtype=np.int32)


def load_image(path, label):
    image = tf.io.decode_image(tf.io.read_file(path), channels=3, expand_animations=False)
    image.set_shape([None, None, 3])
    image = tf.image.resize(image, [IMAGE_SIZE, IMAGE_SIZE], method="bilinear")
    return tf.cast(image, tf.float32) / 255.0, tf.cast(label, tf.float32)


def augment(image, label):
    image = tf.image.random_flip_left_right(image)
    image = tf.image.rot90(image, tf.random.uniform([], 0, 4, dtype=tf.int32))
    image = tf.image.random_brightness(image, max_delta=0.08)
    return tf.clip_by_value(image, 0.0, 1.0), label


def make_dataset(paths, labels, training=False):
    ds = tf.data.Dataset.from_tensor_slices((paths, labels))
    if training:
        ds = ds.shuffle(len(paths), seed=SEED, reshuffle_each_iteration=True)
    ds = ds.map(load_image, num_parallel_calls=tf.data.AUTOTUNE)
    if training:
        ds = ds.map(augment, num_parallel_calls=tf.data.AUTOTUNE)
    return ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)


def build_model():
    inputs = tf.keras.Input(shape=(IMAGE_SIZE, IMAGE_SIZE, 3), name="image")
    x = tf.keras.layers.Conv2D(8, 3, strides=2, padding="same", use_bias=False)(inputs)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.ReLU(max_value=6.0)(x)
    for filters in (16, 32, 48):
        x = tf.keras.layers.SeparableConv2D(
            filters, 3, strides=2, padding="same", use_bias=False
        )(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.ReLU(max_value=6.0)(x)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="poor_probability")(x)
    return tf.keras.Model(inputs, outputs, name="potato_tiny_dsc")


def write_c_header(model_bytes):
    IDF_MAIN_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for offset in range(0, len(model_bytes), 12):
        values = ", ".join(f"0x{x:02x}" for x in model_bytes[offset:offset + 12])
        rows.append("    " + values)
    header = (
        "#pragma once\n#include <cstddef>\n#include <cstdint>\n\n"
        "alignas(16) const unsigned char g_potato_tflite_model[] = {\n"
        + ",\n".join(rows)
        + "\n};\n"
        "const unsigned int g_potato_tflite_model_len = sizeof(g_potato_tflite_model);\n"
    )
    path = IDF_MAIN_DIR / "potato_tiny_model_data.h"
    path.write_text(header, encoding="ascii")
    print(f"Generated firmware model header: {path}")


def decode_array(path):
    image = tf.io.decode_image(tf.io.read_file(path), channels=3, expand_animations=False)
    image.set_shape([None, None, 3])
    image = tf.image.resize(image, [IMAGE_SIZE, IMAGE_SIZE], method="bilinear")
    return image.numpy()[None, ...] / 255.0


def evaluate_int8(model_path, paths, labels):
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()
    inp = interpreter.get_input_details()[0]
    out = interpreter.get_output_details()[0]
    in_scale, in_zero = inp["quantization"]
    out_scale, out_zero = out["quantization"]
    if in_scale == 0 or out_scale == 0:
        raise RuntimeError("TFLite input/output quantization parameters are missing")

    predictions = []
    for path in paths:
        real_input = decode_array(path)
        quant_input = np.clip(np.rint(real_input / in_scale + in_zero), 0, 255).astype(np.uint8)
        interpreter.set_tensor(inp["index"], quant_input)
        interpreter.invoke()
        raw = interpreter.get_tensor(out["index"])[0][0]
        poor_probability = float((raw - out_zero) * out_scale)
        predictions.append(int(poor_probability >= 0.5))

    print(f"INT8 test accuracy: {accuracy_score(labels, predictions):.4%}")
    print(classification_report(
        labels, predictions, labels=[0, 1], target_names=["good", "not_good"], digits=4
    ))
    print("INT8 confusion matrix (rows=true, columns=predicted):")
    print(confusion_matrix(labels, predictions, labels=[0, 1]))


def representative_dataset(paths):
    for path in paths[:min(200, len(paths))]:
        yield [decode_array(path).astype(np.float32)]


def main():
    random.seed(SEED)
    np.random.seed(SEED)
    tf.random.set_seed(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    paths, labels = collect_images()
    train_paths, held_paths, train_labels, held_labels = train_test_split(
        paths, labels, test_size=0.30, random_state=SEED, stratify=labels
    )
    val_paths, test_paths, val_labels, test_labels = train_test_split(
        held_paths, held_labels, test_size=0.50, random_state=SEED, stratify=held_labels
    )
    split = {
        "total": int(len(paths)), "train": int(len(train_paths)),
        "validation": int(len(val_paths)), "test": int(len(test_paths)),
        "good": int(np.sum(labels == 0)), "not_good": int(np.sum(labels == 1)), "seed": SEED,
    }
    (OUTPUT_DIR / "split_summary.json").write_text(json.dumps(split, indent=2), encoding="utf-8")
    print(json.dumps(split, indent=2))

    train_ds = make_dataset(train_paths, train_labels, training=True)
    val_ds = make_dataset(val_paths, val_labels)
    test_ds = make_dataset(test_paths, test_labels)
    model = build_model()
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="binary_crossentropy", metrics=["accuracy"],
    )
    model.summary()
    best_path = OUTPUT_DIR / "best_tiny_dsc.keras"
    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=6, restore_best_weights=True),
        tf.keras.callbacks.ModelCheckpoint(str(best_path), monitor="val_loss", save_best_only=True),
    ]
    model.fit(train_ds, validation_data=val_ds, epochs=MAX_EPOCHS, callbacks=callbacks)
    model = tf.keras.models.load_model(best_path)
    print("FP32 model test metrics:")
    model.evaluate(test_ds, verbose=2)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    float_model = converter.convert()
    (OUTPUT_DIR / "potato_tiny_fp32.tflite").write_bytes(float_model)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: representative_dataset(train_paths)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.uint8
    converter.inference_output_type = tf.uint8
    int8_model = converter.convert()
    int8_path = OUTPUT_DIR / "potato_tiny_int8.tflite"
    int8_path.write_bytes(int8_model)
    write_c_header(int8_model)
    print(f"FP32 TFLite size: {len(float_model):,} bytes")
    print(f"INT8 TFLite size: {len(int8_model):,} bytes")
    print("INT8 model test metrics:")
    evaluate_int8(int8_path, test_paths, test_labels)


if __name__ == "__main__":
    main()
