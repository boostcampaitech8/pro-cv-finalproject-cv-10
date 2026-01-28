import os, time, json, asyncio, uuid, hmac, hashlib
from typing import Dict, Any, Optional
from fastapi import FastAPI, Path, UploadFile, File, Form, HTTPException, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import StreamingResponse, ORJSONResponse
from lib.encrypt import encrypt_payload, decrypt_payload
from lib.tracker import InstanceSelector
from lib.clova import CompletionExecutor

from db.manager import DBManager
from datetime import datetime

# ====== USAGE ======
# uvicorn server:app --host 0.0.0.0 --port 8000
# ngrok http 8000

# ====== 설정 ======
SHARED_KEY = bytes.fromhex(os.environ.get("SHARED_KEY_HEX", "00"*32))  # 파일 암호화용
SESSION_KEY = bytes.fromhex(os.environ.get("SESSION_KEY_HEX", "11"*32))  # 세션 인증용 (다른 키!)

STORE_DIR = os.environ.get("STORE_DIR", "./store")
os.makedirs(STORE_DIR, exist_ok=True)

HEARTBEAT_TIMEOUT_SEC = int(os.environ.get("HEARTBEAT_TIMEOUT_SEC", "15"))
WATCHDOG_PERIOD_SEC = float(os.environ.get("WATCHDOG_PERIOD_SEC", "1.0"))

URI = os.environ.get("URI")
# DB 연결
DB = DBManager(
    uri=URI
)

# Instance Selector 초기화
selector = InstanceSelector(iou_thresh=0.2, data_dir="./store")

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

STATE = {} # 전역 상태 객체

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
        for client_id, state in STATE.items():
            if _now() - state.last_seen_ts > HEARTBEAT_TIMEOUT_SEC:
                STATE[client_id].is_connected = False
                DB.set_client_status(client_id, False)

def clova_caption(image_path: str, json_path: str) -> str:
    completion_executor = CompletionExecutor(
        host='https://clovastudio.stream.ntruss.com',
        api_key=os.getenv('CLOVA_API_KEY', ""),
        request_id='450573ae85b94325a5b2720e77eaa790'
    )
    caption = completion_executor.execute(
        image_path=image_path,
        json_path=json_path)
    return caption

def upload_db(frame_files):
    print("FULL")
    to_save = selector.select_best_filenames(frame_files)
    print("To save is:", to_save)
    
    for img_file in to_save:
        # DB upload
        json_file = img_file.replace(".jpg", ".json")
        caption = clova_caption(
            "./store" + "/" + img_file,
            "./store" + "/" + json_file
        )
        print("CAPTIONN:    ")
        print(caption)
        with open(os.path.join("./store", json_file), "r", encoding="utf-8") as f:
            meta = json.load(f)
            r = DB.create(
                created_at=img_file.split(".jpg")[0],
                remote_file_path=f"images/{img_file}",
                location_name=meta.get("location", "unknown"),
                client_id=json_file.split("@")[0],
                metadata=meta,
                current_file_path=os.path.join("./store", img_file),
                caption=caption,
            )
            print(r)

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
    
    if client_id not in STATE:
        STATE[client_id] = ConnectionState()
        STATE[client_id].is_connected = True
        STATE[client_id].last_seen_ts = _now()
    else:
        STATE[client_id].last_seen_ts = _now()
        STATE[client_id].is_connected = True
    
    DB.set_client_status(client_id, True)

    return {"ok": True, "server_ts": STATE[client_id].last_seen_ts}

@app.get("/connection_state")
async def connection_state():
    return {
        "is_connected": STATE.is_connected, #15초 이상 HEARTBEAT 없으면 False
        "last_seen_ts": STATE.last_seen_ts, # 마지막 HEARTBEAT 수신 시각
        "last_client_id": STATE.last_client_id, # 마지막 HEARTBEAT 보낸 클라이언트 ID
        "timeout_sec": HEARTBEAT_TIMEOUT_SEC, # 타임아웃 설정 값
    }

# ====== 이미지 업로드 및 다운로드 ======
# AES-GCM 암호화된 이미지+json 업로드
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
        with open(os.path.join(STORE_DIR, f"{client_id}@{curtime}.jpg"), "wb") as f:
            f.write(image_bytes)
        with open(os.path.join(STORE_DIR, f"{client_id}@{curtime}.json"), "wb") as f:
            f.write(json_bytes)
        
        # DB 및 S3 업로드
        frame_files = sorted([p.name for p in selector.data_dir.glob("*.jpg")])
        if len(frame_files) >= 10:
            upload_db(frame_files)


        return {"ok": True, "image_id": image_id, "client_id": client_id, "ts": ts, "meta_keys": list(meta.keys())}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"decrypt/unpack failed: {e}")

# 평문 이미지+json 업로드
@app.post("/upload_image", response_class=ORJSONResponse)
async def upload_image(
    client_id: str = Form(...),
    ts: str = Form(...),
    sig: str = Form(...),  
    plaintext: UploadFile = File(...),
):
    try:
        pt_b = await plaintext.read()

        # HMAC 검증: plaintext를 함께 서명
        if not verify_hmac(client_id, ts, pt_b, sig, SESSION_KEY):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # 파일 암호화 복호화
        image_bytes, json_bytes = unpack_two_files(pt_b)
        meta = json.loads(json_bytes.decode("utf-8"))

        image_id = str(uuid.uuid4())
        curtime = datetime.now()
        with open(os.path.join(STORE_DIR, f"{client_id}@{curtime}.jpg"), "wb") as f:
            f.write(image_bytes)
        with open(os.path.join(STORE_DIR, f"{client_id}@{curtime}.json"), "wb") as f:
            f.write(json_bytes)
        
        # DB 및 S3 업로드
        frame_files = sorted([p.name for p in selector.data_dir.glob("*.jpg")])
        if len(frame_files) >= 10:
            upload_db(frame_files)
                
        return {"ok": True, "image_id": image_id, "client_id": client_id, "ts": ts, "meta_keys": list(meta.keys())}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"decrypt/unpack failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8443, ssl_certfile="cert.pem", ssl_keyfile="key.pem")
