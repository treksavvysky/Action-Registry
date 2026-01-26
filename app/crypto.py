import json
import hashlib
import base64
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

def canonical_dumps(obj) -> bytes:
    """
    Returns the canonical JSON representation of the object as bytes.
    Rules:
    - UTF-8 encoding
    - Keys sorted recursively
    - No whitespace (separators=(',', ':'))
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def sha256_bytes(payload: bytes) -> bytes:
    """
    Computes the SHA-256 hash of the payload and returns it as bytes.
    """
    return hashlib.sha256(payload).digest()

def sha256_hex(payload: bytes) -> str:
    """
    Computes the SHA-256 hash of the payload and returns it as a hex string.
    """
    return hashlib.sha256(payload).hexdigest()

def sha256_prefixed_hex(payload: bytes) -> str:
    """
    Computes the SHA-256 hash and returns it as 'sha256:<hex>'.
    """
    return f"sha256:{sha256_hex(payload)}"

def verify_signature_ed25519(hash_bytes: bytes, sig_b64: str, public_key_bytes: bytes) -> bool:
    """
    Verifies an Ed25519 signature.

    Args:
        hash_bytes: The data that was signed (the SHA256 hash of the canonical payload).
        sig_b64: Base64 encoded signature (optionally prefixed with 'base64:').
        public_key_bytes: The raw public key bytes.

    Returns:
        True if the signature is valid, False otherwise.
    """
    try:
        if sig_b64.startswith("base64:"):
            sig_b64 = sig_b64[7:]
        sig_bytes = base64.b64decode(sig_b64)

        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(sig_bytes, hash_bytes)
        return True
    except Exception:
        return False
