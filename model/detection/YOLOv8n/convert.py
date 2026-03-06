from ultralytics import YOLO

model = YOLO("C:/Users/user/Desktop/workspace/8nv1-1_640.pt")

model.export(
    format="edgetpu", 
    data="C:/Users/user/Desktop/workspace/datasetV1-1/data.yaml", 
    imgsz=640
)