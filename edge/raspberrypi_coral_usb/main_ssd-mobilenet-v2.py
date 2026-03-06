import cv2
import numpy as np
import time
import socket
import os
import json
import queue
from threading import Thread
import tflite_runtime.interpreter as tflite
from raspi_detection_sender import DetectionSender

"""
서버 업로드 동안 다음 프레임 받을 수 없음 -> 네트워크 느리면 전체 파이프라인 멈추고 FPS 크게 감소
=> Queue 사용하여 비동기 처리, 처리속도 보장, 버퍼 역할.
bytearray(size)로 필요 크기 미리 할당, memoryview로 메모리 직접 접근, recv_into()로 기존 버퍼에 직접 쓰고
정확히 size만큼 받을 때까지 대기.

edge
-allocate_tensors로 메모리 미리 할당
-매 프레임마다 배열 재사용->메모리 할당, 해제 오버헤드 제거

socket
- nagle 알고리즘 제거 -> 실시간 영상 전송에 불리하기 때문.
"""

# =======Configs=======
# Socket server 
HOST = ''
PORT = 12345
IMG_SIZE = 640 * 360 * 3

# Model
model_path = '/home/raspberrypi/Desktop/workspace/ssd_mobilenet_v2_edgetpu.tflite'
delegate_path = '/usr/lib/aarch64-linux-gnu/libedgetpu.so.1'

# Detection
labels = {0: "fishing_ship", 1: "merchant_ship", 2: "navy_ship", 3: "person", 4: "algae"}
CONFIDENCE_THRESHOLD = 0.01

# Server upload
url_server = ""
CLIENT_ID = "Coral_01"
HEARTBEAT_INTERVAL = 15

# Raspberry Pi optimization settings
SOCKET_BUFFER_SIZE = 65536  # 64KB socket buffer
UPLOAD_QUEUE_SIZE = 10 
NUM_UPLOAD_WORKERS = 1 
JPEG_QUALITY = 85
DISPLAY_ENABLED = False


# Initialize Detection Sender
sender = DetectionSender(client_id=CLIENT_ID, server_url=url_server)
sender.start_heartbeat(interval=HEARTBEAT_INTERVAL)

# Upload queue with worker thread
upload_queue = queue.Queue(maxsize=UPLOAD_QUEUE_SIZE)

def upload_worker():
    """Background thread for uploading detection results to server"""
    while True:
        item = upload_queue.get()
        if item is None:
            break
        
        annotations, img_bytes, timestamp = item
        try:
            sender.upload(
                annotations=annotations,
                image_bytes=img_bytes,
                timestamp=timestamp,
                latitude=0,
                longitude=0,
                weather=0
            )
        except Exception as e:
            print(f"[UPLOAD ERROR] {e}")
        finally:
            upload_queue.task_done()

# Start upload worker thread
upload_thread = Thread(target=upload_worker, daemon=True)
upload_thread.start()
print("[UPLOAD] Worker thread started")


# Socket receive helper (optimized)
def recv_exact(sock, size):
    """Receive exact number of bytes from socket with optimized buffering"""
    buf = bytearray(size)
    view = memoryview(buf)
    pos = 0
    
    while pos < size:
        n = sock.recv_into(view[pos:], size - pos)
        if n == 0:
            return None
        pos += n
    
    return bytes(buf)


# Initialize Edge TPU
try:
    interpreter = tflite.Interpreter(
        model_path=model_path,
        experimental_delegates=[tflite.load_delegate(delegate_path)]
    )
    interpreter.allocate_tensors()
    print("[TPU] Edge TPU loaded successfully")
except Exception as e:
    print(f"[TPU ERROR] Failed to load Edge TPU: {e}")
    exit()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
h, w = input_details[0]['shape'][1], input_details[0]['shape'][2]
print(f"[TPU] Model input size: {w}x{h}")

input_buffer = np.zeros((1, h, w, 3), dtype=np.uint8)


# Start Socket Server
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUFFER_SIZE)
server.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
server.bind((HOST, PORT))
server.listen(1)

print(f"[Jetson] Listening on {HOST}:{PORT}")
print(f"[Jetson] Socket buffer: {SOCKET_BUFFER_SIZE} bytes")
print(f"[Jetson] Display: {'Enabled' if DISPLAY_ENABLED else 'Disabled'}")
print(f"[Jetson] Ready to receive images and perform detection")

try:
    while True:
        print("\n[WAIT] Waiting for client connection...")
        conn, addr = server.accept()
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUFFER_SIZE)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"[CONNECTED] Client connected: {addr}")
        
        frame_id = 0
        fps_counter = []
        last_fps_print = time.time()

        try:
            while True:
                frame_start = time.time()
                
                # Receive image data
                img_data = recv_exact(conn, IMG_SIZE)
                if img_data is None:
                    print("Client disconnected")
                    break
                
                # Reconstruct frame
                frame = np.frombuffer(img_data, dtype=np.uint8).reshape((360, 640, 3))
                
                cv2.resize(frame, (w, h), dst=input_buffer[0], interpolation=cv2.INTER_LINEAR)
                cv2.cvtColor(input_buffer[0], cv2.COLOR_BGR2RGB, dst=input_buffer[0])
                
                # Inference
                start_inf = time.perf_counter()
                interpreter.set_tensor(input_details[0]['index'], input_buffer)
                interpreter.invoke()
                latency = (time.perf_counter() - start_inf) * 1000
                
                # Parse detection results
                boxes = interpreter.get_tensor(output_details[1]['index'])[0]
                classes = interpreter.get_tensor(output_details[3]['index']).flatten()
                scores = interpreter.get_tensor(output_details[0]['index']).flatten()
                
                current_annotations = []
                detected_count = 0
                
                for i in range(len(scores)):
                    if scores[i] > CONFIDENCE_THRESHOLD:
                        class_id = int(classes[i])
                        ymin, xmin, ymax, xmax = boxes[i]
                        
                        # Convert coordinates to 640x360
                        left = int(xmin * 640)
                        top = int(ymin * 360)
                        right = int(xmax * 640)
                        bottom = int(ymax * 360)
                        
                        detected_count += 1
                        
                        current_annotations.append({
                            "class": class_id,
                            "label": labels.get(class_id, "unknown"),
                            "confidence": round(float(scores[i]), 4),
                            "bbox": [left, top, right - left, bottom - top]
                        })


                # Upload to server (only if detections found)
                if current_annotations:
                    timestamp = int(time.time() * 1000)
                    
                    _, img_encoded = cv2.imencode('.jpg', frame, 
                                                   [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                    img_bytes = img_encoded.tobytes()
                    
                    # Add to upload queue (non-blocking)
                    try:
                        upload_queue.put_nowait((current_annotations, img_bytes, timestamp // 1000))
                        print(f"[F{frame_id:04d}] Detected: {detected_count} objects | "
                              f"Latency: {latency:.1f}ms | Queue: {upload_queue.qsize()}/{UPLOAD_QUEUE_SIZE}")
                    except queue.Full:
                        print(f"[WARN] Upload queue full, skipping frame {frame_id}")
                

                # Display
                if DISPLAY_ENABLED and current_annotations:
                    annotated_frame = frame.copy()
                    for ann in current_annotations:
                        l, t, wb, hb = ann["bbox"]
                        cv2.rectangle(annotated_frame, (l, t), (l + wb, t + hb), (0, 255, 0), 2)
                        label_text = f"{ann['label']}: {ann['confidence']:.2f}"
                        cv2.putText(annotated_frame, label_text, (l, t - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    cv2.imshow("Edge TPU Detection Monitor", annotated_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("[INFO] 'q' pressed - stopping display")
                        break
                
                frame_time = time.time() - frame_start
                fps_counter.append(1.0 / frame_time if frame_time > 0 else 0)
                
                if time.time() - last_fps_print >= 1.0:
                    avg_fps = sum(fps_counter) / len(fps_counter) if fps_counter else 0
                    print(f"[PERF] Avg FPS: {avg_fps:.1f} | Avg Latency: {latency:.1f}ms")
                    fps_counter.clear()
                    last_fps_print = time.time()
                
                frame_id += 1
        
        except Exception as e:
            print(f"[ERROR] Session error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            conn.close()
            if DISPLAY_ENABLED:
                cv2.destroyAllWindows()
            print("[INFO] Connection closed, waiting for next client...")
            
except KeyboardInterrupt:
    print("\n[SHUTDOWN] Keyboard interrupt received")
finally:
    print("[SHUTDOWN] Cleaning up...")

    sender.stop_heartbeat()
    
    print(f"[SHUTDOWN] Waiting for {upload_queue.qsize()} uploads to complete...")
    upload_queue.join()
    
    upload_queue.put(None)
    upload_thread.join(timeout=5)
    
    server.close()
    if DISPLAY_ENABLED:
        cv2.destroyAllWindows()
    
    print("[SHUTDOWN] Server shutdown complete")
