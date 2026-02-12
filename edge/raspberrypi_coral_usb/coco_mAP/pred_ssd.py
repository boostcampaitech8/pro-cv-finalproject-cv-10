import os
import json
import time
import cv2
import numpy as np
import tflite_runtime.interpreter as tflite

# ============================================================================  
# 경로 및 설정
# ============================================================================  
IMG_DIR  = "/home/raspberrypi/Desktop/boonseok/images"
OUT_DIR  = "/home/raspberrypi/Desktop/boonseok/pred_1_ssd"

MODEL_PATH    = "/home/raspberrypi/Desktop/workspace/ssd_mobilenet_v2_edgetpu.tflite"
DELEGATE_PATH = "/usr/lib/aarch64-linux-gnu/libedgetpu.so.1"

CONFIDENCE_THRESHOLD = 0.3

# 저장 JSON bbox를 어떤 해상도로 맞출지 (기존처럼 640x360 기준으로 bbox 뽑고 싶으면 유지)
OUTPUT_WIDTH  = 640
OUTPUT_HEIGHT = 360

LABELS = {
    0: "fishing_ship",
    1: "merchant_ship",
    2: "navy_ship",
    3: "person",
    4: "algae"
}

os.makedirs(OUT_DIR, exist_ok=True)

# ============================================================================  
# Edge TPU Interpreter 초기화
# ============================================================================  
interpreter = tflite.Interpreter(
    model_path=MODEL_PATH,
    experimental_delegates=[tflite.load_delegate(DELEGATE_PATH)]
)
interpreter.allocate_tensors()
print("✓ Edge TPU load success")

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
input_h, input_w = input_details[0]["shape"][1:3]
print(f"모델 입력 크기: {input_w}x{input_h}")

# ============================================================================  
# SSD output 텐서 인덱스 찾기 (모델마다 output_details 순서가 달라질 수 있어서 안전하게)
# 보통 TF2 SSD는:
#   boxes:   [1, N, 4]  (ymin,xmin,ymax,xmax)
#   classes: [1, N]
#   scores:  [1, N]
#   count:   [1]
# ============================================================================  
def _shape(od):
    return tuple(od.get("shape", []))

boxes_i = classes_i = scores_i = count_i = None

for i, od in enumerate(output_details):
    s = _shape(od)
    # boxes 후보: (1, N, 4)
    if len(s) == 3 and s[0] == 1 and s[-1] == 4:
        boxes_i = i
    # count 후보: (1,) or (1,1)
    elif len(s) == 1 and s[0] == 1:
        count_i = i
    elif len(s) == 2 and s[0] == 1 and s[1] == 1:
        count_i = i
    # classes/scores 후보: (1, N)
    elif len(s) == 2 and s[0] == 1:
        # dtype로 대략 구분: classes는 float인데 정수처럼 들어오는 경우가 많고,
        # scores도 float. 결국 둘 다 float라서 아래에서 name 힌트도 같이 봄.
        name = (od.get("name") or "").lower()
        if "class" in name:
            classes_i = i
        elif "score" in name or "prob" in name:
            scores_i = i

# name 힌트로 못 잡았으면 (1,N) 텐서들 중 남은 걸 classes/scores로 채움
one_by_n = [i for i, od in enumerate(output_details) if len(_shape(od)) == 2 and _shape(od)[0] == 1]
# boxes_i, count_i 제외하고 남은 것들
candidates = [i for i in one_by_n if i not in {boxes_i, count_i}]
if scores_i is None and len(candidates) >= 1:
    scores_i = candidates[0]
if classes_i is None and len(candidates) >= 2:
    classes_i = candidates[1]

if boxes_i is None or scores_i is None or classes_i is None or count_i is None:
    print("⚠️ output_details를 자동으로 매핑하지 못했습니다.")
    print("output_details:")
    for i, od in enumerate(output_details):
        print(i, od.get("name"), od.get("shape"), od.get("dtype"))
    raise RuntimeError("SSD output tensor mapping failed")

print(f"✓ output mapping: boxes={boxes_i}, scores={scores_i}, classes={classes_i}, count={count_i}")

# ============================================================================  
# 유틸: 이미지 목록
# ============================================================================  
valid_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
img_files = [f for f in os.listdir(IMG_DIR) if os.path.splitext(f.lower())[1] in valid_ext]
img_files.sort()

if not img_files:
    raise RuntimeError(f"이미지 없음: {IMG_DIR}")

# ============================================================================  
# 추론 루프 (이미지 1장 -> JSON 1개)
# ============================================================================  
total_infer_ms = 0.0
processed = 0

for fname in img_files:
    img_path = os.path.join(IMG_DIR, fname)
    img = cv2.imread(img_path)
    if img is None:
        print("skip (read fail):", fname)
        continue

    # bbox 기준 해상도 통일 (요청 포맷 예시처럼 640x360 기준으로 bbox 뽑기)
    img_out = cv2.resize(img, (OUTPUT_WIDTH, OUTPUT_HEIGHT))

    # 모델 입력 전처리: 모델 입력 크기로 resize 후 RGB
    inp = cv2.cvtColor(cv2.resize(img_out, (input_w, input_h)), cv2.COLOR_BGR2RGB)
    input_data = np.expand_dims(inp, axis=0).astype(np.uint8)

    # inference
    t0 = time.perf_counter()
    interpreter.set_tensor(input_details[0]["index"], input_data)
    interpreter.invoke()
    infer_ms = (time.perf_counter() - t0) * 1000.0
    print(f"[{processed+1}/{len(img_files)}] {fname} | latency: {infer_ms:.2f} ms")

    # outputs
    boxes   = interpreter.get_tensor(output_details[boxes_i]["index"])[0]      # (N,4)
    scores  = interpreter.get_tensor(output_details[scores_i]["index"])[0]     # (N,)
    classes = interpreter.get_tensor(output_details[classes_i]["index"])[0]    # (N,)
    count_v = interpreter.get_tensor(output_details[count_i]["index"])
    # count는 [1] 또는 [[1]] 형태일 수 있음
    count = int(np.array(count_v).reshape(-1)[0])

    # count까지만 사용
    boxes   = boxes[:count]
    scores  = scores[:count]
    classes = classes[:count]

    # threshold
    keep = scores >= CONFIDENCE_THRESHOLD
    boxes = boxes[keep]
    scores = scores[keep]
    classes = classes[keep]

    predictions = []
    for box, cls, score in zip(boxes, classes, scores):
        ymin, xmin, ymax, xmax = box.tolist()

        # 정규화 좌표 -> OUTPUT_WIDTH/HEIGHT 기준 픽셀 bbox (x,y,w,h)
        x = float(xmin * OUTPUT_WIDTH)
        y = float(ymin * OUTPUT_HEIGHT)
        w = float((xmax - xmin) * OUTPUT_WIDTH)
        h = float((ymax - ymin) * OUTPUT_HEIGHT)

        cid = int(cls)
        predictions.append({
            "filename": fname,
            "category_id": cid,
            "category_name": LABELS.get(cid, str(cid)),
            "bbox": [x, y, w, h],
            "score": float(score)
        })

    out_json = {
        "predictions": predictions,
        "latency_ms": float(infer_ms)
    }

    out_path = os.path.join(OUT_DIR, os.path.splitext(fname)[0] + ".json")
    with open(out_path, "w") as f:
        json.dump(out_json, f, indent=2)

    processed += 1
    total_infer_ms += infer_ms

print(f"완료 | {processed} images | avg latency_ms: {total_infer_ms/processed:.3f}")
print("saved to:", OUT_DIR)
