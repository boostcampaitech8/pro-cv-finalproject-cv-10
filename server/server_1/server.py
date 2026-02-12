import traceback
import os, time, json, asyncio, uuid, shutil
from typing import Optional
from fastapi import FastAPI, Path, UploadFile, File, Form, HTTPException
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import ORJSONResponse
from utils.tracker_bytetrack import ByteTrackAdvanced as InstanceSelector
from utils.clova import CompletionExecutor, clova_caption, clova_report
import errno
from pymongo.errors import DuplicateKeyError
import multiprocessing as mp

from pathlib import Path as PyPath

from db.manager import DBManager
from datetime import datetime
from utils.utils import verify_hmac, unpack_two_files

# ====== USAGE ======
# uvicorn server:app --host 0.0.0.0 --port 8000
# ngrok http 8000

# ====== 설정 ======
SHARED_KEY = bytes.fromhex(os.environ.get("SHARED_KEY_HEX", "00"*32))  # 파일 암호화용
SESSION_KEY = bytes.fromhex(os.environ.get("SESSION_KEY_HEX", "11"*32))  # 세션 인증용 


HEARTBEAT_TIMEOUT_SEC = int(os.environ.get("HEARTBEAT_TIMEOUT_SEC", "15"))
WATCHDOG_PERIOD_SEC = float(os.environ.get("WATCHDOG_PERIOD_SEC", "1.0"))


LastSentFrame_per_Client = {}  
FrameCounter_per_Client = {}   
Selector_per_Clients = dict()
FrameCounter_per_Clients = dict()
LastSentFrame_per_Clients = dict()
TASK_Q = None
WORKERS = []

URI = os.environ.get("URI")
# DB 연결

DB_selected = DBManager(
    uri=URI,
    db_name = "data_metadata"
)

DB_streaming  = DBManager(
    uri=URI,
    db_name = "streaming_service"
)

#client
Selector_per_Clients = dict()

TASK_Q = mp.Queue()

@asynccontextmanager
async def lifespan(app: FastAPI):

    global TASK_Q, WORKERS

    WORKERS = [mp.Process(target=worker_main, args=(TASK_Q,)) for _ in range(5)]
    task = asyncio.create_task(watchdog_loop())
    for p in WORKERS:
        p.start()

    task = asyncio.create_task(watchdog_loop())
    try:
        yield
    finally:
        for _ in WORKERS:
            TASK_Q.put(None)
        for p in WORKERS:
            p.join()

app = FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan)

# ====== 연결 상태 ======
class ConnectionState:
    def __init__(self):
        self.last_seen_ts: Optional[float] = None
        self.is_connected: bool = False
        self.last_client_id: Optional[str] = None

STATE = {} # 전역 상태 객체


async def watchdog_loop():
    while True:
        await asyncio.sleep(WATCHDOG_PERIOD_SEC)
        for client_id, state in STATE.items():
            if time.time() - state.last_seen_ts > HEARTBEAT_TIMEOUT_SEC:
                STATE[client_id].is_connected = False
                DB_streaming.set_client_status(client_id, False)
                DB_selected.set_client_status(client_id, False)
                
def purge_store_dir(data_dir: PyPath, cutoff_ts: float):
    for p in data_dir.glob("*"):
        if p.suffix not in (".jpg", ".json"):
            continue
        try:
            if p.stat().st_mtime <= cutoff_ts:
                p.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        
## multiprocessing 업로드 헬퍼 함수
def stage_pair(jpg_src: PyPath, json_src: PyPath, selected_dir: Optional[PyPath]):
    if selected_dir is None:
        return jpg_src, json_src

    selected_dir.mkdir(parents=True, exist_ok=True)
    jpg_final = selected_dir / jpg_src.name
    json_final = selected_dir / json_src.name
    lock_path = selected_dir / (jpg_src.name + ".lock")

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except OSError as e:
        traceback.print_exc()
        if e.errno == errno.EEXIST:
            return None
        raise

    try:
        if not jpg_src.exists() or not json_src.exists():
            return None

        os.replace(str(jpg_src), str(jpg_final))
        os.replace(str(json_src), str(json_final))
        return jpg_final, json_final
    except:
        traceback.print_exc()
    finally:
        lock_path.unlink(missing_ok=True)

def worker_main(task_q):
    db = DBManager(uri=URI, db_name="data_metadata")

    while True:
        item = task_q.get()
        if item is None:
            break

        jpg_path = json_path = None
        

        try:
            jpg_path, json_path = PyPath(item[0]), PyPath(item[1])
            
            created_at_str = jpg_path.stem.split("@")[1],
            print(created_at_str)
            created_at_dt = datetime.strptime(created_at_str[0],"%Y-%m-%d %H:%M:%S.%f")
            print(created_at_dt)
            with open(json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            try:
                db.create(
                    created_at=created_at_dt,
                    remote_file_path=f"images/{jpg_path.name}",
                    location_name=meta.get("location", "unknown"),
                    client_id=json_path.name.split("@")[0],
                    metadata=meta,
                    current_file_path=str(jpg_path),
                    caption="",
                    report="",
                )
            except Exception as e:
                print("ERROR",e)
                if isinstance(e, DuplicateKeyError) or ("E11000" in str(e)):
                    jpg_path.unlink(missing_ok=True)
                    json_path.unlink(missing_ok=True)
                    continue
                else:
                    print("ERROR:",e)
                raise

            caption = clova_caption(str(jpg_path), str(json_path))
            report = clova_report(caption)["result"]["message"]["content"]

            db.update_by_path(
                remote_file_path=f"images/{jpg_path.name}",
                caption=caption,
                report=report
            )

            jpg_path.unlink(missing_ok=True)
            json_path.unlink(missing_ok=True)

        except Exception:
            traceback.print_exc()
            if jpg_path: jpg_path.unlink(missing_ok=True)
            if json_path: json_path.unlink(missing_ok=True)
            
            

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
        STATE[client_id].last_seen_ts = time.time()
    else:
        STATE[client_id].last_seen_ts = time.time()
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
        selector: InstanceSelector = Selector_per_Clients[client_id]

        FrameCounter_per_Clients[client_id] = FrameCounter_per_Clients.get(client_id, 0) + 1
        server_frame_idx = FrameCounter_per_Clients[client_id]

        LastSentFrame_per_Clients.setdefault(client_id, {})

        latest_jpg = f"{client_id}@{curtime}.jpg"
        new_ids, touched_ids = selector.update_one(latest_jpg)

        to_send = set(new_ids)

        for tid in touched_ids:
            last = LastSentFrame_per_Clients[client_id].get(tid)
            if last is not None and (server_frame_idx - last) >= 10:
                to_send.add(tid)

        data_dir = PyPath(f"./store/{client_id}")
        selected_dir = PyPath(f"./selected_frames/{client_id}")

        for tid in sorted(to_send):
            fname = selector.get_best_filename_for_track(tid)
            if fname is None:
                continue

            jpg_src = data_dir / fname
            json_src = data_dir / fname.replace(".jpg", ".json")
            staged = stage_pair(jpg_src, json_src, selected_dir)
            if staged is None:
                continue

            jpg_path, json_path = staged
            TASK_Q.put((str(jpg_path), str(json_path)))
            LastSentFrame_per_Clients[client_id][tid] = server_frame_idx

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
