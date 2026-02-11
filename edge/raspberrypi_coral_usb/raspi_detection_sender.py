import os
import time
import hmac
import hashlib
import json
import requests
from threading import Thread

class DetectionSender:
    def __init__(self, client_id, server_url):
        self.client_id = client_id
        self.server_url = server_url.rstrip('/')

        session_key_hex = os.environ.get("SESSION_KEY_HEX", "11" * 32)
        self.session_key = bytes.fromhex(session_key_hex)

        self.heartbeat_thread = None
        self.heartbeat_running = False 

        print(f"DetectionSender initialized | ID: {client_id} | URL: {server_url}")

    def compute_hmac(self, ts, body):
        msg = f"{self.client_id}:{ts}".encode() + b":" + body
        return hmac.new(self.session_key, msg, hashlib.sha256).hexdigest()

    def pack(self, annotations, image_bytes, latitude, longitude, weather, location_name, timestamp):
        json_data = {
            "annotations": [
                {
                    "class": int(ann["class"]),
                    "confidence": round(float(ann["confidence"]), 4),
                    "bbox": [int(v) for v in ann["bbox"]]
                } for ann in annotations
            ],
            "latitude": latitude,
            "longitude": longitude,
            "weather": weather,
            "location_name": location_name,
            "time": timestamp
        }
        json_bytes = json.dumps(json_data).encode('utf-8')
        json_length = len(json_bytes).to_bytes(8, "big")
        return json_length + json_bytes + image_bytes

    def upload(self, annotations, image_bytes, latitude=0, longitude=0, weather=0, location_name="unknown_location", timestamp=None):
        if timestamp is None:
            timestamp = int(time.time())
        
        plaintext = self.pack(annotations, image_bytes, latitude, longitude, weather, location_name, timestamp)
        ts = str(time.time())
        sig = self.compute_hmac(ts, plaintext)
        
        files = {
            "client_id": (None, self.client_id),
            "ts": (None, ts),
            "sig": (None, sig),
            "plaintext": ("data.bin", plaintext, "application/octet-stream"),
        }
        
        try:
            response = requests.post(f"{self.server_url}/upload_image", files=files, timeout=10)
            if response.status_code == 200:
                print(f"Upload success: {len(annotations)} objects")
                return True
            return False
        except Exception as e:
            print(f"Upload error: {e}")
            return False

    def send_heartbeat(self):
        ts = str(time.time())
        sig = self.compute_hmac(ts, b"")
        data = {"client_id": self.client_id, "ts": ts, "sig": sig}
        try:
            response = requests.post(f"{self.server_url}/heartbeat", data=data, timeout=5)
            return response.status_code == 200
        except: return False

    def _heartbeat_loop(self, interval):
        while self.heartbeat_running:
            self.send_heartbeat()
            time.sleep(interval)

    def start_heartbeat(self, interval=10):
        if not self.heartbeat_running:
            self.heartbeat_running = True
            self.heartbeat_thread = Thread(target=self._heartbeat_loop, args=(interval,), daemon=True)
            self.heartbeat_thread.start()
            print(f"Heartbeat started ({interval}s)")

    def stop_heartbeat(self):
        self.heartbeat_running = False
        print("Heartbeat stopped")
