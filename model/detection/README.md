# Detection (Model)



Detection 파트의 2개 모델 YOLOv8n, SSD MobileNet V2.



## Folder Structure

```
├─ YOLOv8n
│    ├── convert.py  # .pt형식의 YOLO모델을 edgetpu.tflite로 변환
│    ├── inference_yolo.py  # YOLO모델로 inference
│    ├── make_calibration.py  # 대표데이터 생성
│    ├── resize_img.py  # inference 시 image resize
│    └── train.py  # YOLO모델 학습
├─ SSD_MobileNet_V2
│    └── pipeline.config  # TF OD API 기반 학습 config
```



## Detection 최종 모델 선별 과정

이번 프로젝트에서의 목적은 모델의 정확성을 유지하면서 실시간성을 확보하는 것이었다.
이를 위해 실시간 객체 탐지에 적합한 SSD MobileNet V2와 YOLOv8n을 선정하여 성능을 비교하였다.
복원된 이미지에 대한 inference 결과 YOLOv8n이 객체를 더 탐지하였기 때문에 최종 모델로 선정하였다. 이후 Post Training Quantization(PTQ) 과정에서  대표데이터셋을 적용 여부에 따라 512, 640을 imgsz로 넣고 edgetpu.tflite로 변환한 총 4개의 모델을 비교한 결과 coco 형식의 mAP 기준 imgsz 640에 대표데이터셋 적용한 모델이 가장 성능이 좋았으므로 이를 최종 선별하고, restoration 모델들과의 조합을 살펴보았다.