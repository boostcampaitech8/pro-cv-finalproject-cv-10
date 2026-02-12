import os
import cv2
import time
import threading

import tensorrt as trt
import pycuda.driver as cuda

from camera_module import CameraModule
from socket_module import SocketModule
from ir_module import IRModule
from ir_module.constants import *

VIDEO_PATH = "./source/MVI_1451_VIS_Haze.avi"   # 동영상 경로
WINDOW_NAME = "Live Stream (Drop Old Frames)"

CONST_PATH_ENGINE_EMBED = './engine/embedder_float16.trt'
CONST_PATH_ENGINE_RESTORE = './engine/restorer_kd_float16.trt'
TRT_LOGGER = trt.Logger(trt.Logger.INFO)

CONST_STR_SOCKET_IP = ''
CONST_INT_SOCKET_PORT = 0

CONST_PATH_OUTPUT = os.path.join('./demo', os.path.splitext(os.path.basename(VIDEO_PATH))[0])
os.makedirs(os.path.join(CONST_PATH_OUTPUT, 'input'), exist_ok=True)
os.makedirs(os.path.join(CONST_PATH_OUTPUT, 'result'), exist_ok=True)
# =============================
# 전역 상태
# =============================
latest_frame = None
lock = threading.Lock()
stop_flag = False

# =============================
# 프레임 읽기 스레드 (Producer)
# =============================
def frame_reader():
    global latest_frame, stop_flag

    cap = cv2.VideoCapture(VIDEO_PATH)

    if not cap.isOpened():
        print("❌ Video open failed")
        stop_flag = True
        return

    while not stop_flag:
        ret, frame = cap.read()
        if not ret:
            stop_flag = True
            break

        with lock:
            latest_frame = frame

    cap.release()


# =============================
# 추론 + 출력 스레드 (Consumer)
# =============================
def infer_and_display():
    global latest_frame, stop_flag

    import pycuda.driver as cuda
    cuda.init()

    device = cuda.Device(0)
    cuda_ctx = device.make_context()

    try:
        stream = cuda.Stream()
        ir = IRModule()
        ir.load_engine(CONST_PATH_ENGINE_EMBED, CONST_PATH_ENGINE_RESTORE)
        ir.set_context()

        while not stop_flag:
            with lock:
                frame = latest_frame

            if frame is None:
                time.sleep(0.001)
                continue

            start = time.time()
            # preprocess
            frame = cv2.resize(frame, (640, 360))
            img_input = preprocess(frame)

            # inference
            t0 = time.time()
            out = ir.infer(img_input, stream)
            t1 = time.time()

            latency = (t1 - t0) * 1000
            fps = 1000 / latency

            out_img = postprocess(out)

            so.send(out_img)

            infer_time = time.time() - start
            print(f"Model Infer: {latency:.2f} ms / Model FPS: {fps:.2f} / Preprocess: {(t0-start) * 1000:.2f} ms / Postprocess: {(infer_time - (t1 - start)) * 1000:.2f} ms / Total Latency: {infer_time*1000:.2f} ms / Total FPS: {(1 / infer_time):.2f}")
    
    finally:
        cuda_ctx.pop()
    cv2.destroyAllWindows()

def preprocess(frame):
    # BGR → RGB
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # uint8 → float16
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

so = SocketModule()
so.set_address(CONST_STR_SOCKET_IP, CONST_INT_SOCKET_PORT)

reader_thread = threading.Thread(target=frame_reader, daemon=True)
infer_thread = threading.Thread(target=infer_and_display, daemon=True)

reader_thread.start()
infer_thread.start()

infer_thread.join()
stop_flag = True
reader_thread.join()

print("✅ 종료")
