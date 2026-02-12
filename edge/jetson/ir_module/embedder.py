import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit  # 반드시 필요
import numpy as np

from .constants import *

TRT_LOGGER = trt.Logger(trt.Logger.INFO)

class Embedder():
    def __init__(self, d_img=CONST_TUPLE_IMAGE, d_out=CONST_TUPLE_EMBED):
        self.d_img = d_img
        self.d_out = d_out

    def load_engine(self, engine_path):
        with open(engine_path, "rb") as f, trt.Runtime(TRT_LOGGER) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())

        self.context = self.engine.create_execution_context()
    
    def set_context(self):
        self.context.set_input_shape(CONST_STR_IMAGE_NAME, CONST_TUPLE_IMAGE)
        
        self.context.set_tensor_address(CONST_STR_IMAGE_NAME, int(self.d_img))
        self.context.set_tensor_address(CONST_STR_EMBED_NAME, int(self.d_out))

    def infer(self, img, stream):
        cuda.memcpy_htod_async(self.d_img, img, stream)
        self.context.execute_async_v3(stream.handle)
        out = np.empty(CONST_TUPLE_EMBED, dtype=CONST_TYPE_DATA)
        cuda.memcpy_dtoh_async(out, self.d_out, stream)
        stream.synchronize()
        return out