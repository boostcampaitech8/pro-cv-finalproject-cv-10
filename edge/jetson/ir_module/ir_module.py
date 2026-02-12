from .embedder import *
from .restorer import *

class IRModule():
    def __init__(self):
        d_img = self.alloc(CONST_TUPLE_IMAGE)
        d_embed = self.alloc(CONST_TUPLE_EMBED)
        d_out = self.alloc(CONST_TUPLE_RESTO)
        self.embedder = Embedder(d_img, d_embed)
        self.restorer = Restorer(d_img, d_embed, d_out)
    
    def load_engine(self, embeder_path, restorer_path):
        self.embedder.load_engine(embeder_path)
        self.restorer.load_engine(restorer_path)
    
    def set_context(self):
        self.embedder.set_context()
        self.restorer.set_context()

    def infer(self, img, stream):
        embed = self.embedder.infer(img, stream)
        out = self.restorer.infer(img, embed, stream)
        return out

    def alloc(self, shape):
        return cuda.mem_alloc(int(np.prod(shape) * np.float32().nbytes))