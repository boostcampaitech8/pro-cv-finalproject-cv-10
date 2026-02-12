import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit  # 반드시 필요
import numpy as np
import cv2
import time

'''
특징
1. 동적 생성
- 입력/출력 텐서 이름과 shape를 engine에서 읽어와서 자동으로 GPU 메모리를 할당함.
- engine.num_io_tensors, engine.get_tensor_name(i) 등으로 동적으로 처리 가능.
2. 자동 관리
- 어떤 입력/출력이 있든 반복문으로 처리.
- Tensor 이름, shape, dtype를 engine에서 가져오므로 engine 구조가 바뀌어도 코드를 크게 안 바꿔도 됨.
3. Host & Device 메모리 쌍 생성
- 입력/출력마다 host (CPU)와 device (GPU)를 생성해서 memcpy 사용 가능.
4. bindings 리스트
- 사실 TensorRT 10.x에서는 필요 없음 (execute_async_v3는 set_tensor_address 기반임).

장점: 여러 입력/출력이 있을 때 확장성 좋음.
단점: 코드가 조금 복잡하고, 불필요한 bindings 리스트 사용.
'''

# ================================
# TensorRT Logger
# ================================
TRT_LOGGER = trt.Logger(trt.Logger.INFO)

# ================================
# Engine Loader
# ================================
def load_engine(engine_path):
    with open(engine_path, "rb") as f, trt.Runtime(TRT_LOGGER) as runtime:
        return runtime.deserialize_cuda_engine(f.read())

def allocate_buffers(engine, context):
    inputs = {}
    outputs = {}
    bindings = []
    stream = cuda.Stream()

    for i in range(engine.num_io_tensors):
        name = engine.get_tensor_name(i)
        dtype = trt.nptype(engine.get_tensor_dtype(name))
        shape = context.get_tensor_shape(name)
        size = trt.volume(shape)

        host_mem = cuda.pagelocked_empty(size, dtype=dtype)
        device_mem = cuda.mem_alloc(host_mem.nbytes)

        bindings.append(int(device_mem))

        if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
            inputs[name] = {'host': host_mem, 'device': device_mem}
        else:
            outputs[name] = {'host': host_mem, 'device': device_mem}

    # Ensure the input tensor address is set before inference
    for name, inp in inputs.items():
        context.set_tensor_address(name, int(inp['device']))  # Set the address of the input tensor

    for name, inp in outputs.items():
        context.set_tensor_address(name, int(inp['device']))  # Set the address of the input tensor

    return inputs, outputs, bindings, stream

def do_inference(context, bindings, inputs, outputs, stream):
    # Host → Device
    for name, inp in inputs.items():  # 수정: name과 inp으로 변경
        cuda.memcpy_htod_async(inp['device'], inp['host'], stream)

    # setInputTensorAddress

    # Execute
    context.execute_async_v3(stream_handle=stream.handle)#, bindings=bindings)

    # Device → Host
    for name, out in outputs.items():  # 수정: name과 out으로 변경
        cuda.memcpy_dtoh_async(out['host'], out['device'], stream)

    stream.synchronize()
    return {name: out['host'] for name, out in outputs.items()}


def preprocess_image(img_path):
    img = cv2.imread(img_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (640, 360))  # W x H

    img = img.astype(np.float32) / 255.0

    # mean = np.array([0.485, 0.456, 0.406])
    # std  = np.array([0.229, 0.224, 0.225])
    # img = (img - mean) / std

    img = np.transpose(img, (2, 0, 1))  # HWC → CHW
    img = np.expand_dims(img, axis=0)   # (1,3,360,640)

    return img

ENGINE_PATH = "embedder_fp16.engine"
IMAGE_PATH = "1.png"

# Load engine
engine = load_engine(ENGINE_PATH)
context = engine.create_execution_context()
context.set_input_shape("image", (1, 3, 360, 640))

# Allocate buffers
inputs, outputs, bindings, stream = allocate_buffers(engine,  context)

# Preprocess image
img = preprocess_image(IMAGE_PATH)
inputs["image"]["host"][:] = img.ravel()

# Inference
t0 = time.time()
output = do_inference(context, bindings, inputs, outputs, stream)
t1 = time.time()

# Output embedding
embedding = output['embedding'].reshape(1, -1)


latency = (t1 - t0) / 1 * 1000
fps = 1000 / latency

print(f"Latency: {latency:.2f} ms")
print(f"FPS: {fps:.2f}")
