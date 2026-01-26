import json
import hashlib

def canonical_dumps(obj) -> bytes:
    """
    Returns the canonical JSON representation of the object as bytes.
    Rules:
    - UTF-8 encoding
    - Keys sorted recursively
    - No whitespace (separators=(',', ':'))
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def sha256_hex(payload: bytes) -> str:
    """
    Computes the SHA-256 hash of the payload and returns it as a hex string.
    """
    return hashlib.sha256(payload).hexdigest()

def verify_signature_ed25519(hash_bytes: bytes, sig_b64: str, public_key_b64: str) -> bool:
    """
    Verifies an Ed25519 signature.
    STUB: Returns False for Sprint-0.
    TODO: Wire real Ed25519 verification in Sprint-1.
    """
    return False
