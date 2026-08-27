"""
Module 2 — Oil Spill Detection (inference wrapper)
----------------------------------------------------
Extracted from the team's oil_spill_main_compatibilty_sort.ipynb
(Module 2 branch). Loads the trained MobileNetV2 classifier once and
exposes detect_oil(image_path) -> dict, matching analyze_image() from
the notebook (classification + confidence; severity overlay skipped
here since the API returns JSON, not images).

Falls back to a clearly-labeled mock prediction if torch/opencv or the
checkpoint aren't available in the current environment, so the rest of
the pipeline is never blocked by an environment issue.
"""

import os
import random

WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "vendor", "module2_ai", "oil_spill_main_backup.pth")

_model = None
_device = None
_transform = None
_backend_ready = False
_init_error = None


def _try_init():
    global _model, _device, _transform, _backend_ready, _init_error
    if _backend_ready or _init_error is not None:
        return
    try:
        import torch
        import torch.nn as nn
        from torchvision import models, transforms

        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        model = models.mobilenet_v2(weights=None)  # avoid needing internet for ImageNet weights
        model.classifier[1] = nn.Linear(model.last_channel, 2)

        if not os.path.exists(WEIGHTS_PATH):
            raise FileNotFoundError(f"Checkpoint not found at {WEIGHTS_PATH}")

        state_dict = torch.load(WEIGHTS_PATH, map_location=_device)
        model.load_state_dict(state_dict)
        model.to(_device)
        model.eval()

        _model = model
        _transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        _backend_ready = True
    except Exception as e:  # torch missing, weights missing, etc.
        _init_error = str(e)


def detect_oil(image_path: str) -> dict:
    """
    Returns:
      {
        "oil_detected": bool,
        "confidence": float 0-1,
        "severity": "LOW"|"MEDIUM"|"HIGH",
        "mode": "real" | "mock",
        "note": str (only present in mock mode)
      }
    """
    _try_init()

    if _backend_ready:
        import cv2
        import torch

        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Could not read image at {image_path}")

        img = cv2.medianBlur(img, 5)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        input_tensor = _transform(img_rgb).unsqueeze(0).to(_device)

        with torch.no_grad():
            output = _model(input_tensor)
            probs = torch.softmax(output, dim=1)[0]
            pred_class = int(torch.argmax(probs).item())
            confidence = float(probs[pred_class].item())

        oil_detected = pred_class == 1
        severity = "HIGH" if confidence > 0.85 else ("MEDIUM" if confidence > 0.6 else "LOW")

        return {
            "oil_detected": oil_detected,
            "confidence": round(confidence, 4),
            "severity": severity if oil_detected else "NONE",
            "mode": "real",
        }

    # --- Mock fallback (torch/weights not available in this environment) ---
    confidence = round(random.uniform(0.75, 0.97), 4)
    return {
        "oil_detected": True,
        "confidence": confidence,
        "severity": "HIGH" if confidence > 0.85 else "MEDIUM",
        "mode": "mock",
        "note": f"Module 2 real model unavailable ({_init_error}); using mock detection.",
    }
