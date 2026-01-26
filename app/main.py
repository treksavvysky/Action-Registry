from fastapi import FastAPI, HTTPException
from typing import Dict, List, Any
import hashlib

from app.schemas import ActionList, ActionItem, ActionVersionResponse, SignatureBlock
from app.crypto import canonical_dumps, sha256_hex, verify_signature_ed25519

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

@app.get("/actions/{name}/versions/{version}", response_model=ActionVersionResponse)
def get_action_version(name: str, version: str):
    if name not in ACTIONS_DB:
        raise HTTPException(status_code=404, detail="Action not found")

    versions_dict = ACTIONS_DB[name]
    if version not in versions_dict:
        raise HTTPException(status_code=404, detail="Version not found")

    data = versions_dict[version]
    schema_obj = data["schema"]
    sig_data = data["signature"]

    # Compute hash
    canonical_bytes = canonical_dumps(schema_obj)
    hash_hex = sha256_hex(canonical_bytes)

    # Calculate hash bytes for verification
    # AGENTS.md recommends signing the hash.
    hash_bytes = hashlib.sha256(canonical_bytes).digest()

    # Verify stub
    is_verified = verify_signature_ed25519(
        hash_bytes=hash_bytes,
        sig_b64=sig_data["sig"],
        public_key_b64="mock_key" # We don't have key lookup yet
    )

    return ActionVersionResponse(
        name=name,
        version=version,
        schema=schema_obj,
        hash=f"sha256:{hash_hex}",
        signature=SignatureBlock(**sig_data),
        verified=is_verified
    )
