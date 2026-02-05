from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ActionItem(BaseModel):
    name: str
    latest_version: str
    versions: List[str]
    description: Optional[str] = None

class ActionList(BaseModel):
    items: List[ActionItem]

class SignatureBlock(BaseModel):
    alg: str
    kid: str
    sig: str

class ActionVersionResponse(BaseModel):
    name: str
    version: str
    schema_: Dict[str, Any] = Field(..., alias="schema")
    hash: str
    signature: SignatureBlock
    verified: bool
    verify_error: Optional[str] = None

class PublishRequest(BaseModel):
    schema_: Dict[str, Any] = Field(..., alias="schema")
    signature: SignatureBlock

    model_config = {"populate_by_name": True}


class ErrorDetails(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseModel):
    error: ErrorDetails
