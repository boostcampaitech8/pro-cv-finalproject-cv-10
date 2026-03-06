import os
import json

LBL_DIR = "/home/raspberrypi/Desktop/boonseok/lbl_resized"
OUT_GT  = "/home/raspberrypi/Desktop/boonseok/gt_coco.json"

# 프로젝트 class 정의
categories = [
    {"id": 0, "name": "fishing_ship"},
    {"id": 1, "name": "merchant_ship"},
    {"id": 2, "name": "navy_ship"},
    {"id": 3, "name": "person"},
    {"id": 4, "name": "seabird"},
    {"id": 5, "name": "ship_etc/none"},
]

coco = {
    "images": [],
    "annotations": [],
    "categories": categories
}

image_id_map = {}
img_id = 0
ann_id = 0

for jf in sorted(os.listdir(LBL_DIR)):
    if not jf.endswith(".json"):
        continue

    with open(os.path.join(LBL_DIR, jf), "r") as f:
        data = json.load(f)

    anns = data.get("annotations", [])
    if len(anns) == 0:
        continue

    for a in anns:
        fname = a["filename"]
        width = int(a["width"])
        height = int(a["height"])

        # images 등록
        if fname not in image_id_map:
            image_id_map[fname] = img_id
            coco["images"].append({
                "id": img_id,
                "file_name": fname,
                "width": width,
                "height": height
            })
            img_id += 1

        # annotation 등록
        x, y, w, h = map(float, a["bbox"])

        coco["annotations"].append({
            "id": ann_id,
            "image_id": image_id_map[fname],
            "category_id": int(a["class"]),
            "bbox": [x, y, w, h],
            "area": float(w * h),
            "iscrowd": 0
        })
        ann_id += 1

with open(OUT_GT, "w") as f:
    json.dump(coco, f, indent=2)

print("✅ COCO GT saved:", OUT_GT)
print("images:", len(coco["images"]))
print("annotations:", len(coco["annotations"]))
