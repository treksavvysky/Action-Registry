from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ActionItem(BaseModel):
    name: str = Field(..., description="Unique action identifier (dotted namespace).", examples=["files.move"])
    latest_version: str = Field(..., description="Highest available version for this action.", examples=["1.1.0"])
    versions: List[str] = Field(..., description="All published versions for the action.")
    description: Optional[str] = Field(default=None, description="Short human-readable action summary.")

class ActionList(BaseModel):
    items: List[ActionItem] = Field(..., description="Collection of action headers.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "name": "files.move",
                        "latest_version": "1.1.0",
                        "versions": ["1.0.0", "1.1.0"],
                        "description": "Move a file from A to B (optional overwrite)",
                    }
                ]
            }
        }
    }

class SignatureBlock(BaseModel):
    alg: str = Field(..., description="Signature algorithm identifier.", examples=["ed25519"])
    kid: str = Field(..., description="Trusted key ID used for verification.", examples=["dev-root-1"])
    sig: str = Field(..., description="Detached base64 signature over canonical payload hash.", examples=["base64:abc..."])

class ActionVersionResponse(BaseModel):
    name: str = Field(..., description="Unique action identifier.")
    version: str = Field(..., description="Action version.")
    schema_: Dict[str, Any] = Field(..., alias="schema", description="Published action schema payload.")
    hash: str = Field(..., description="Canonical payload SHA-256 digest.", examples=["sha256:abc123..."])
    signature: SignatureBlock = Field(..., description="Stored detached signature metadata.")
    verified: bool = Field(..., description="True when signature validates against configured trust store.")
    verify_error: Optional[str] = Field(default=None, description="Reason verification failed when verified=false.")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "name": "files.move",
                "version": "1.1.0",
                "schema": {"description": "Move a file", "parameters": {"source": {"type": "string"}}},
                "hash": "sha256:abc123...",
                "signature": {"alg": "ed25519", "kid": "dev-root-1", "sig": "base64:..."},
                "verified": True,
                "verify_error": None,
            }
        },
    }


class ActionVerifyResponse(BaseModel):
    name: str = Field(..., description="Unique action identifier.")
    version: str = Field(..., description="Action version.")
    verified: bool = Field(..., description="True when signature validates against configured trust store.")
    kid: str = Field(..., description="Key ID used to verify signature.")
    alg: str = Field(..., description="Algorithm used for verification.")
    hash: str = Field(..., description="Canonical payload SHA-256 digest.")
    verify_error: Optional[str] = Field(default=None, description="Reason verification failed when verified=false.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "files.move",
                "version": "1.1.0",
                "verified": True,
                "kid": "dev-root-1",
                "alg": "ed25519",
                "hash": "sha256:abc123...",
                "verify_error": None,
            }
        }
    }

class PublishRequest(BaseModel):
    schema_: Dict[str, Any] = Field(..., alias="schema", description="Schema object to publish.")
    signature: SignatureBlock = Field(..., description="Detached signature metadata for the submitted schema.")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "schema": {
                    "description": "Move a file from A to B",
                    "parameters": {"source": {"type": "string"}, "destination": {"type": "string"}},
                },
                "signature": {"alg": "ed25519", "kid": "dev-root-1", "sig": "base64:..."},
            }
        },
    }


class ErrorDetails(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable error message.")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Optional structured context for debugging.")

class ErrorResponse(BaseModel):
    error: ErrorDetails = Field(..., description="Error envelope.")
