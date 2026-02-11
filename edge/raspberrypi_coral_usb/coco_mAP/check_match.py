import os
import json
import cv2

IMG_DIR  = "/home/raspberrypi/Desktop/boonseok/images"
JSON_DIR = "/home/raspberrypi/Desktop/boonseok/pred_1_ssd"
OUT_DIR  = "/home/raspberrypi/Desktop/boonseok/bbox_check_ssd"
os.makedirs(OUT_DIR, exist_ok=True)

TARGET_W, TARGET_H = 640, 360

for jf in os.listdir(JSON_DIR):
    if not jf.endswith(".json"):
        continue

    jpath = os.path.join(JSON_DIR, jf)

    with open(jpath, "r") as f:
        data = json.load(f)

    preds = data.get("predictions", [])
    if len(preds) == 0:
        continue

    # 한 json 안의 preds는 보통 같은 filename을 공유한다고 가정
    filename = preds[0].get("filename")
    if not filename:
        print("filename 없음:", jf)
        continue

    img_path = os.path.join(IMG_DIR, filename)
    if not os.path.exists(img_path):
        print("이미지 없음:", filename)
        continue

    img = cv2.imread(img_path)
    if img is None:
        print("이미지 로드 실패:", img_path)
        continue

    # 혹시 크기 다르면 맞춤
    if img.shape[1] != TARGET_W or img.shape[0] != TARGET_H:
        img = cv2.resize(img, (TARGET_W, TARGET_H))

    for p in preds:
        bbox = p.get("bbox", None)
        if bbox is None or len(bbox) != 4:
            continue

        x, y, w, h = bbox
        x1, y1 = int(x), int(y)
        x2, y2 = int(x + w), int(y + h)

        # 클래스명 우선 (없으면 id로)
        cls = p.get("category_name", None)
        if cls is None:
            cls = str(p.get("category_id", "unknown"))

        score = p.get("score", None)
        if score is not None:
            label = f"{cls} {score:.2f}"
        else:
            label = str(cls)

        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, label, (x1, max(0, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    out_path = os.path.join(OUT_DIR, filename)
    cv2.imwrite(out_path, img)

print("bbox 시각화 완료")
