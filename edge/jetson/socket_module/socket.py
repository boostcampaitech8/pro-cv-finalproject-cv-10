import socket

class SocketModule():
    def __init__(self):
        # self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def set_address(self, ip:str, port:int):
        self.address = (ip, port)
        print(self.address)
        self.connect()

    def connect(self):
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(self.address)

    def send(self, data):
        # self.sock.sendto(data.tobytes(), self.address)
        # self.sock.sendall(data.tobytes())
        # print(f'[Socket Module] send data')#: {data.tobytes()}')
        try:
            self.connect()
            self.sock.sendall(data.tobytes())
        except (socket.error, ConnectionResetError) as e:
            print(f"❌ Socket error: {e}")
            # 재연결 시도
            self.sock.close()
            self.sock = None
            self.connect()
            self.sock.sendall(data.tobytes())

    def release(self):
        self.sock.close()

if __name__ == '__main__':
    so = SocketModule()
    so.set_address('172.16.20.249', 12345)
    so.send(np.random.randint(0, 256, size=(640, 360), dtype=np.uint8))