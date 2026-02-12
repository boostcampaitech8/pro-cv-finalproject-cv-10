import cv2
import numpy as np
from datetime import datetime

class CameraReadError(Exception):
    pass

class CameraModule:
    def __init__(self, cam_index:int=0, show:bool=False):
        self.cap = cv2.VideoCapture(cam_index)
        self.frame = None
        self.show = show

    def read_frame(self)->np.array:
        ret, frame = self.cap.read()
        if ret:
            self.frame = frame
            # raise CameraReadError('[Camera Module] Camera frame read failed')
        else:
            raise CameraReadError('[Camera Module] Camera frame read failed')
        # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # filename = f"frame_{timestamp}.png"
        # cv2.imwrite(filename, frame)

        if self.show:
            cv2.imshow('Camera', frame)
            # cv2.waitKey(1)

        return self.frame
    
    def release(self):
        self.cap.release()
        cv2.destroyAllWindows()

# def list_cameras(max_index=10):
#     available = []
#     for i in range(max_index):
#         cap = cv2.VideoCapture(i)
#         if cap.isOpened():
#             print(f"Camera found at index {i}")
#             available.append(i)
#             cap.release()
#     if not available:
#         print("No cameras detected")
#     return available

# cams = list_cameras()        

if __name__ == '__main__':
    cam = CameraModule()
    frame = cam.read_frame()
    print(type(frame))
    print(frame.shape)