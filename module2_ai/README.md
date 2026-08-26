# 🛰️ MARIS — Oil Spill Detection Module (Module 2: AI)

This module is the AI/ML component of the **MARIS** project. It detects oil spills in **Sentinel-1 SAR (Synthetic Aperture Radar) satellite imagery**, using a fine-tuned MobileNetV2 classifier, then localizes and visualizes *where* the spill is and roughly *how severe* it looks.

---

## What this does, in plain terms

1. **Classify** — Given a SAR image chip, the model decides: `Oil Detected` or `No Oil`, with a confidence score.
2. **Localize** — If oil is detected, [Grad-CAM](https://github.com/jacobgil/pytorch-grad-cam) highlights *which part* of the image the model focused on to make that call.
3. **Estimate severity** — Within that highlighted region, darker pixels are treated as denser oil (oil dampens surface waves, which shows up as darker/lower backscatter in SAR). This produces a color-coded overlay.
4. **Demo it** — A [Gradio](https://www.gradio.app/) web app lets you upload an image and see all of the above live.

> ⚠️ The severity overlay is a **visual heuristic**, not a scientifically validated thickness measurement — there's no ground-truth oil-thickness data in the training set to calibrate it against.

---

## How it works (pipeline)

```
SAR image (path or array)
        │
        ▼
  Despeckle (median blur)          removes SAR's characteristic grainy noise
        │
        ▼
  MobileNetV2 classifier           Oil / No Oil + confidence
        │
        ▼ (only if "Oil Detected")
  Grad-CAM                         "where is the model looking?"
        │
        ▼
  Severity map                     darker pixels in the flagged region = denser oil
        │
        ▼
  Overlay image + confidence       shown in the Gradio demo
```

The whole pipeline is wrapped in a single function, `analyze_image()`, which is the one entry point used by both the demo and the test/evaluation cells. It accepts either:
- a **file path** (string) — e.g. the `.jpg` chips from the training dataset, or
- an **already-loaded grayscale array** — e.g. SAR data converted from GeoTIFF.

---

## Model

- **Architecture:** MobileNetV2 (ImageNet-pretrained backbone, final classifier layer replaced with a 2-class output: `No Oil` / `Oil`)
- **Input:** 224×224, normalized with ImageNet mean/std
- **Weights file:** `oil_spill_main_backup.pth` (PyTorch `state_dict`)
- **Training data:** [CSIRO Sentinel-1 SAR Oil Spill Detection dataset](https://www.kaggle.com/datasets/harikrishnacs/sentinel-1-sar-oil-spill-detection-dataset) (Kaggle) — binary labels, `Class_0` = No Oil, `Class_1` = Oil
- **Split:** 80/20 train/val, stratified by class, `random_state=42` for reproducibility

---

## Files in this module

| File | What it is |
|---|---|
| `oil_spill_main_compatibilty_sort.ipynb` | Main notebook: loads the model, defines the detection pipeline, evaluates it, and launches the Gradio demo |
| `oil_spill_main_backup.pth` | Trained model weights (MobileNetV2 state dict) |
| `README.md` | This file |

---

## Setup (Google Colab)

This notebook is built for Colab and expects to prompt you for file uploads.

1. Upload `oil_spill_main_compatibilty_sort.ipynb` to [Colab](https://colab.research.google.com/) (or open it straight from GitHub via Colab's "Open from GitHub" option).
2. **Runtime → Change runtime type → GPU** (T4 is fine) — the model will run on CPU too, but a GPU makes training/eval much faster.
3. Run cells top to bottom (see [Running it](#running-it) below for what each stage does). You'll be prompted twice for uploads:
   - `oil_spill_main_backup.pth` (the model checkpoint)
   - your own `kaggle.json` (only needed if you want to download the training dataset)

No manual dependency installation needed — Colab has most packages preinstalled, and the notebook itself `pip install`s the few it doesn't (`grad-cam`, `gradio`, `kaggle`).

---

## Running it

1. Run the imports → model setup → load-checkpoint cells, uploading the `.pth` checkpoint when prompted.
2. Run the despeckle / Grad-CAM / severity-map helper cells, then the `analyze_image()` cell — this builds the full pipeline.
3. To evaluate on the dataset or retrain, run the Kaggle download cell (you'll need your own `kaggle.json`) and the cells below it.
4. Run the last cell to launch the **Gradio demo** — it gives you a shareable public link where you can upload a SAR image chip and see the live classification, confidence, and severity overlay.

### Quick usage (in code)

```python
result = analyze_image("path/to/sar_image.jpg")
print(result['prediction'], result['confidence'])   # e.g. "Oil Detected", 92.4

# result also contains:
# result['original']         -> the resized input image
# result['severity_overlay'] -> color overlay (only set if oil was detected)
```

`analyze_image()` also accepts a raw grayscale numpy array directly (e.g. for data converted from GeoTIFF), so it works the same whether the image came from a `.jpg` file or another team's GeoTIFF pipeline.

---

## Notes & limitations

- Trained on SAR image **chips only** — non-SAR images (regular color photos) will still run through the pipeline but aren't meaningful inputs; there's minimal built-in validation for this.
- No pixel-level oil masks exist in the dataset, so localization comes entirely from Grad-CAM (a weakly-supervised technique) rather than trained segmentation.
- Severity values are relative *within* an individual image's flagged region, not comparable in absolute terms across different images.

---

## Part of MARIS

This is Module 2 of the MARIS project (see the other modules: `module1-data`, `module3-environment`, `module5-ais`, `frontend-integration`).
