import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit  # 반드시 필요
import numpy as np
import cv2
import time

from camera_module import CameraModule
from socket_module import SocketModule
from ir_module import IRModule
from ir_module.constants import *

# # CONST VALUE
CONST_PATH_ENGINE_EMBED = f'./embedder_float16.trt'
CONST_PATH_ENGINE_RESTORE = f'./engine/restorer_float16.trt'

CONST_STR_SOCKET_IP = ''
CONST_INT_SOCKET_PORT = 0
CONST_INT_TRIAL = 10000000

# TensorRT Logger
TRT_LOGGER = trt.Logger(trt.Logger.INFO)

def preprocess(frame):
    # BGR → RGB
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # uint8 → float32
    frame = frame.astype(np.float32) / 255.0

    # HWC → CHW
    frame = np.transpose(frame, (2, 0, 1))

    # add batch
    frame = np.expand_dims(frame, axis=0)

    # **Ensure contiguous memory**
    return np.ascontiguousarray(frame, dtype=np.float32)


def postprocess(out):
    # NCHW → HWC
    img = out[0].transpose(1, 2, 0)

    img = np.clip(img, 0, 1)

    # float → uint8
    img = (img * 255).astype(np.uint8)

    # RGB → BGR (OpenCV)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

def main():
    stream = cuda.Stream()
    
    so = SocketModule()
    so.set_address(CONST_STR_SOCKET_IP, CONST_INT_SOCKET_PORT)

    cam = CameraModule()

    ir = IRModule()
    ir.load_engine(CONST_PATH_ENGINE_EMBED, CONST_PATH_ENGINE_RESTORE)
    ir.set_context()
    
    print('=================================================================')
    print('Embedder: ')
    print('-----------------------------------------------------------------')
    print("TRT input shape:",
          ir.embedder.context.get_tensor_shape(CONST_STR_IMAGE_NAME))
    print("TRT input dtype:",
          ir.embedder.engine.get_tensor_dtype(CONST_STR_IMAGE_NAME))
    print("TRT output shape:",
          ir.embedder.context.get_tensor_shape(CONST_STR_EMBED_NAME))
    print("TRT output dtype:",
          ir.embedder.engine.get_tensor_dtype(CONST_STR_EMBED_NAME))

    print('=================================================================')
    print('Restorer: ')
    print('-----------------------------------------------------------------')
    print("TRT input shape:",
          ir.restorer.context.get_tensor_shape(CONST_STR_IMAGE_NAME))
    print("TRT input dtype:",
          ir.restorer.engine.get_tensor_dtype(CONST_STR_IMAGE_NAME))
    print("TRT input shape:",
          ir.restorer.context.get_tensor_shape(CONST_STR_EMBED_NAME))
    print("TRT input dtype:",
          ir.restorer.engine.get_tensor_dtype(CONST_STR_EMBED_NAME))
    print("TRT output shape:",
          ir.restorer.context.get_tensor_shape(CONST_STR_RESTO_NAME))
    print("TRT output dtype:",
          ir.restorer.engine.get_tensor_dtype(CONST_STR_RESTO_NAME))
    print('=================================================================')

    print("CONST_TUPLE_EMBED:", CONST_TUPLE_EMBED)
    print("CONST_TYPE_DATA:", CONST_TYPE_DATA)

    num = CONST_INT_TRIAL

    for i in range(num):
        frame = cam.read_frame()
        frame = cv2.resize(frame, (640, 360))
        cv2.imwrite(f'data/image_{time.time()}.jpg', frame)
        
        img_input = preprocess(frame)
        t0 = time.time()
        out = ir.infer(img_input, stream)
        t1 = time.time()

        latency = (t1 - t0) / 1 * 1000
        fps = 1000 / latency

        print(f"Latency: {latency:.2f} ms")
        print(f"FPS: {fps:.2f}")

        out_img = postprocess(out)

        so.send(out_img)
        print(f'Success send image {out_img.shape}')

    cam.release()

if __name__ == '__main__':
    main()