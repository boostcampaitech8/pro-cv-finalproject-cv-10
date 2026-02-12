

import hashlib
import hmac
import json
from typing import Any, Dict


def compute_hmac(client_id: str, ts: str, body: bytes, key: bytes) -> str:
    """HMAC 계산"""
    msg = f"{client_id}:{ts}".encode() + b":" + body
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_hmac(client_id: str, ts: str, body: bytes, received_sig: str, key: bytes) -> bool:
    computed_sig = compute_hmac(client_id, ts, body, key)
    return hmac.compare_digest(computed_sig, received_sig)

# ====== 유틸 함수 ======


def unpack_two_files(payload: bytes) -> tuple[bytes, bytes]:
    n = int.from_bytes(payload[:8], "big")
    json_bytes = payload[8:8+n]
    image_bytes = payload[8+n:]
    return image_bytes, json_bytes
