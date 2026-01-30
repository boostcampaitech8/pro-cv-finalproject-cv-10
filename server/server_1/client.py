import os, json, time, asyncio, hmac, hashlib
import httpx
from utils.encrypt import encrypt_payload, decrypt_payload
from utils.utils import compute_hmac
# ngrok 가입 후,ngrok config add-authtoken <your_token> 입력.
# uvicorn server:app --host 0.0.0.0 --port 8000
# ngrok http 8000 후
# export SERVER=""로.
SERVER = os.environ.get("SERVER", "https://localhost:8000")
#SERVER = "https://localhost:8000"
print(SERVER)
CLIENT_ID = os.environ.get("CLIENT_ID", "client_1")
SHARED_KEY = bytes.fromhex(os.environ.get("SHARED_KEY_HEX", "00"*32))
SESSION_KEY = bytes.fromhex(os.environ.get("SESSION_KEY_HEX", "11"*32))  # 서버와 동일한 세션키

LIMITS = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=20,
    keepalive_expiry=60.0,
)

client = httpx.AsyncClient(
    base_url=SERVER,
    verify=False,
    timeout=httpx.Timeout(10.0),
    limits=LIMITS,
)

stop_event = asyncio.Event()

async def request_with_retry(method: str, url: str, *, max_retry=999999, **kwargs):
    backoff = 1.0
    attempt = 0
    while True:
        try:
            r = await client.request(method, url, **kwargs)
            r.raise_for_status()
            return r
        except Exception:
            attempt += 1
            if attempt >= max_retry:
                raise
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

async def heartbeat_loop(period_sec: float = 3.0):
    """heartbeat with HMAC signature"""
    while not stop_event.is_set():
        try:
            ts = str(time.time())
            sig = compute_hmac(CLIENT_ID, ts, b"", SESSION_KEY)
            await request_with_retry(
                "POST",
                "/heartbeat",
                data={"client_id": CLIENT_ID, "ts": ts, "sig": sig}
            )
            await asyncio.sleep(period_sec)
        except Exception:
            await asyncio.sleep(1.0)

def pack_two_files(image_bytes: bytes, json_bytes: bytes) -> bytes:
    n = len(json_bytes).to_bytes(8, "big")
    return n + json_bytes + image_bytes

async def upload_image_and_json_enc(image_path: str, json_path: str):
    """Upload with HMAC signature"""
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    with open(json_path, "rb") as f:
        json_bytes = f.read()

    plaintext = pack_two_files(image_bytes, json_bytes)
    enc = encrypt_payload(SHARED_KEY, plaintext, aad=b"img+json:v1")
    
    ts = str(time.time())
    combined = enc["nonce"] + enc["ciphertext"]
    sig = compute_hmac(CLIENT_ID, ts, combined, SESSION_KEY)
    
    files = {
        "client_id": (None, CLIENT_ID),
        "ts": (None, ts),
        "sig": (None, sig),  # HMAC 서명 추가
        "nonce": ("nonce.bin", enc["nonce"], "application/octet-stream"),
        "ciphertext": ("data.bin", enc["ciphertext"], "application/octet-stream"),
    }

    r = await request_with_retry("POST", "/upload_image_enc", files=files)
    return r.json()


async def upload_image_and_json(image_path: str, json_path: str):
    """Upload with HMAC signature"""
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    with open(json_path, "rb") as f:
        json_bytes = f.read()

    plaintext = pack_two_files(image_bytes, json_bytes)

    ts = str(time.time())
    sig = compute_hmac(CLIENT_ID, ts, plaintext, SESSION_KEY)
    
    files = {
        "client_id": (None, CLIENT_ID),
        "ts": (None, ts),
        "sig": (None, sig),  # HMAC 서명 추가
        "plaintext": ("data.bin", plaintext, "application/octet-stream"),
    }

    r = await request_with_retry("POST", "/upload_image", files=files)
    return r.json()

async def main():
    hb_task = asyncio.create_task(heartbeat_loop())

    try:
        for i in range(10):
            resp = await upload_image_and_json(
                f"./samples/img/frame_0{i}.jpg",
                f"./samples/label/frame_0{i}.json",
            )
            print("uploaded:", resp)
        while True:
            print("heartbeat running...")
            await asyncio.sleep(10)
    except httpx.HTTPStatusError as e:
        error_detail = e.response.json()["detail"]
        print(f"Status: {e.response.status_code}, Detail: {error_detail}")
    finally:
        stop_event.set()
        hb_task.cancel()
        await client.aclose()
        
async def test_report(image_id: str):
    ts = str(time.time())
    sig = compute_hmac(CLIENT_ID, ts, image_id.encode(), SESSION_KEY)
    resp = await request_with_retry(
        "POST",
        "/report",
        data={"client_id": CLIENT_ID, "ts": ts, "sig": sig, "image_id": image_id}
    )

    print("report:", resp.json())

if __name__ == "__main__":
    asyncio.run(main())
    #asyncio.run(test_report("697c0c6bc7e48d53d77560f8"))  # 여기에 이미지 ID 입력
