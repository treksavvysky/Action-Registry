from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, List, Any, Optional
import hashlib

from app.schemas import ActionList, ActionItem, ActionVersionResponse, SignatureBlock, ErrorResponse
from app.crypto import canonical_dumps, sha256_hex, sha256_prefixed_hex, verify_signature_ed25519, sha256_bytes
from app.settings import TRUSTED_KEYS

app = FastAPI()

# In-memory storage
# Structure: { name: { version: { "schema": ..., "signature": ... } } }
ACTIONS_DB = {
    "files.move": {
        "1.0.0": {
            "schema": {
                "description": "Move a file from A to B",
                "parameters": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"}
                }
            },
            "signature": {
                "alg": "ed25519",
                "kid": "dev-root-1",
                "sig": "base64:mock_signature_1.0.0"
            }
        },
        "1.1.0": {
             "schema": {
                "description": "Move a file from A to B (optional)",
                "parameters": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                    "overwrite": {"type": "boolean"}
                }
            },
            "signature": {
                "alg": "ed25519",
                "kid": "dev-root-1",
                "sig": "base64:mock_signature_1.1.0"
            }
        }
    }
}

def create_error_response(status_code: int, code: str, message: str, details: Optional[Dict[str, Any]] = None):
    content = {
        "error": {
            "code": code,
            "message": message,
            "details": details
        }
    }
    return JSONResponse(status_code=status_code, content=content)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/actions", response_model=ActionList)
def list_actions():
    items = []
    for name, versions_dict in ACTIONS_DB.items():
        versions = sorted(versions_dict.keys()) # simple string sort for now, as per Sprint-0 scope
        latest = versions[-1] if versions else "0.0.0"

        # Get description from latest version if available
        description = None
        if latest and latest in versions_dict:
             description = versions_dict[latest]["schema"].get("description")

        items.append(ActionItem(
            name=name,
            latest_version=latest,
            versions=versions,
            description=description
        ))
    return ActionList(items=items)

@app.get("/actions/{name}/versions/{version}", response_model=ActionVersionResponse, responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}})
def get_action_version(name: str, version: str):
    if name not in ACTIONS_DB:
        return create_error_response(404, "ACTION_NOT_FOUND", f"Action '{name}' not found")

    versions_dict = ACTIONS_DB[name]
    if version not in versions_dict:
        return create_error_response(404, "VERSION_NOT_FOUND", f"Version '{version}' not found")

    data = versions_dict[version]
    schema_obj = data["schema"]
    sig_data = data["signature"]

    # Compute hash
    canonical_bytes = canonical_dumps(schema_obj)

    # Verify
    kid = sig_data.get("kid")
    trusted_entry = TRUSTED_KEYS.get(kid)

    is_verified = False
    verify_error = None

    if not trusted_entry:
        verify_error = "Unknown key id"
        # verified remains False
    else:
        alg, pub_key_bytes = trusted_entry
        if alg != "ed25519":
             verify_error = f"Unsupported algorithm in trust store: {alg}"
        else:
            # We need to verify the hash of the canonical payload
            hash_bytes_val = sha256_bytes(canonical_bytes)

            if verify_signature_ed25519(
                hash_bytes=hash_bytes_val,
                sig_b64=sig_data["sig"],
                public_key_bytes=pub_key_bytes
            ):
                is_verified = True
            else:
                verify_error = "Bad signature"

    return ActionVersionResponse(
        name=name,
        version=version,
        schema=schema_obj,
        hash=sha256_prefixed_hex(canonical_bytes),
        signature=SignatureBlock(**sig_data),
        verified=is_verified,
        verify_error=verify_error
    )
