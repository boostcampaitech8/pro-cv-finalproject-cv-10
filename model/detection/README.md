# Detection (Model)



Detection 파트의 2개 모델 YOLOv8n, SSD MobileNet V2.



## Folder Structure

├─ YOLOv8n
     ├── convert.py  # .pt형식의 YOLO모델을 edgetpu.tflite로 변환
     ├── inference_yolo.py  # YOLO모델로 inference
     ├── make_calibration.py  # edgetpu.tflite로 변환 시 사용할 대표데이터 생성
     ├── resize_img.py  # inference 시 image resize
     └── train.py  # YOLO모델 학습
├─ SSD_MobileNet_V2
     └── pipeline.config # Tensorflow Object Detection API 기반 학습 시 사용한 config파일



## Detection 최종 모델 선별 과정

이번 프로젝트에서의 목적은 모델의 정확성을 유지하면서 실시간성을 추구하는 것이었다.
그래서 실시간성 detection모델로 뛰어난 SSD MobileNet V2와 YOLOv8n을 선정하였다.
SSD MobileNet V2와 YOLOv8n의 모델로 복원된 이미지에 대한 inference 결과, YOLOv8n이 객체를 더 탐지하는 모습이었다.
그래서 YOLOv8n을 최종 모델로 선정하였고, Post Training Quantization(PTQ) 시 대표데이터셋을 넣는지에 따라서 512, 640을 imgsz로 넣고 edgetpu.tflite로 변환한 결과 
coco 형식의 mAP 기준 imgsz 640에 대표데이터셋 적용한 모델이 가장 성능이 좋았으므로 이를 최종 선별하고, restoration 모델들과의 조합을 살펴보았다.