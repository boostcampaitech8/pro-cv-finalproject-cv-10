import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit
import numpy as np
import time

TRT_LOGGER = trt.Logger(trt.Logger.INFO)

def load_engine(engine_path):
    with open(engine_path, "rb") as f, trt.Runtime(TRT_LOGGER) as runtime:
        return runtime.deserialize_cuda_engine(f.read())

engine = load_engine("onerestore.trt")
context = engine.create_execution_context()

# input shapes
img_shape = (1, 3, 512, 512)
embed_shape = (1, 324)
output_shape = (1, 3, 512, 512)

# # allocate buffers
# d_img = cuda.mem_alloc(np.prod(img_shape) * np.float16().nbytes)
# d_embed = cuda.mem_alloc(np.prod(embed_shape) * np.float16().nbytes)
# d_out = cuda.mem_alloc(np.prod(output_shape) * np.float16().nbytes)

img_nbytes   = int(np.prod(img_shape)) * np.dtype(np.float16).itemsize
embed_nbytes = int(np.prod(embed_shape)) * np.dtype(np.float16).itemsize
out_nbytes   = int(np.prod(output_shape)) * np.dtype(np.float16).itemsize

d_img   = cuda.mem_alloc(img_nbytes)
d_embed = cuda.mem_alloc(embed_nbytes)
d_out   = cuda.mem_alloc(out_nbytes)

bindings = [int(d_img), int(d_embed), int(d_out)]
stream = cuda.Stream()

def infer(img, embed):
    cuda.memcpy_htod_async(d_img, img, stream)
    cuda.memcpy_htod_async(d_embed, embed, stream)

    context.execute_async_v3(stream.handle)

    out = np.empty(output_shape, dtype=np.float16)
    cuda.memcpy_dtoh_async(out, d_out, stream)
    stream.synchronize()
    return out

# warmup
img = np.random.rand(*img_shape).astype(np.float16)
embed = np.random.rand(*embed_shape).astype(np.float16)
for _ in range(10):
    infer(img, embed)

# benchmark
N = 100
t0 = time.time()
for _ in range(N):
    infer(img, embed)
t1 = time.time()

latency = (t1 - t0) / N * 1000
fps = 1000 / latency

print(f"Latency: {latency:.2f} ms")
print(f"FPS: {fps:.2f}")
