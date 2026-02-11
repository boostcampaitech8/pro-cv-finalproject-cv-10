from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

GT_JSON   = "/home/raspberrypi/Desktop/boonseok/gt_coco.json"
PRED_JSON = "/home/raspberrypi/Desktop/boonseok/predictions_2_512_coco.json"

coco_gt = COCO(GT_JSON)
coco_dt = coco_gt.loadRes(PRED_JSON)

e = COCOeval(coco_gt, coco_dt, "bbox")
e.evaluate()
e.accumulate()
e.summarize()   # 반드시 먼저 실행

map50 = e.stats[1]      # AP@0.50
map5095 = e.stats[0]    # AP@0.50:0.95

print(f"\n✅ mAP50 (AP@0.50): {map50:.3f}")
print(f"✅ mAP50-95 (AP@0.50:0.95): {map5095:.3f}")
