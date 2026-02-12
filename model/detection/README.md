# Detection

Detection 파트에서 사용된 모델은 YOLOv8n과 SSD MobileNet V2이다.

## Folder Structure
```
├─ YOLOv8n
│    ├── convert.py  # .pt 형식 YOLO 모델을 EdgeTPU TFLite로 변환
│    ├── inference_yolo.py  # YOLO 모델 inference
│    ├── make_calibration.py  # PTQ용 대표데이터 생성
│    ├── resize_img.py  # inference 전 이미지 resize
│    └── train.py  # YOLO 모델 학습
├─ SSD_MobileNet_V2
│    └── pipeline.config  # TF OD API 기반 학습 config
```
## Framework
SSD MobileNet V2의 경우 Tensorflow Object Detection API를 기반으로 학습하였다.
YOLOv8n 모델의 경우 Ultralytics YOLO framework를 기반으로 학습하였다.

## Detection 최종 모델 선별 과정
Detection 파트의 목적은 정확도를 유지하면서 실시간성을 확보하는 것이다. 이를 위해 실시간 객체 탐지에 적합한 SSD MobileNet V2와 YOLOv8n을 선정하여 성능을 비교하였다.
복원된 이미지에 대한 inference 결과 YOLOv8n이 더 많은 객체를 탐지하는 성능을 보였으며, Post Training Quantization(PTQ) 과정에서 대표 데이터셋을 적용 여부와 imgsz 512, 640에 따라 4개의 EdgeTPU TFLite 모델을 생성하였다.
그 결과, 대표데이터셋을 적용한 imgsz 640 모델이 COCO mAP 기준 가장 높은 성능을 보여 해당 모델을 최종 detection 모델로 선정하고 restoration 모델과의 조합 성능을 분석하였다.