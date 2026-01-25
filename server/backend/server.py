import os, time, json, asyncio, uuid, hmac, hashlib
from typing import Dict, Any, Optional
from fastapi import FastAPI, Path, UploadFile, File, Form, HTTPException, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import StreamingResponse, ORJSONResponse
from encrypt import encrypt_payload, decrypt_payload
from tracker import InstanceSelector
import boto3


from db.manager import MongoDBAtlasManager
from datetime import datetime

# ====== 설정 ======
SHARED_KEY = bytes.fromhex(os.environ.get("SHARED_KEY_HEX", "00"*32))  # 파일 암호화용
SESSION_KEY = bytes.fromhex(os.environ.get("SESSION_KEY_HEX", "11"*32))  # 세션 인증용 (다른 키!)

STORE_DIR = os.environ.get("STORE_DIR", "./store")
os.makedirs(STORE_DIR, exist_ok=True)

HEARTBEAT_TIMEOUT_SEC = int(os.environ.get("HEARTBEAT_TIMEOUT_SEC", "15"))
WATCHDOG_PERIOD_SEC = float(os.environ.get("WATCHDOG_PERIOD_SEC", "1.0"))

URI = ""
AWS_ACCESS_KEY_ID = ""
AWS_SECRET_ACCESS_KEY = ""
# MongoDB Atlas 연결
DB = MongoDBAtlasManager(
    uri=URI
)

# AWS S3 설정
BUCKET = "pro-cv-finalproject-cv-10-ehekafhr"
s3 = boto3.client("s3", region_name="ap-southeast-2",
                  aws_access_key_id=AWS_ACCESS_KEY_ID,
                  aws_secret_access_key=AWS_SECRET_ACCESS_KEY )

# Instance Selector 초기화
selector = InstanceSelector(iou_thresh=0.2, data_dir="./store")

def DB_upload_metadata(file_path: str, created_at: datetime, location_name: str, metadata: Dict[str, Any]) -> str:
    remote_file_path = f"s3://{BUCKET}/{file_path}"
    doc_id = DB.create(
        created_at=created_at,
        remote_file_path=remote_file_path,
        location_name=location_name,
        metadata=metadata
    )
    return doc_id

def S3_upload_file(file_path: str, local_path: str) -> None:
    s3.upload_file(local_path, BUCKET, file_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(watchdog_loop())
    try:
        yield
    finally:
        task.cancel()

app = FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan)

# ====== 연결 상태 ======
class ConnectionState:
    def __init__(self):
        self.last_seen_ts: Optional[float] = None
        self.is_connected: bool = False
        self.last_client_id: Optional[str] = None

STATE = ConnectionState()

def _now() -> float:
    return time.time()

def compute_hmac(client_id: str, ts: str, body: bytes, key: bytes) -> str:
    """HMAC 계산"""
    msg = f"{client_id}:{ts}".encode() + b":" + body
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_hmac(client_id: str, ts: str, body: bytes, received_sig: str, key: bytes) -> bool:
    computed_sig = compute_hmac(client_id, ts, body, key)
    return hmac.compare_digest(computed_sig, received_sig)

# ====== 유틸 함수 ======
def pack_image_json(meta: Dict[str, Any], image_bytes: bytes) -> bytes:
    meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    return meta_bytes + b"\n" + image_bytes

def unpack_image_json(payload: bytes):
    i = payload.find(b"\n")
    if i < 0:
        raise ValueError("Invalid payload: missing delimiter")
    meta = json.loads(payload[:i].decode("utf-8"))
    img = payload[i+1:]
    return meta, img

def unpack_two_files(payload: bytes) -> tuple[bytes, bytes]:
    n = int.from_bytes(payload[:8], "big")
    json_bytes = payload[8:8+n]
    image_bytes = payload[8+n:]
    return image_bytes, json_bytes

async def watchdog_loop():
    while True:
        await asyncio.sleep(WATCHDOG_PERIOD_SEC)
        if STATE.last_seen_ts is None:
            STATE.is_connected = False
            continue
        if _now() - STATE.last_seen_ts > HEARTBEAT_TIMEOUT_SEC:
            STATE.is_connected = False


# ====== API 엔드포인트 ======
@app.post("/heartbeat")
async def heartbeat(client_id: str = Form(...), ts: str = Form(...), sig: str = Form(...)):
    """
    heartbeat with HMAC verification.
    sig = HMAC-SHA256(client_id:ts, SESSION_KEY)
    """
    # 빈 본문(heartbeat은 파일 없음)
    if not verify_hmac(client_id, ts, b"", sig, SESSION_KEY):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    STATE.last_seen_ts = _now()
    STATE.is_connected = True
    STATE.last_client_id = client_id
    return {"ok": True, "server_ts": STATE.last_seen_ts}

@app.get("/connection_state")
async def connection_state():
    return {
        "is_connected": STATE.is_connected,
        "last_seen_ts": STATE.last_seen_ts,
        "last_client_id": STATE.last_client_id,
        "timeout_sec": HEARTBEAT_TIMEOUT_SEC,
    }

@app.post("/upload_image_enc", response_class=ORJSONResponse)
async def upload_image_enc(
    client_id: str = Form(...),
    ts: str = Form(...),
    sig: str = Form(...),  # HMAC 서명 추가
    nonce: UploadFile = File(...),
    ciphertext: UploadFile = File(...),
):
    """
    Encrypted image+json 업로드.
    sig = HMAC-SHA256((client_id:ts:nonce_bytes:ciphertext_bytes), SESSION_KEY)
    """
    try:
        nonce_b = await nonce.read()
        ct_b = await ciphertext.read()
        
        # HMAC 검증: nonce + ciphertext를 함께 서명
        combined = nonce_b + ct_b
        if not verify_hmac(client_id, ts, combined, sig, SESSION_KEY):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # 파일 암호화 복호화
        payload = decrypt_payload(SHARED_KEY, nonce_b, ct_b, aad=b"img+json:v1")
        image_bytes, json_bytes = unpack_two_files(payload)
        meta = json.loads(json_bytes.decode("utf-8"))

        image_id = str(uuid.uuid4())
        curtime = datetime.now()
        with open(os.path.join(STORE_DIR, f"{curtime}.jpg"), "wb") as f:
            f.write(image_bytes)
        with open(os.path.join(STORE_DIR, f"{curtime}.json"), "wb") as f:
            f.write(json_bytes)
        
        # DB 및 S3 업로드
        frame_files = sorted([p.name for p in selector.data_dir.glob("*.jpg")])
        if len(frame_files) >= 10:
            print("FULL")
            to_save = selector.select_best_filenames(frame_files)
            print("To save is:", to_save)
            
            for img_file in to_save:
                # DB upload
                json_file = img_file.replace(".jpg", ".json")
                with open(os.path.join("./store", json_file), "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    image_id = DB_upload_metadata(
                        file_path=f"images/{img_file}",
                        created_at = img_file.split(".jpg")[0],
                        location_name=meta.get("location", "unknown"),
                        metadata=meta
                    )
                # S3 upload
                s3_file_path = f"images/{img_file}"
                local_img_path = os.path.join(selector.data_dir, img_file)
                S3_upload_file(s3_file_path, local_img_path)

            # 폴더에서, "맨 뒤 5프레임" 제외 삭제
            data_dir = selector.data_dir
            jpg_paths = sorted(data_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
            keep_set = set(p.name for p in jpg_paths[-5:])  
            for p in jpg_paths:
                if p.name in keep_set:
                    continue
                # jpg 삭제
                p.unlink(missing_ok=True)
                # 매칭 json 삭제
                json_p = p.with_suffix(".json")
                json_p.unlink(missing_ok=True)

                
        return {"ok": True, "image_id": image_id, "client_id": client_id, "ts": ts, "meta_keys": list(meta.keys())}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"decrypt/unpack failed: {e}")

@app.get("/download_image/{image_id}")
async def download_image(image_id: str):
    nonce_path = os.path.join(STORE_DIR, f"{image_id}.nonce")
    bin_path = os.path.join(STORE_DIR, f"{image_id}.bin")
    if not (os.path.exists(nonce_path) and os.path.exists(bin_path)):
        raise HTTPException(status_code=404, detail="not found")

    nonce = open(nonce_path, "rb").read()
    ciphertext = open(bin_path, "rb").read()
    payload = decrypt_payload(SHARED_KEY, nonce, ciphertext, aad=b"img+json:v1")
    meta, img = unpack_image_json(payload)

    boundary = "----fastapi-boundary"

    def gen():
        yield f"--{boundary}\r\nContent-Type: application/json\r\n\r\n".encode()
        yield json.dumps(meta, ensure_ascii=False).encode("utf-8")
        yield b"\r\n"
        yield f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        yield img
        yield b"\r\n"
        yield f"--{boundary}--\r\n".encode()

    return StreamingResponse(gen(), media_type=f"multipart/mixed; boundary={boundary}")

@app.get("/request_image")
async def request_image():
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8443, ssl_certfile="cert.pem", ssl_keyfile="key.pem")
