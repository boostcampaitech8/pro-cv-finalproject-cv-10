# 군 경계지역 CCTV 영상 품질 개선을 통한 지능형 분석 고도화

## 📜 프로젝트 개요
군 경계 지역 CCTV 영상의 화질 열화 문제를 개선하고 객체 탐지 및 보고서 생성 파이프라인을 구축하여 **군 경계 감시 업무의 자동화**를 지향하는 프로젝트입니다.

군 감시 카메라 영상에 실시간 열화 개선을 적용하여 객체 탐지 안정성을 높이며, 탐지 내용 기반의 보고서를 작성하고 구조화된 탐지 결과를 제공하는 통합된 시스템을 제시합니다.


## 🎬 데모

[[시연 영상은 이곳에서 확인하실 수 있습니다.]](https://www.youtube.com/watch?v=n9__Jga_j58)

## ✨ 주요 기능

- **🚨 객체 식별 알림**
  - 실시간 화질 개선이 적용된 감시영상에서 객체가 식별되면 사용자에게 알립니다.
  
- **📜 식별 개체에 대한 AI 보고서**
  - `HyperCLOVA X` 모델로부터 추론한, 탐지상황에 대한 세부 보고서를 제공합니다.
  
- **🗓️ 감시 기록 열람**
  - 탐지 기기, 일자 및 , 보고서를 비롯한 과거 탐지 기록을 열람합니다.
  

## 🏛️ 시스템 아키텍처
- **전체 구조** <br>

<img src="./misc/overall_pipeline.png" width="600" align="center" hspace=50>
<br><br>

- **메인 서버** <br>

<img src="./misc/main_server.png" width="600" align="center" hspace=50>
<br><br>

- **엣지 디바이스** <br>

<img src="./misc/edge_device.png" width="600" align="center" hspace=50>
<br><br>

- **웹 서버** <br>

<img src="./misc/web_server.png" width="600" align="center" hspace=50>
<br><br>


## 🔍 활용 모델 및 데이터베이스 구조

### 이미지 복원 모델

- **BioIR** <br>

<img src="./misc/bioir.png" width="600" align="center" hspace=50>
<br><br>
  
  인간 시각에서의 중심 시야와 주변 시야의 상호작용을 모사한 복합 열화 이미지 복원 모델입니다. 후술할 OneRestore와 같이 U-Net 구조를 가져 지식 증류에 유리하고 최신 이미지 복원 모델 중 높은 성능 지표를 보여 Teacher 모델로 선정했습니다.

- **OneRestore** <br>

<img src="./misc/onerestore.png" width="600" align="center" hspace=50>
<br><br>

  복합 열화 환경에서 안정적인 복원 성능을 가지고 있으면서도, 약 598만개의 파라미터로 구성된 경량 모델로 Edge Device에서의 On-Device 추론에 적합하여 Student 모델로 선정했습니다.

- **Feature 기반 지식 증류** <br>

<img src="./misc/kd.png" width="600" align="center" hspace=50>
<br><br>

  높은 이미지 복원 성능의 Teacher 모델의 지식을 Student 모델로 이식하여 On-Device 추론에 활용하기 위해, feature 기반 지식 증류를 적용했습니다. 각 모델의 최종 디코더 출력 feature를 바탕으로 계산된 distillation loss를 사용합니다.

### 객체 탐지 모델

- **YOLOv8n** <br>

<img src="./misc/yolov8.png" width="600" align="center" hspace=50>
<br><br>

Single-stage 객체 탐지 모델로서, 특히 nano 모델의 경우 실시간성을 유지하면서 작은 객체도 잘 식별하기 때문에 정확도 측면에서도 뛰어날 것이라 판단하여 선정했습니다.

- **SSD MobileNet V2** <br>

<img src="./misc/ssdMobileNet.png" width="600" align="center" hspace=50>
<br><br>

Google Coral에서 공식적으로 지원하는 객체 탐지 모델입니다. 초경량 및 저전력의 엣지 디바이스에 최적화되어 있으며 실시간성 측면에서 강점을 가져 선정했습니다.

### DB 스키마

- 객체 탐지 결과
<div align="center">

| Name | Type | Description |
| :--- | :--- | :--- |
| **created_at** | datetime | 이미지가 생성된 시각 |
| **remote_file_path** | string | 해당하는 이미지의 AWS S3 저장 경로 |
| **location_name** | string | 이미지가 촬영된 위치 |
| **client_id** | string | 이미지를 보낸 Client의 ID |
| **metadata** | json | Edge Device의 Object Detection 결과 |
| **caption** | string | HCX-005가 분석한 이미지 정보 |
| **report** | json | HCX-007가 구조화한 캡션 정보 |
</div>

- 엣지 디바이스 상태

<div align="center">

| Name | Type | Description |
| :--- | :--- | :--- |
| **client_id** | string | Edge Device의 ID |
| **status** | Bool | Edge Device 연결 여부 |
| **updated_at** | datetime | 마지막으로 Heartbeat를 보낸 시간 |
</div>

### 활용 데이터셋 명세

| Usage | Dataset | Source | Type | # Samples | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Image Restoration** | 눈, 비, 안개 등의 다양한 외부 환경 노이즈 제거를 위한 영상 데이터 | AI-Hub | Real | Train 285<br>Test 69 | - 해상 상황에서 빈번하게 발생하는 시야 저하 조건 중심 수집<br>- 영상 단위 기준으로 Train/Validation 데이터 분리 |
| **Image Restoration** | 해무/안개 CCTV 데이터 | AI-Hub | Real | Train 19<br>Test 14 | - 안개 없는(no-fog) 영상을 GT 또는 기준 영상으로 활용 (카메라 각도, 촬영 위치, 배경 유사성 고려) |
| **Image Restoration** | LMHaze (Zhang, Ruikun, et al.) | - | Real | Train 144<br>Test 48 | - 실내·실외에서 인위적으로 안개를 조성해 구축한 데이터셋<br>- 과도한 안개로 정보가 소실된 샘플과 유사 데이터는 선별적으로 제거 |
| **Image Restoration** | RESIDE-6K (Liu, Bing, et al.) | - | Synthetic | Train 3000<br>Test 331 | - 실제 영상에 Synthetic 안개를 적용해 구성한 데이터셋<br>- GT에 안개가 포함되었거나 열화 강도가 부적절한 샘플은 제거 |
| **Image Restoration** | Singapore maritime dataset (D. K. Prasad et al.) | - | Real | Train 446<br>Test 181 | - 해무가 존재하는 영상만 선별<br>- 열화의 종류를 판별하는 Embedder 학습 및 모델 테스트에 사용 |
| **Object Detection** | 군 경계 작전 환경 내 인식 데이터 | AI-Hub | Real | Train 37766<br>Test 9450 | - 객체 클래스 분포를 유지하도록 Group-Stratified Split으로 8:2 분할 |

## 테스트 결과

### Image Restoration
<div align="center">

| Model | Input Image Size | PSNR (↑) | SSIM (↑) | KD | TensorRT | FPS | Latency (ms) |
| :--- | :---: | ---: | ---: | :---: | :---: | :---: | ---: |
| **BioIR (Teacher)** | 640x360 | 30.6160 | 0.9477 | X | X | - | - |
| **OneRestore (Student)** | 640x360 | 23.2825 | 0.9118 | X | O | 6.63 ~ 6.97 | 143 ~ 150ms |
| **OneRestore KD** | 640x640 | 26.9925 | 0.8932 | O | O | 6.63 ~ 6.97 | 143 ~ 150ms |
</div>

### Object Detection
<div align="center">

| Model | Input Image Size | mAP50 | PTQ | FPS | Latency(ms) |
| --- | --- | --- | --- | --- | --- |
| YOLOv8n | 512x512 | 0.01 | X | 19~28 | 36~52 |
| YOLOv8n | 640x640 | 0.237 | X | 8.66~12.1 | 82.8~115.5 |
| YOLOv8n | 512x512 | 0.278 | O | 21.1~27.9 | 35.8~47.4 |
| YOLOv8n | 640x640 | 0.498 | O | 8.6~12.3 | 81~116 |
| SSD MobileNet V2 | 640x640 | 0.123 | O | 4~4.8 | 209.1~249.2 |
</div>

### Image Restoration → Object Detection
<div align="center">

| Restorer | Detector* | mAP50 | FPS | Latency(ms) |
| --- | --- | --- | --- | --- |
| Original | YOLOv8n | 0.313 | 9.79~12.1 | 82.7~102.1 |
| OneRestore | YOLOv8n | 0.304 | 7.84~12.1 | 82.7~127.6 |
| OneRestore KD | YOLOv8n | 0.390 | 8.77~12.1 | 82.5~114 |
</div>

### 이미지 복원 및 탐지 결과

<table style="border: none; border-collapse: collapse;">
  <tr style="border: none;">
    <td style="border: none;"><img src="./misc/res_original.png" width="250"></td>
    <td style="border: none;"><img src="./misc/res_onerestore.png" width="250"></td>
    <td style="border: none;"><img src="./misc/res_onerestoreKD.png" width="250"></td>
  </tr>
  <tr style="border: none; text-align: center;">
    <td style="border: none;"><b>Original Image</b></td>
    <td style="border: none;"><b>OneRestore</b></td>
    <td style="border: none;"><b>OneRestore + KD</b></td>
  </tr>
</table>


## 🗓️ 프로젝트 진행 일정

![timeline](./misc/timeline.png)


## 👥 Collaborators

<div align="center">

|                                                   팀원                                                    |                                 역할                                  |
| :-------------------------------------------------------------------------------------------------------: | :-------------------------------------------------------------------: |
|     도담록     |  데이터 수집 및 EDA, 메인서버 구현, DB 구현, DB 및 Clova Studio 메인 서버 연동  |
|     정현우     | 프로젝트 운영 및 테스트 설계, 이미지 복원 모델 학습, 이미지 복원 모델 Jetson Orin Nano 최적화, CCTV 모듈 개발     |
|     조예원     | 데이터 수집 및 EDA, 가상 열화 데이터 생성, 웹 서버 구축 (프론트엔드 / 백엔드), 웹 서버와 DB 연동 |
|     최중식     | 이미지 복원 모델 학습, 이미지 복원 모델 경량화 및 테스트, 가상 열화 데이터 생성  |
|     최진우     | 객체 인식 모델 학습, 객체 인식 모델 추론 최적화, CCTV 모듈 개발  |


</div>

## 🛠️ Tech Stack

<div align="center">
<img src="https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white"> 
<img src="https://img.shields.io/badge/pytorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white">
<img src="https://img.shields.io/badge/opencv-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white"> 
<img src="https://img.shields.io/badge/jetson-76B900?style=for-the-badge&logo=nvidia&logoColor=white"> 
<img src="https://img.shields.io/badge/tensorrt-76B900?style=for-the-badge&logo=nvidia&logoColor=white">
<img src="https://img.shields.io/badge/google coral-4285F4?style=for-the-badge&logo=google&logoColor=white"> 
<img src="https://img.shields.io/badge/litert-4285F4?style=for-the-badge&logo=google&logoColor=white">  
<img src="https://img.shields.io/badge/fastapi-009688?style=for-the-badge&logo=fastapi&logoColor=white"> 
<img src="https://img.shields.io/badge/aws-252F3E?style=for-the-badge&logo=aws&logoColor=white"> 
<img src="https://img.shields.io/badge/react-61DAFB?style=for-the-badge&logo=react&logoColor=white"> 
<img src="https://img.shields.io/badge/mongoDB-47A248?style=for-the-badge&logo=mongodb&logoColor=white"> 
<img src="https://img.shields.io/badge/CLOVA STUDIO-03C75A?style=for-the-badge&logo=naver&logoColor=white"> 



</div>

## 👨‍🔬 References

-  (주)미디어그룹사람과숲(AI Hub 공개), 눈, 비, 안개 등의 다양한 외부 환경 노이즈 제거를 위한 영상 데이터, 2021
-  (주)유에스티21(AI Hub 공개), 해무/안개 cctv데이터, 2021
-  (주)흥일기업(AI Hub 공개), 군 경계 작전 환경 내 인식 데이터, 2024
-  Singapore maritime Dataset, Prasad, Dilip K., et al. "Video processing from electro-optical sensors for object detection and tracking in a maritime environment: A survey." *IEEE Transactions on Intelligent Transportation Systems* 18.8 (2017): 1993-2016."
-  LMHaze Dataset, Zhang, Ruikun, et al. "Lmhaze: intensity-aware image dehazing with a large-scale multi-intensity real haze dataset." *Proceedings of the 6th ACM International
Conference on Multimedia in Asia*. 2024."
-  RESIDE6K, Liu, Bing, et al. "Residual-based Efficient Bidirectional Diffusion Model for Image Dehazing and Haze Generation." *2025 IEEE International Conference on Multimedia
and Expo (ICME)*. IEEE, 2025."
-  Guo, Yu, et al. "Onerestore: A universal restoration framework for composite degradation." *European conference on computer vision*. Cham: Springer Nature Switzerland, 2024."
-  Cui, Yuning, Wenqi Ren, and Alois Knoll. "Bio-Inspired Image Restoration." *The Thirty-ninth Annual Conference on Neural Information Processing Systems*. "
-  Sandler, Mark, et al. "Mobilenetv2: Inverted residuals and linear bottlenecks." Proceedings of the IEEE conference on computer vision and pattern recognition. 2018."
-  Redmon, Joseph, et al. "You only look once: Unified, real-time object detection." Proceedings of the IEEE conference on computer vision and pattern recognition. 2016."
-  Jocher, Glenn, et al. Ultralytics YOLO Version 8, Ultralytics, 2023, https://platform.ultralytics.com/ultralytics/yolov8
-  Zhang, Yifu, et al. "Bytetrack: Multi-object tracking by associating every detection box." *European conference on computer vision*. Cham: Springer Nature Switzerland, 2022."
-  Jacob, Benoit, et al. "Quantization and training of neural networks for efficient integer-arithmetic-only inference." Proceedings of the IEEE conference on computer vision and pattern recognition. 2018.


