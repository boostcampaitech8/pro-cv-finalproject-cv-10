import traceback
import os, time, json, asyncio, uuid, hmac, hashlib, shutil
from typing import Dict, Any, Optional
from fastapi import FastAPI, Path, UploadFile, File, Form, HTTPException, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import StreamingResponse, ORJSONResponse
from utils.encrypt import encrypt_payload, decrypt_payload
#from utils.tracker import InstanceSelector
from utils.tracker_bytetrack import ByteTrackAdvanced as InstanceSelector
from utils.clova import CompletionExecutor

import multiprocessing as mp

from pathlib import Path as PyPath

from db.manager import DBManager
from datetime import datetime

# ====== USAGE ======
# uvicorn server:app --host 0.0.0.0 --port 8000
# ngrok http 8000

# ====== 설정 ======
SHARED_KEY = bytes.fromhex(os.environ.get("SHARED_KEY_HEX", "00"*32))  # 파일 암호화용
SESSION_KEY = bytes.fromhex(os.environ.get("SESSION_KEY_HEX", "11"*32))  # 세션 인증용 (다른 키!)


HEARTBEAT_TIMEOUT_SEC = int(os.environ.get("HEARTBEAT_TIMEOUT_SEC", "15"))
WATCHDOG_PERIOD_SEC = float(os.environ.get("WATCHDOG_PERIOD_SEC", "1.0"))

URI = os.environ.get("URI")
# DB 연결

DB_selected = DBManager(
    uri=URI,
    db_name = "selected_object_caption"
)

DB_streaming  = DBManager(
    uri=URI,
    db_name = "streaming_service"
)

#client
Selector_per_Clients = dict()

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
                DB_streaming.set_client_status(client_id, False)

def clova_caption(image_path: str, json_path: str) -> str:
    try:
        completion_executor = CompletionExecutor(
            host='https://clovastudio.stream.ntruss.com',
            api_key=os.getenv('CLOVA_API_KEY', ""),
            request_id='450573ae85b94325a5b2720e77eaa790'
        )
        caption = completion_executor.image_caption(
            image_path=image_path,
            json_path=json_path)
        return caption
    except Exception as e:
        return "Caption generation failed. Maybe API Key error."


def clova_report(caption: str) -> str:
    try:
        completion_executor = CompletionExecutor(
            host='https://clovastudio.stream.ntruss.com',
            api_key=os.getenv('CLOVA_API_KEY', ""),
            request_id='450573ae85b94325a5b2720e77eaa790'
        )
        caption = completion_executor.report(
            text=caption)
        return caption
    except Exception as e:
        return "Report generation failed. Maybe API Key error."


## multiprocessing 업로드 헬퍼 함수
def stage_pair(jpg_src: Path, json_src: Path, selected_dir: Path ):
    # selected_dir=None이면 스테이징 없이 원본 경로 그대로 사용
    if selected_dir is None:
        return jpg_src, json_src

    selected_dir.mkdir(parents=True, exist_ok=True)
    jpg_final = selected_dir / jpg_src.name
    json_final = selected_dir / json_src.name

    jpg_tmp = selected_dir / (jpg_src.name + ".tmp") #임시 파일
    json_tmp = selected_dir / (json_src.name + ".tmp") #임시 파일

    shutil.copy2(jpg_src, jpg_tmp)
    shutil.copy2(json_src, json_tmp)

    os.replace(jpg_tmp, jpg_final)
    os.replace(json_tmp, json_final)

    return jpg_final, json_final

def worker_main(task_q):
    while True:
        item = task_q.get()
        if item is None:   # sentinel로 종료 
            break
        try:
            jpg_path, json_path = PyPath(item[0]), PyPath(item[1])
            
            with open(json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                
            DB_selected.create(
                created_at=jpg_path.stem.split("@")[1],
                remote_file_path=f"images/{jpg_path.name}",
                location_name=meta.get("location", "unknown"),
                client_id=json_path.name.split("@")[0],
                metadata=meta,
                current_file_path=str(jpg_path),
                caption="",
                report="",
            )
            caption = clova_caption(str(jpg_path), str(json_path))
            
            report = clova_report(caption)["result"]["message"]["content"]
            
            DB_selected.update_by_path(
                remote_file_path=f"images/{jpg_path.name}",
                caption=caption,
                report=report
            )
            #print(f"updated! time: {time.time()}")
            #파일 삭제
            jpg_path.unlink(missing_ok=True)
            json_path.unlink(missing_ok=True)
        except Exception:
            traceback.print_exc()

def upload_db_split(frame_files,client_id,selector, num_workers=4):
    data_dir = PyPath(f"./store/{client_id}")
    selected_dir = PyPath(f"./selected_frames/{client_id}")
    to_save = selector.select_best_filenames(frame_files)
    if not to_save: return
    task_q = mp.Queue()
    procs = [mp.Process(target=worker_main, args=(task_q,)) for _ in range(num_workers)]
    for p in procs:
        p.start()
    try:
        for img_file in to_save:
            jpg_src = data_dir / img_file
            json_src = data_dir / img_file.replace(".jpg", ".json")

            jpg_path, json_path = stage_pair(jpg_src, json_src, selected_dir)
            task_q.put((str(jpg_path), str(json_path)))
    except Exception:
        traceback.print_exc() 

    finally:
        for _ in procs:
            task_q.put(None)  # 종료 신호 
        for p in procs:
            p.join()
    
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

def upload_frame(frame_file: str, client_id: str = ""):
    json_file = frame_file.replace(".jpg", ".json")

    with open(os.path.join("./store", client_id, json_file), "r", encoding="utf-8") as f:
        meta = json.load(f)
        try:
            r = DB_streaming.create(
                created_at=(frame_file.split(".jpg")[0].split("@")[1]),
                remote_file_path=f"images/{frame_file}",
                location_name=meta.get("location", "unknown"),
                client_id=json_file.split("@")[0],
                metadata=meta,
                current_file_path=os.path.join("./store",client_id, frame_file),
                caption="",
            )
        except Exception as e:
            print(f"DB insert error: {e}")
            
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
    
    DB_streaming.set_client_status(client_id, True)

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

# 평문 이미지+json 업로드
@app.post("/upload_image", response_class=ORJSONResponse)
async def upload_image(
    client_id: str = Form(...),
    ts: str = Form(...),
    sig: str = Form(...),  
    plaintext: UploadFile = File(...),
):
    if client_id not in Selector_per_Clients:
        Selector_per_Clients[client_id] = InstanceSelector( data_dir=f"./store/{client_id}")
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
        current_dir = os.path.join("./store", f"{client_id}")
        
        os.makedirs(current_dir, exist_ok=True)
        with open(os.path.join(current_dir, f"{client_id}@{curtime}.jpg"), "wb") as f:
            f.write(image_bytes)
        with open(os.path.join(current_dir, f"{client_id}@{curtime}.json"), "wb") as f:
            f.write(json_bytes)
        
        # DB 및 S3 업로드
        selector = Selector_per_Clients[client_id]
        frame_files = sorted([p.name for p in selector.data_dir.glob("*.jpg")])
        upload_frame(frame_files[-1],client_id)  # 최신 프레임 업로드
        if len(frame_files) >= 10:
            try:
                upload_db_split(
                    frame_files = frame_files,
                    client_id = client_id,
                    selector = selector,
                    num_workers=4)
            except Exception:
                traceback.print_exc()

        return {"ok": True, "image_id": image_id, "client_id": client_id, "ts": ts, "meta_keys": list(meta.keys())}
    except HTTPException as e:
        print("HTTPException caught:", e)
        raise HTTPException(status_code=400, detail=f"decrypt/unpack failed: {e}")
    except Exception as e:
        print("General exception caught:", e)
        raise HTTPException(status_code=400, detail=f"decrypt/unpack failed: {e}")



@app.post("/report")
async def report(
            client_id: str = Form(...),
            ts: str = Form(...),
            sig: str = Form(...),  
            image_id: str = Form(...),
):
    # 검증
    if not verify_hmac(client_id, ts, image_id.encode(), sig, SESSION_KEY):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    meta = DB_selected.read_by_id(image_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Image ID not found")
    caption = meta["caption"]
    if caption is not None:
        
        completion_executor = CompletionExecutor(
            host='https://clovastudio.stream.ntruss.com',
            api_key=os.getenv('CLOVA_API_KEY', ""),
            request_id='450573ae85b94325a5b2720e77eaa790'
        )
        report = completion_executor.report(text = caption)
        # 이미지로부터..
        report["client_id"] = meta["client_id"]
        report["location_name"] = meta["location_name"]
        report["time"] = meta["updated_at"]
        return {"ok": True, "report": report}
    else:
        raise HTTPException(status_code=404, detail="This image has no caption")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, ssl_certfile="cert.pem", ssl_keyfile="key.pem")
