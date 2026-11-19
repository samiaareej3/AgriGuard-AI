"""Build a leakage-aware train/val/test split for the tomato subset of PlantVillage.

Leakage controls:
1. PlantVillage contains several photos of the same physical leaf. The
   dataset's own ``leaf-map.json`` maps each image to a leaf ID; all images of
   one leaf are kept in the same split.
2. Near-duplicate images (difference-hash Hamming distance <= 3 within a class)
   are merged into the same group as well.
Groups are then split ~70/15/15 with class stratification
(``StratifiedGroupKFold``), seed 42.

Outputs (git-ignored, under dataset/_work/): manifest.csv
Outputs (tracked): reports/dataset_report.json

Usage (from repo root):
    .\\.venv\\Scripts\\python.exe ai_training\\scripts\\prepare_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np
from PIL import Image
from sklearn.model_selection import StratifiedGroupKFold

from common import (
    LEAF_MAP, MANIFEST, RAW_DIR, REPORTS_DIR, SEED, SOURCE_FOLDERS, WORK_DIR,
)


def dhash(path, size: int = 8) -> int:
    with Image.open(path) as img:
        g = np.asarray(img.convert("L").resize((size + 1, size), Image.Resampling.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def main() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    leaf_map = json.loads(LEAF_MAP.read_text(encoding="utf-8"))

    rows = []
    for folder, cls in SOURCE_FOLDERS.items():
        files = sorted(p for p in (RAW_DIR / folder).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        for p in files:
            key = p.stem.split("___", 1)[-1].lower()  # e.g. "rs_erly.b 8389"
            leaf = None
            for entry in leaf_map.get(key, []):
                src_cls, _, leaf_id = entry.partition(":::")
                if src_cls == folder:
                    leaf = f"{folder}:{leaf_id}"
            rows.append({
                "path": str(p.relative_to(RAW_DIR.parents[1])).replace("\\", "/"),
                "abs": p, "class": cls, "leaf": leaf,
                "sha1": hashlib.sha1(p.read_bytes()).hexdigest(),
            })
    print(f"images: {len(rows)}")

    # Exact duplicates (same bytes) across the whole subset.
    exact = Counter(r["sha1"] for r in rows)
    print(f"exact duplicate files: {sum(c - 1 for c in exact.values() if c > 1)}")

    uf = UnionFind(len(rows))
    by_leaf: dict[str, list[int]] = defaultdict(list)
    by_sha: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        if r["leaf"]:
            by_leaf[r["leaf"]].append(i)
        by_sha[r["sha1"]].append(i)
    for idxs in list(by_leaf.values()) + list(by_sha.values()):
        for j in idxs[1:]:
            uf.union(idxs[0], j)

    print("computing perceptual hashes ...")
    hashes = np.array([dhash(r["abs"]) for r in rows], dtype=np.uint64)
    near_pairs = 0
    for cls in SOURCE_FOLDERS.values():
        idx = np.array([i for i, r in enumerate(rows) if r["class"] == cls])
        h = hashes[idx]
        for a in range(len(idx)):
            x = np.bitwise_xor(h[a + 1:], h[a])
            dist = np.array([bin(int(v)).count("1") for v in x]) if len(x) else np.array([])
            for b in np.nonzero(dist <= 3)[0]:
                uf.union(int(idx[a]), int(idx[a + 1 + b]))
                near_pairs += 1
    print(f"near-duplicate pairs merged: {near_pairs}")

    groups = np.array([uf.find(i) for i in range(len(rows))])
    labels = np.array([r["class"] for r in rows])
    rng_idx = np.arange(len(rows))

    # Test split: 1 of 7 folds (~14-15%), then validation: 1 of 6 folds of the remainder.
    sgkf = StratifiedGroupKFold(n_splits=7, shuffle=True, random_state=SEED)
    trainval_idx, test_idx = next(sgkf.split(rng_idx, labels, groups))
    sgkf2 = StratifiedGroupKFold(n_splits=6, shuffle=True, random_state=SEED)
    tr_rel, va_rel = next(sgkf2.split(trainval_idx, labels[trainval_idx], groups[trainval_idx]))
    split = np.empty(len(rows), dtype=object)
    split[trainval_idx[tr_rel]] = "train"
    split[trainval_idx[va_rel]] = "val"
    split[test_idx] = "test"

    # Sanity: no group spans two splits.
    g2s: dict[int, set] = defaultdict(set)
    for g, s in zip(groups, split):
        g2s[int(g)].add(s)
    leaks = sum(1 for s in g2s.values() if len(s) > 1)
    assert leaks == 0, f"{leaks} groups span multiple splits"

    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "class", "split", "group", "leaf_id", "sha1"])
        for r, s, g in zip(rows, split, groups):
            w.writerow([r["path"], r["class"], s, int(g), r["leaf"] or "", r["sha1"]])

    counts = {s: dict(Counter(labels[split == s])) for s in ("train", "val", "test")}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "PlantVillage (raw/color), tomato subset",
        "source_url": "https://github.com/spMohanty/PlantVillage-Dataset",
        "license": "CC BY-SA 3.0 (per Hugging Face dataset card mohanty/PlantVillage)",
        "citation": "Mohanty, S.P., Hughes, D.P., Salathé, M. (2016). Using deep learning for image-based "
                    "plant disease detection. Frontiers in Plant Science 7:1419. doi:10.3389/fpls.2016.01419",
        "source_folders": SOURCE_FOLDERS,
        "total_images": len(rows),
        "images_with_leaf_id": sum(1 for r in rows if r["leaf"]),
        "groups": int(len(set(groups.tolist()))),
        "exact_duplicate_files": int(sum(c - 1 for c in exact.values() if c > 1)),
        "near_duplicate_pairs_merged": near_pairs,
        "split_method": "StratifiedGroupKFold (seed 42): test=1/7 of groups, val=1/6 of remainder; "
                        "groups = leaf-map leaf IDs ∪ exact duplicates ∪ dHash Hamming<=3 near-duplicates",
        "class_counts": counts,
        "groups_spanning_splits": leaks,
    }
    (REPORTS_DIR / "dataset_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
