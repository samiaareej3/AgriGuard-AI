# Sample images — attribution

These 12 images are taken from the **held-out test split** of the PlantVillage dataset (tomato subset)
and are used only by the device simulator ("simulated capture") and the integration tests.

- Source: PlantVillage Dataset — https://github.com/spMohanty/PlantVillage-Dataset (`raw/color/`)
- License: **CC BY-SA 3.0** (per the dataset card at https://huggingface.co/datasets/mohanty/PlantVillage)
- Citation: Mohanty, S.P., Hughes, D.P., Salathé, M. (2016). *Using deep learning for image-based plant
  disease detection.* Frontiers in Plant Science 7:1419. doi:10.3389/fpls.2016.01419
- Changes: renamed only (`<class>_<n>.jpg`). Selected with `ai_training/scripts/evaluate.py` from test
  images the model classified correctly, so simulated demos show the intended class; this is NOT a measure
  of accuracy (see ai_training/reports/metrics.json for real metrics).

Redistribution of these files must keep this attribution and the CC BY-SA 3.0 license.
