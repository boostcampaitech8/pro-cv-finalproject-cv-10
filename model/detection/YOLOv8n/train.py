from ultralytics import YOLO
import os 

def main(): 
    data_yaml_path = "datasetV1-1/data.yaml" 
    model = YOLO("yolov8n.pt") 
    model.train( 
        data=data_yaml_path, 
        imgsz=512, 
        rect=True, 
        epochs=50, 
        batch=32, 
        device=0, 
        project="final", 
        name="yolo8n_v5", 
        exist_ok=True 
    ) 
    
if __name__ == "__main__": 
    main()