# EDGE (Raspberrypi4B + Google Coral USB Accelerator)



Edge to Edge, Edge to Server 파이프라인 구현과 edgetpu.tflite 모델의 coco mAP를 구하는 코드들이 포함되어있다.



## Folder Structure

```
├─ raspberrypi_coral_usb
│    └── coco_mAP
│        ├── check_match.py  # 예측 결과가 이미지에 잘 매칭되는지 확인
│        ├── coco_base_map50_cal.py  # GT json과 pred json을 이용해서 coco 형식의 mAP 계산
│        ├── make_gt.py  # GT json 생성
│        ├── main_pred_json.py  # 각 이미지마다의 pred 결과 json을 하나로 합침
│        ├── pred_ssd.py  # SSD MobileNet V2의 TFLite 모델 이용한 각 이미지마다의 예측 결과 JSON 생성
│        ├── pred.py # YOLOv8n의 TFLite 모델 이용한 각 이미지마다의 예측 결과 JSON 생성
│    ├── main_ssd-mobilenet-v2.py  # SSD MobileNet V2의 TFLite 모델 이용한 Edge to Edge, Edge to Server 파이프라인
│    ├── main_yolov8n.py  # YOLOv8n의 TFLite 모델 이용한 Edge to Edge, Edge to Server 파이프라인
│    └── raspi_detection_sender.py  # Edge to Edge, Edge to Server 파이프라인에서 서버 전송 관련 모듈
```


## Edge to Edge, Edge to Server 파이프라인
Jetson Orin Nano 측에서 TCP 통신으로 라즈베리파이로 복원된 이미지를 보내면 복원된 이미지에 대해서 Google Coral USB Accelerator가 추론을 진행한다.
추론 결과를 JSON형식으로 나타내며 다음과 같다.
```
{annotations:
	[
	  {
	    "class": 1,
	    "confidence": 0.9499, #4자리 반올림
	    "bbox": [
		    x, # 왼쪽 끝
		    y, # 위쪽 끝
		    w,
		    h
	    ]
	  }
	]
	latitude: 0 
	longitude: 0
	weather: 0 
	time: 0
}
```
이렇게 복원된 이미지와 JSON형식의 annotation data를 서버로 HTTP 통신으로 보내게 된다.
