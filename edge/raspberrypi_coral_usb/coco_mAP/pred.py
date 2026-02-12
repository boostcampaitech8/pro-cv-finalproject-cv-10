import cv2
import numpy as np
import time
import os
import json
import tflite_runtime.interpreter as tflite

# ---------------------------
# 경로 설정
# ---------------------------
INPUT_DIR = '/home/raspberrypi/Desktop/boonseok/OneRestoreKD'     # 평가할 이미지 폴더
OUTPUT_DIR = '/home/raspberrypi/Desktop/boonseok/pred_onekd'  # 이미지별 pred json 저장
os.makedirs(OUTPUT_DIR, exist_ok=True)

model_path = '/home/raspberrypi/boostcamp/8n_calib_640_full_integer_quant_edgetpu.tflite'
delegate_path = '/usr/lib/aarch64-linux-gnu/libedgetpu.so.1'

labels = {0: "fishing_ship", 1: "merchant_ship", 2: "navy_ship", 3: "person", 4: "seabird", 5:"ship_etc/none"}
# ---------------------------
# Edge TPU 초기화
# ---------------------------
interpreter = tflite.Interpreter(
    model_path=model_path,
    experimental_delegates=[tflite.load_delegate(delegate_path)]
)
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

h, w = input_details[0]['shape'][1], input_details[0]['shape'][2]
scales = input_details[0]['quantization_parameters']['scales']
zero_points = input_details[0]['quantization_parameters']['zero_points']
out_scale = output_details[0]['quantization_parameters']['scales'][0]
out_zero = output_details[0]['quantization_parameters']['zero_points'][0]

# ---------------------------
# NMS 함수
# ---------------------------
def iou(box1, box2):
    # box: [cx, cy, w, h] (normalized)
    w_ = (box1[2] + box2[2]) / 2 - abs(box1[0] - box2[0])
    h_ = (box1[3] + box2[3]) / 2 - abs(box1[1] - box2[1])
    if w_ <= 0 or h_ <= 0:
        return 0.0
    inter = w_ * h_
    union = box1[2] * box1[3] + box2[2] * box2[3] - inter
    return inter / union if union > 0 else 0.0

def nms(bboxes, iou_threshold=0.1, threshold=0.1):
    # bboxes shape assumed [1, N, (4+num_classes)] or similar → squeeze+transpose로 N개 박스
    bboxes = np.transpose(np.squeeze(bboxes))
    # x = [cx,cy,w,h,cls_scores...]
    bboxes = [[float(np.max(x[4:])), int(np.argmax(x[4:]))] + list(map(float, x[:4]))
              for x in bboxes if float(np.max(x[4:])) > threshold]
    bboxes.sort(reverse=True)  # conf 내림차순
    result = []
    while bboxes:
        box = bboxes.pop(0)
        # 같은 class끼리만 NMS (네 로직 유지)
        bboxes = [b for b in bboxes if box[1] != b[1] or iou(box[2:], b[2:]) < iou_threshold]
        result.append(box)
    return result

# ---------------------------
# 이미지 폴더 처리
# ---------------------------
image_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
image_files.sort()

total = 0
for img_name in image_files:
    img_path = os.path.join(INPUT_DIR, img_name)
    frame = cv2.imread(img_path)
    if frame is None:
        print(f"⚠️ Failed to load {img_path}")
        continue

    frame_h, frame_w = frame.shape[:2]

    # 전처리 (네 방식 유지)
    frame_resized = cv2.resize(frame, (w, h))
    img_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
    img_float = img_rgb.astype(np.float32) / 255.0
    img_int8 = np.round(img_float / scales + zero_points).astype(np.int8)
    input_img = np.expand_dims(img_int8, axis=0)

    # 추론
    start_inf = time.perf_counter()
    interpreter.set_tensor(input_details[0]['index'], input_img)
    interpreter.invoke()
    latency_ms = (time.perf_counter() - start_inf) * 1000

    # 출력 디퀀트
    result_int8 = interpreter.get_tensor(output_details[0]['index'])
    result = (result_int8.astype(np.float32) - out_zero) * out_scale

    detections = nms(result, iou_threshold=0.1, threshold=0.1)

    # ---------------------------
    # ✅ 이미지별 pred json 저장 (COCO prediction 형식)
    # ---------------------------
    preds = []
    for conf, cls_id, cx, cy, bw, bh in detections:
        # 네 모델 출력이 normalized(cx,cy,w,h) 라는 가정 그대로 사용
        x = (cx - bw / 2) * frame_w
        y = (cy - bh / 2) * frame_h
        ww = bw * frame_w
        hh = bh * frame_h

        preds.append({
            "filename": img_name,
            "category_id": int(cls_id),
            "category_name": labels.get(int(cls_id), str(cls_id)),
            "bbox": [float(x), float(y), float(ww), float(hh)],  # [x,y,w,h] pixel
            "score": float(conf)
        })

    out_json = os.path.join(OUTPUT_DIR, os.path.splitext(img_name)[0] + ".json")
    with open(out_json, "w") as f:
        json.dump({"predictions": preds, "latency_ms": latency_ms}, f, indent=2)

    print(f"✅ {img_name} -> {len(preds)} det, {latency_ms:.1f} ms, saved: {out_json}")
    total += 1

print(f"🎉 Finished. processed images: {total}, pred json dir: {OUTPUT_DIR}")
