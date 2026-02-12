import os
import shutil
import random

ORIG_DATASET = "/data/ephemeral/home/datasetV1-1"
CALIB_DATASET = "/data/ephemeral/home/datasetV1-1-calib"

NUM_CALIB = 50
RANDOM_SEED = 42

random.seed(RANDOM_SEED)

IMG_DIR = os.path.join(ORIG_DATASET, "valid/images")
LBL_DIR = os.path.join(ORIG_DATASET, "valid/labels")

OUT_IMG_DIR = os.path.join(CALIB_DATASET, "valid/images")
OUT_LBL_DIR = os.path.join(CALIB_DATASET, "valid/labels")

os.makedirs(OUT_IMG_DIR, exist_ok=True)
os.makedirs(OUT_LBL_DIR, exist_ok=True)

images = [
    f for f in os.listdir(IMG_DIR)
    if f.lower().endswith((".jpg", ".jpeg", ".png"))
]

selected_images = random.sample(images, NUM_CALIB)

print(f"selected calibration image count: {len(selected_images)}")

for img in selected_images:
    shutil.copy2(os.path.join(IMG_DIR, img), os.path.join(OUT_IMG_DIR, img))

    lbl = os.path.splitext(img)[0] + ".txt"
    src_lbl = os.path.join(LBL_DIR, lbl)
    if os.path.exists(src_lbl):
        shutil.copy2(src_lbl, os.path.join(OUT_LBL_DIR, lbl))

print("Calibration dataset produced")
