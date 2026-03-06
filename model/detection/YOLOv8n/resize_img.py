import cv2
import os

input_dir = "/data/ephemeral/home/demo_images"
output_dir = "/data/ephemeral/home/resized_demo"

os.makedirs(output_dir, exist_ok=True)

valid_ext = (".jpg", ".jpeg", ".png", ".bmp")

for fname in os.listdir(input_dir):
    if not fname.lower().endswith(valid_ext):
        continue

    src_path = os.path.join(input_dir, fname)
    dst_path = os.path.join(output_dir, fname)

    img = cv2.imread(src_path)
    if img is None:
        print(f"[WARN] Failed to read {fname}")
        continue

    resized = cv2.resize(img, (640, 360))  # (W, H)
    cv2.imwrite(dst_path, resized)

    print(f"[OK] {fname} -> 640x360")

print("Done.")
