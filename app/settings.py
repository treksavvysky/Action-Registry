import os
import json
import base64
from typing import Dict, Tuple

def load_trusted_keys() -> Dict[str, Tuple[str, bytes]]:
    keys_json = os.getenv("TRUSTED_KEYS_JSON")
    keys_path = os.getenv("TRUSTED_KEYS_PATH")

    data = []
    if keys_json:
        try:
            data = json.loads(keys_json)
        except json.JSONDecodeError:
            print("Warning: Failed to parse TRUSTED_KEYS_JSON")
    elif keys_path and os.path.exists(keys_path):
        try:
            with open(keys_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
             print(f"Warning: Failed to load keys from {keys_path}")

    trusted_keys = {}
    for entry in data:
        kid = entry.get("kid")
        alg = entry.get("alg")
        pub_key_str = entry.get("public_key", "")

        if not (kid and alg and pub_key_str):
            continue

        if pub_key_str.startswith("base64:"):
            pub_key_str = pub_key_str[7:]

        try:
            pub_key_bytes = base64.b64decode(pub_key_str)
            trusted_keys[kid] = (alg, pub_key_bytes)
        except Exception as e:
            print(f"Warning: Failed to decode key for kid {kid}: {e}")

    return trusted_keys

TRUSTED_KEYS = load_trusted_keys()

API_KEY = os.getenv("ACTION_REGISTRY_API_KEY")
