"""Receive ESP32-CAM JPEGs, classify them with the trained PyTorch model."""

import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms


MODEL_PATH = "best_potato_model.pth"
HOST = "0.0.0.0"
PORT = 5001
IMG_SIZE = 224
CLASS_NAMES = ["good", "not_good"]
MAX_IMAGE_BYTES = 2 * 1024 * 1024
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def load_model():
    model_path = MODEL_PATH
    if not os.path.isfile(model_path):
        model_path = os.path.join("models", os.path.basename(MODEL_PATH))
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Model not found: {MODEL_PATH} or models/{MODEL_PATH}")

    model = models.mobilenet_v2(weights=None)
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.2),
        nn.Linear(model.classifier[1].in_features, len(CLASS_NAMES)),
    )
    model.load_state_dict(torch.load(model_path, map_location=DEVICE, weights_only=True))
    model.to(DEVICE).eval()
    print(f"Loaded {model_path} on {DEVICE}")
    return model


PREPROCESS = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
MODEL = None


class ClassifierHandler(BaseHTTPRequestHandler):
    def _reply(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/classify":
            self._reply(404, {"error": "not_found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > MAX_IMAGE_BYTES:
                self._reply(413, {"error": "invalid_image_size"})
                return

            image_bytes = self.rfile.read(content_length)
            if len(image_bytes) != content_length:
                self._reply(400, {"error": "incomplete_image"})
                return

            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            input_tensor = PREPROCESS(image).unsqueeze(0).to(DEVICE)
            with torch.inference_mode():
                probabilities = torch.softmax(MODEL(input_tensor), dim=1)[0]
                confidence, class_index = torch.max(probabilities, dim=0)

            result = {
                "quality": CLASS_NAMES[class_index.item()],
                "confidence": round(confidence.item(), 4),
            }
            print(f"{result['quality']} ({result['confidence']:.1%}) from {self.client_address[0]}")
            self._reply(200, result)
        except Exception as exc:
            print(f"Classification request failed: {exc}")
            self._reply(400, {"error": "classification_failed"})

    def log_message(self, fmt, *args):
        return


def main():
    global MODEL
    MODEL = load_model()
    server = ThreadingHTTPServer((HOST, PORT), ClassifierHandler)
    print(f"ESP32-CAM classifier listening on http://{HOST}:{PORT}/classify")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
