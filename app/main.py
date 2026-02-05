from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from typing import Dict, List, Any, Optional

from app.schemas import ActionList, ActionItem, ActionVersionResponse, SignatureBlock, ErrorResponse, PublishRequest
from app.crypto import canonical_dumps, sha256_hex, sha256_prefixed_hex, verify_signature_ed25519, sha256_bytes
from app.settings import TRUSTED_KEYS, API_KEY

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


@app.post("/actions/{name}/versions/{version}", status_code=201, response_model=ActionVersionResponse, responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
def publish_action(name: str, version: str, body: PublishRequest, x_api_key: Optional[str] = Header(None)):
    # Auth
    if not API_KEY or not x_api_key or x_api_key != API_KEY:
        return create_error_response(401, "UNAUTHORIZED", "Invalid or missing API key")

    schema_obj = body.schema_
    sig_data = body.signature

    # Compute canonical hash
    canonical_bytes = canonical_dumps(schema_obj)
    hash_bytes_val = sha256_bytes(canonical_bytes)
    hash_hex = sha256_prefixed_hex(canonical_bytes)

    # Look up trusted key
    kid = sig_data.kid
    trusted_entry = TRUSTED_KEYS.get(kid)
    if not trusted_entry:
        return create_error_response(400, "UNKNOWN_KEY_ID", f"Key id '{kid}' is not in the trusted key store")

    alg, pub_key_bytes = trusted_entry
    if alg != "ed25519":
        return create_error_response(400, "UNKNOWN_KEY_ID", f"Unsupported algorithm in trust store: {alg}")

    # Verify signature
    if not verify_signature_ed25519(hash_bytes=hash_bytes_val, sig_b64=sig_data.sig, public_key_bytes=pub_key_bytes):
        return create_error_response(400, "BAD_SIGNATURE", "Signature verification failed")

    # Immutability check
    if name in ACTIONS_DB and version in ACTIONS_DB[name]:
        existing = ACTIONS_DB[name][version]
        existing_hash = sha256_prefixed_hex(canonical_dumps(existing["schema"]))
        if existing_hash == hash_hex:
            # Idempotent — same payload, return 200
            return JSONResponse(status_code=200, content={
                "name": name,
                "version": version,
                "schema": schema_obj,
                "hash": hash_hex,
                "signature": {"alg": sig_data.alg, "kid": sig_data.kid, "sig": sig_data.sig},
                "verified": True,
                "verify_error": None
            })
        else:
            return create_error_response(409, "IMMUTABLE_VERSION_CONFLICT",
                f"Version '{version}' of '{name}' already exists with a different schema")

    # Store
    if name not in ACTIONS_DB:
        ACTIONS_DB[name] = {}

    ACTIONS_DB[name][version] = {
        "schema": schema_obj,
        "signature": {
            "alg": sig_data.alg,
            "kid": sig_data.kid,
            "sig": sig_data.sig,
        }
    }

    return ActionVersionResponse(
        name=name,
        version=version,
        schema=schema_obj,
        hash=hash_hex,
        signature=sig_data,
        verified=True,
        verify_error=None
    )
