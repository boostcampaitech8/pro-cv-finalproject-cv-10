import os
from addict import Dict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_payload(key: bytes, plaintext: bytes, aad: bytes = b"") -> Dict[str, bytes]:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # GCM 권장 nonce 길이
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return {"nonce": nonce, "ciphertext": ct}

def decrypt_payload(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)