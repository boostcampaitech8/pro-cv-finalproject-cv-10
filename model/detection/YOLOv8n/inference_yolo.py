from ultralytics import YOLO
import os

model = YOLO('C:/Users/user/Desktop/workspace/best.pt') 

valid_img_path = 'C:/Users/user/Desktop/bioir+degraded&restored(haze)/restored_h/2.png'
results = model.predict(
    source=valid_img_path, 
    save=True,
    conf=0.4, # 신뢰도 임계값
    project='restored_h',
    name='inference_results'
)

print(f"prediction complete")