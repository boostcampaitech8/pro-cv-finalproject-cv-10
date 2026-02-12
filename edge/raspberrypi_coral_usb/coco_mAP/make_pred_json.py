import os
import json

GT_COCO   = "/home/raspberrypi/Desktop/boonseok/gt_coco.json"
PRED_DIR  = "/home/raspberrypi/Desktop/boonseok/pred_1_ssd"
OUT_PRED  = "/home/raspberrypi/Desktop/boonseok/ssd_coco.json"

# -------------------------
# 1) GT에서 file_name -> image_id 매핑 만들기
# -------------------------
with open(GT_COCO, "r") as f:
    gt = json.load(f)

file_to_image_id = {}
for img in gt.get("images", []):
    file_to_image_id[img["file_name"]] = img["id"]

# -------------------------
# 2) pred 폴더의 json들을 COCO pred(list)로 합치기
# -------------------------
coco_preds = []

miss_file = 0
bad_bbox = 0
total_det = 0
used_det = 0

for jf in sorted(os.listdir(PRED_DIR)):
    if not jf.endswith(".json"):
        continue

    jpath = os.path.join(PRED_DIR, jf)
    with open(jpath, "r") as f:
        data = json.load(f)

    preds = data.get("predictions", [])  # ✅ 너 포맷
    if not preds:
        continue

    for p in preds:
        total_det += 1

        fname = p.get("filename")
        if not fname:
            miss_file += 1
            continue

        if fname not in file_to_image_id:
            # GT에 없는 이미지면 COCOeval에서 매칭 불가 -> 스킵
            miss_file += 1
            continue

        bbox = p.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            bad_bbox += 1
            continue

        x, y, w, h = map(float, bbox)
        score = float(p.get("score", 0.0))
        category_id = int(p.get("category_id", -1))
        if category_id < 0:
            continue

        coco_preds.append({
            "image_id": int(file_to_image_id[fname]),
            "category_id": category_id,
            "bbox": [x, y, w, h],   # ✅ pixel xywh
            "score": score
        })
        used_det += 1

# -------------------------
# 3) 저장
# -------------------------
with open(OUT_PRED, "w") as f:
    json.dump(coco_preds, f, indent=2)

print("✅ COCO predictions saved:", OUT_PRED)
print("GT images:", len(gt.get("images", [])))
print("Total detections read:", total_det)
print("Detections used:", used_det)
print("Skipped (filename missing or not in GT):", miss_file)
print("Skipped (bad bbox):", bad_bbox)
