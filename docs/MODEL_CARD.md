# Model card: `tomato-mnv2-20261118-1120`

## Intended use

Decision support for spotting **Early Blight** and **Late Blight** on single **tomato** leaves, feeding a
separate safety engine that may *propose* a spray for operator approval. **Not** a guaranteed field
diagnosis. Out-of-scope: other crops, other diseases, whole-plant/canopy images, and any automatic spraying
without the safety engine.

## Data

- **Source:** PlantVillage dataset, `raw/color` tomato folders, https://github.com/spMohanty/PlantVillage-Dataset
- **License:** CC BY-SA 3.0 (per the Hugging Face dataset card `mohanty/PlantVillage`)
- **Citation:** Mohanty, S.P., Hughes, D.P., Salathé, M. (2016). *Using deep learning for image-based plant
  disease detection.* Frontiers in Plant Science 7:1419. doi:10.3389/fpls.2016.01419
- **Retrieved:** 2026-11-18 (sparse clone of the three class folders + `leaf-map.json`)
- **Images:** 4,500 (Early Blight 1,000 · Late Blight 1,909 · Healthy 1,591). Lab photos: one leaf, plain background.

### Leakage control (split)

PlantVillage contains multiple photos of the same physical leaf. `prepare_dataset.py` groups images by
(1) the dataset's own `leaf-map.json` leaf IDs (2,918 images mapped), (2) exact duplicate bytes (14 found),
and (3) near-duplicates (difference-hash Hamming ≤ 3 within class, 34 pairs). 2,280 groups were split with
`StratifiedGroupKFold` (seed 42): **train 3,212 / val 644 / test 644**, with 0 groups spanning splits.

| Split | Early Blight | Healthy | Late Blight |
|---|---|---|---|
| train | 712 | 1,137 | 1,363 |
| val | 144 | 227 | 273 |
| test | 144 | 227 | 273 |

## Training

- MobileNetV2 (ImageNet weights) → GlobalAveragePooling → Dropout 0.3 → Dense(3, softmax), 224×224 RGB.
- Preprocessing (shared file `backend/app/ml/preprocessing.py`, used by training *and* serving): EXIF
  transpose → RGB → centre square crop → bilinear resize 224 → `x/127.5 − 1` (asserted equal to
  `keras.applications.mobilenet_v2.preprocess_input` in a test).
- Augmentation on **training batches only**: flips, ±8 % rotation, ±10 % zoom, contrast/brightness ±15 %.
- Class weights for imbalance. Stage 1: frozen backbone, Adam 1e-3, 8 epochs. Stage 2: fine-tune top 30
  layers (BatchNorm frozen), Adam 1e-5, 5 epochs. Best weights by validation loss.
- CPU (Intel i7-8550U), TensorFlow 2.21 / Keras 3.15, 1,084 s total. Best validation accuracy 95.8 %.

## Evaluation (held-out test split, n = 644, evaluated once after training)

| Metric | Value |
|---|---|
| Accuracy | **96.89 %** |
| Macro precision / recall / F1 | 96.60 % / 96.57 % / **96.57 %** |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Early Blight | 95.07 % | 93.75 % | 94.41 % | 144 |
| Healthy | 96.60 % | 100.00 % | 98.27 % | 227 |
| Late Blight | 98.13 % | 95.97 % | 97.04 % | 273 |

Confusion matrix (rows = true, columns = predicted: Early, Healthy, Late):

```
Early   135    4    5
Healthy   0  227    0
Late      7    4  262
```

**Uncertainty trade-off** (top-class confidence threshold → share auto-labelled / accuracy on those):

| Threshold | 0.50 | 0.60 | 0.70 | **0.75** | 0.80 | 0.85 | 0.90 | 0.95 |
|---|---|---|---|---|---|---|---|---|
| Coverage | 99.2 % | 97.2 % | 94.3 % | **93.2 %** | 91.8 % | 88.8 % | 83.9 % | 77.3 % |
| Accuracy | 97.3 % | 97.8 % | 98.5 % | **98.5 %** | 99.0 % | 99.1 % | 99.6 % | 99.6 % |

At the default 0.75 threshold, 44 of 644 test images (6.8 %) are routed to human review. The service also
requires a 15-point top-2 margin.

**Inference time** (CPU laptop, eager single image incl. decode + preprocess): mean 184.8 ms, p95 226.9 ms;
batch-32 throughput 39.3 images/s. Observed end-to-end API scans: ~300 ms.

Plots: `ai_training/reports/confusion_matrix.png`, `training_curves.png`, `confidence_coverage.png`.
Raw numbers: `ai_training/reports/metrics.json` (also embedded in `agriguard_model_config.json` and shown
in the dashboard under Settings → Model).

## Limitations and risks

- **Domain shift:** lab images with uniform backgrounds. Field photos (clutter, lighting, multiple leaves,
  occlusion, ESP32-CAM optics) will reduce accuracy. **Field performance has not been measured.**
- A 3-class softmax always picks one of its classes. Out-of-distribution images (other plants or diseases)
  can still receive high confidence. Mitigations: threshold + margin, a "leaf-coloured area" heuristic that
  forces review on clearly non-plant images, operator approval, and the safety engine. These reduce the
  risk but do not remove it.
- Early Blight is the weakest class (recall 93.8 %). Confusions are mostly with Late Blight.
- One of the bundled simulator samples (`early_blight_1.jpg`) is a correctly-ranked but low-confidence
  (52.6 %) case. It is kept deliberately to demonstrate the REVIEW_REQUIRED path.

## Re-training

`ai_training/scripts/{prepare_dataset,train,evaluate}.py` or the Colab notebook. Add field images from the
ESP32-CAM (with consent and labels) as a new **test** set before trusting the model in the field.
