"""Train the AgriGuard tomato-leaf classifier (MobileNetV2 transfer learning).

Stage 1: ImageNet MobileNetV2 frozen, train the classification head.
Stage 2: fine-tune the top of the backbone at a low learning rate
         (BatchNorm layers stay in inference mode).

Augmentation (random flip / rotation / zoom / contrast / brightness) is applied
to TRAINING batches only. Validation and test data are never augmented.
Preprocessing comes from backend/app/ml/preprocessing.py (shared with serving).

Usage (from repo root; CPU is fine, ~20-30 min on a laptop):
    .\\.venv\\Scripts\\python.exe ai_training\\scripts\\train.py
Options: --epochs-head 8 --epochs-finetune 5 --finetune-layers 30 --batch 32
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
from PIL import Image

from common import (
    CACHE, CLASS_IDS, CONFIG_PATH, DISPLAY_NAMES, INPUT_SIZE, MANIFEST, MODEL_PATH, MODELS_DIR,
    PREPROCESSING_ID, RAW_DIR, REPORTS_DIR, SEED, mobilenet_v2_scale, prepare_image,
)


def load_arrays() -> dict[str, tuple[np.ndarray, np.ndarray, list[str]]]:
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    if CACHE.exists():
        data = np.load(CACHE, allow_pickle=False)
        if len(data["paths"]) == len(rows):
            print("using cached 224x224 arrays")
            out = {}
            for s in ("train", "val", "test"):
                m = data["split"] == s
                out[s] = (data["x"][m], data["y"][m], data["paths"][m].tolist())
            return out
    print("decoding images with shared prepare_image() ...")
    root = RAW_DIR.parents[1]
    x = np.empty((len(rows), INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
    for i, r in enumerate(rows):
        with Image.open(root / r["path"]) as img:
            x[i] = prepare_image(img)
    y = np.array([CLASS_IDS.index(r["class"]) for r in rows], dtype=np.int64)
    split = np.array([r["split"] for r in rows])
    paths = np.array([r["path"] for r in rows])
    np.savez(CACHE, x=x, y=y, split=split, paths=paths)
    return {s: (x[split == s], y[split == s], paths[split == s].tolist()) for s in ("train", "val", "test")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs-head", type=int, default=8)
    ap.add_argument("--epochs-finetune", type=int, default=5)
    ap.add_argument("--finetune-layers", type=int, default=30)
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()

    import keras
    import tensorflow as tf

    keras.utils.set_random_seed(SEED)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    data = load_arrays()
    (xtr, ytr, _), (xva, yva, _) = data["train"], data["val"]
    print({s: len(v[1]) for s, v in data.items()})

    augment = keras.Sequential([
        keras.layers.RandomFlip("horizontal_and_vertical"),
        keras.layers.RandomRotation(0.08, fill_mode="reflect"),
        keras.layers.RandomZoom((-0.1, 0.1), fill_mode="reflect"),
        keras.layers.RandomContrast(0.15),
        keras.layers.RandomBrightness(0.15, value_range=(0, 255)),
    ], name="train_augmentation")

    def scale(x):  # identical math to mobilenet_v2_scale
        return tf.cast(x, tf.float32) / 127.5 - 1.0

    train_ds = (
        tf.data.Dataset.from_tensor_slices((xtr, ytr))
        .shuffle(len(ytr), seed=SEED, reshuffle_each_iteration=True)
        .batch(args.batch)
        .map(lambda x, y: (scale(tf.clip_by_value(augment(tf.cast(x, tf.float32), training=True), 0, 255)), y),
             num_parallel_calls=tf.data.AUTOTUNE)
        .prefetch(tf.data.AUTOTUNE)
    )
    val_ds = (
        tf.data.Dataset.from_tensor_slices((xva, yva)).batch(args.batch)
        .map(lambda x, y: (scale(x), y), num_parallel_calls=tf.data.AUTOTUNE).prefetch(tf.data.AUTOTUNE)
    )

    # Class weights compensate for imbalance (early blight is the minority class).
    counts = np.bincount(ytr, minlength=len(CLASS_IDS))
    class_weight = {i: float(len(ytr) / (len(CLASS_IDS) * c)) for i, c in enumerate(counts)}
    print("class weights:", class_weight)

    base = keras.applications.MobileNetV2(
        input_shape=(INPUT_SIZE, INPUT_SIZE, 3), include_top=False, weights="imagenet"
    )
    base.trainable = False
    inputs = keras.Input((INPUT_SIZE, INPUT_SIZE, 3), name="image")  # already scaled to [-1, 1]
    x = base(inputs, training=False)  # keep BatchNorm statistics frozen
    x = keras.layers.GlobalAveragePooling2D()(x)
    x = keras.layers.Dropout(0.3, seed=SEED)(x)
    outputs = keras.layers.Dense(len(CLASS_IDS), activation="softmax", name="probabilities")(x)
    model = keras.Model(inputs, outputs, name="agriguard_mobilenetv2")

    ckpt = keras.callbacks.ModelCheckpoint(MODEL_PATH, monitor="val_loss", save_best_only=True)
    early = keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)
    history: dict[str, list[float]] = {}

    def run(epochs: int, lr: float, stage: str) -> None:
        model.compile(optimizer=keras.optimizers.Adam(lr), loss="sparse_categorical_crossentropy",
                      metrics=["accuracy"])
        t = time.time()
        h = model.fit(train_ds, validation_data=val_ds, epochs=epochs, class_weight=class_weight,
                      callbacks=[ckpt, early], verbose=2)
        print(f"{stage} done in {time.time() - t:.0f}s")
        for k, v in h.history.items():
            history.setdefault(k, []).extend(float(a) for a in v)
        history.setdefault("stage", []).extend([stage] * len(h.history["loss"]))

    t0 = time.time()
    run(args.epochs_head, 1e-3, "head")
    if args.epochs_finetune > 0:
        base.trainable = True
        for layer in base.layers[: -args.finetune_layers]:
            layer.trainable = False
        for layer in base.layers:
            if isinstance(layer, keras.layers.BatchNormalization):
                layer.trainable = False
        run(args.epochs_finetune, 1e-5, "finetune")
    train_seconds = time.time() - t0

    model.save(MODEL_PATH)  # best weights restored by EarlyStopping
    version = "tomato-mnv2-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    config = {
        "model_version": version,
        "architecture": "MobileNetV2 (ImageNet) + GAP + Dropout(0.3) + Dense softmax",
        "crop": "tomato",
        "classes": CLASS_IDS,
        "display_names": DISPLAY_NAMES,
        "input_size": INPUT_SIZE,
        "preprocessing": PREPROCESSING_ID,
        "preprocessing_detail": "EXIF transpose, RGB, center square crop, bilinear resize 224, x/127.5-1",
        "recommended_confidence_threshold": 0.75,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training": {
            "epochs_head": args.epochs_head, "epochs_finetune": args.epochs_finetune,
            "finetune_layers": args.finetune_layers, "batch_size": args.batch, "seed": SEED,
            "class_weight": class_weight, "train_seconds": round(train_seconds, 1),
            "augmentation": "train only: flip h+v, rotation 0.08, zoom ±10%, contrast 0.15, brightness 0.15",
            "tensorflow_version": tf.__version__, "keras_version": keras.__version__,
        },
        "dataset": json.loads((REPORTS_DIR / "dataset_report.json").read_text(encoding="utf-8")),
        "history": history,
        "metrics": None,  # filled by evaluate.py on the held-out test split
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"saved {MODEL_PATH} and {CONFIG_PATH} ({train_seconds:.0f}s)")


if __name__ == "__main__":
    main()
