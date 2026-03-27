import json
import logging
import time
import uuid
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import canonical_dumps, sha256_bytes, sha256_prefixed_hex, verify_signature_ed25519
from app.db import async_engine, get_db
from app.models import Action, ActionVersion, Base
from app.schemas import (
    ActionItem,
    ActionList,
    ActionVerifyResponse,
    ActionVersionResponse,
    ErrorResponse,
    PublishRequest,
    SignatureBlock,
)
from app.settings import API_KEY, TRUSTED_KEYS

app = FastAPI(
    title="Action Registry API",
    description=(
        "Discover, fetch, verify, and publish signed action schemas. "
        "Responses include deterministic hash and signature verification state."
    ),
    version="0.1.0",
)

logger = logging.getLogger("action_registry")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

METRICS = {
    "http_requests_total": defaultdict(int),
    "http_request_duration_seconds_count": defaultdict(int),
    "http_request_duration_seconds_sum": defaultdict(float),
    "http_request_duration_seconds_bucket_raw": defaultdict(int),
    "publish_total": 0,
    "verify_pass_total": 0,
    "verify_fail_total": 0,
}
LATENCY_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


def create_error_response(
    status_code: int,
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    content = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
    return JSONResponse(status_code=status_code, content=content)


def _version_sort_key(version: str) -> tuple[int, int, int, str]:
    parts = version.split(".")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return (int(parts[0]), int(parts[1]), int(parts[2]), "")
    return (0, 0, 0, version)


def _verify_action_version(av: ActionVersion) -> tuple[bool, Optional[str]]:
    canonical_bytes = canonical_dumps(av.schema_json)
    hash_bytes_val = sha256_bytes(canonical_bytes)

    trusted_entry = TRUSTED_KEYS.get(av.sig_kid)
    if not trusted_entry:
        METRICS["verify_fail_total"] += 1
        return False, "Unknown key id"

    alg, pub_key_bytes = trusted_entry
    if alg != "ed25519":
        METRICS["verify_fail_total"] += 1
        return False, f"Unsupported algorithm in trust store: {alg}"

    is_valid = verify_signature_ed25519(
        hash_bytes=hash_bytes_val,
        sig_b64=av.sig_b64,
        public_key_bytes=pub_key_bytes,
    )

    if is_valid:
        METRICS["verify_pass_total"] += 1
        return True, None

    METRICS["verify_fail_total"] += 1
    return False, "Bad signature"


@lru_cache(maxsize=1)
def get_expected_migration_head() -> Optional[str]:
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    if not alembic_ini.exists():
        return None
    config = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start

    response.headers["x-request-id"] = request_id

    status_code = response.status_code
    route = request.url.path
    method = request.method
    METRICS["http_requests_total"][(method, route, str(status_code))] += 1
    METRICS["http_request_duration_seconds_count"][(method, route)] += 1
    METRICS["http_request_duration_seconds_sum"][(method, route)] += elapsed

    for bucket in LATENCY_BUCKETS:
        if elapsed <= bucket:
            METRICS["http_request_duration_seconds_bucket_raw"][(method, route, str(bucket))] += 1
            break
    else:
        METRICS["http_request_duration_seconds_bucket_raw"][(method, route, "+Inf")] += 1

    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": method,
                "path": route,
                "status_code": status_code,
                "latency_seconds": round(elapsed, 6),
            }
        )
    )
    return response


@app.on_event("startup")
async def on_startup() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get(
    "/livez",
    summary="Liveness Probe",
    description="Process-level health check used by orchestration to confirm the service is running.",
)
def livez() -> Dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/readyz",
    summary="Readiness Probe",
    description="Checks database connectivity and ensures the current Alembic revision matches expected head.",
)
async def readyz(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(text("SELECT version_num FROM alembic_version"))
        versions = {row[0] for row in result.fetchall()}
        expected_head = get_expected_migration_head()

        if expected_head and versions != {expected_head}:
            return create_error_response(
                503,
                "NOT_READY_MIGRATIONS",
                "Database schema is not at expected migration revision",
                {"expected": expected_head, "current": sorted(versions)},
            )
        return {"status": "ready"}
    except Exception as exc:
        return create_error_response(503, "NOT_READY", "Database not ready", {"reason": str(exc)})


@app.get(
    "/healthz",
    summary="Basic Health Check",
    description="Simple health endpoint returning an OK status.",
)
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/metrics",
    summary="Prometheus Metrics",
    description=(
        "Exposes request, publish, and verification metrics in Prometheus text format. "
        "Includes histogram bucket/count/sum for request duration."
    ),
)
def metrics() -> Response:
    lines = []

    lines.append("# TYPE action_registry_publish_total counter")
    lines.append(f"action_registry_publish_total {METRICS['publish_total']}")
    lines.append("# TYPE action_registry_verify_pass_total counter")
    lines.append(f"action_registry_verify_pass_total {METRICS['verify_pass_total']}")
    lines.append("# TYPE action_registry_verify_fail_total counter")
    lines.append(f"action_registry_verify_fail_total {METRICS['verify_fail_total']}")

    lines.append("# TYPE action_registry_http_requests_total counter")
    for (method, route, status), count in METRICS["http_requests_total"].items():
        lines.append(
            "action_registry_http_requests_total"
            f'{{method="{method}",route="{route}",status="{status}"}} {count}'
        )

    lines.append("# TYPE action_registry_http_request_duration_seconds histogram")
    for method, route in sorted(METRICS["http_request_duration_seconds_count"].keys()):
        cumulative = 0
        for bucket in LATENCY_BUCKETS:
            key = (method, route, str(bucket))
            cumulative += METRICS["http_request_duration_seconds_bucket_raw"][key]
            lines.append(
                "action_registry_http_request_duration_seconds_bucket"
                f'{{method="{method}",route="{route}",le="{bucket}"}} {cumulative}'
            )
        count = METRICS["http_request_duration_seconds_count"][(method, route)]
        lines.append(
            "action_registry_http_request_duration_seconds_bucket"
            f'{{method="{method}",route="{route}",le="+Inf"}} {count}'
        )
        lines.append(
            "action_registry_http_request_duration_seconds_count"
            f'{{method="{method}",route="{route}"}} {count}'
        )
        lines.append(
            "action_registry_http_request_duration_seconds_sum"
            f'{{method="{method}",route="{route}"}} '
            f'{METRICS["http_request_duration_seconds_sum"][(method, route)]:.6f}'
        )

    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get(
    "/actions",
    response_model=ActionList,
    summary="Discover Actions",
    description=(
        "Lists registered action headers. Supports optional text query, signer key filter, "
        "and pagination controls."
    ),
)
async def list_actions(
    q: str = Query(default="", description="Case-insensitive substring search"),
    kid: Optional[str] = Query(default=None, description="Filter by signer key id"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ActionList:
    rows = (await db.execute(select(ActionVersion))).scalars().all()

    grouped: dict[str, list[ActionVersion]] = defaultdict(list)
    q_lower = q.lower().strip()

    for row in rows:
        if kid and row.sig_kid != kid:
            continue
        description = str(row.schema_json.get("description", ""))
        if q_lower and q_lower not in row.name.lower() and q_lower not in description.lower():
            continue
        grouped[row.name].append(row)

    action_names = sorted(grouped.keys())
    page_names = action_names[offset : offset + limit]

    items = []
    for name in page_names:
        versions = sorted((row.version for row in grouped[name]), key=_version_sort_key)
        latest = versions[-1] if versions else "0.0.0"
        latest_row = next((row for row in grouped[name] if row.version == latest), None)
        description = None
        if latest_row:
            description = latest_row.schema_json.get("description")

        items.append(
            ActionItem(
                name=name,
                latest_version=latest,
                versions=versions,
                description=description,
            )
        )

    return ActionList(items=items)


@app.get(
    "/actions/{name}/versions/{version}",
    response_model=ActionVersionResponse,
    summary="Fetch Versioned Action Schema",
    description=(
        "Returns a specific action version including schema payload, stored signature block, "
        "hash, and live verification result."
    ),
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def get_action_version(name: str, version: str, db: AsyncSession = Depends(get_db)):
    action = await db.get(Action, name)
    if not action:
        return create_error_response(404, "ACTION_NOT_FOUND", f"Action '{name}' not found")

    row_result = await db.execute(
        select(ActionVersion).where(ActionVersion.name == name, ActionVersion.version == version)
    )
    row = row_result.scalars().first()
    if not row:
        return create_error_response(404, "VERSION_NOT_FOUND", f"Version '{version}' not found")

    is_verified, verify_error = _verify_action_version(row)

    return ActionVersionResponse(
        name=name,
        version=version,
        schema=row.schema_json,
        hash=row.hash,
        signature=SignatureBlock(alg=row.sig_alg, kid=row.sig_kid, sig=row.sig_b64),
        verified=is_verified,
        verify_error=verify_error,
    )


@app.get(
    "/actions/{name}/versions/{version}/verify",
    response_model=ActionVerifyResponse,
    summary="Verify Action Signature",
    description=(
        "Performs signature verification for a stored action version and returns verification state "
        "without returning the full schema payload."
    ),
    responses={404: {"model": ErrorResponse}},
)
async def verify_action_version(name: str, version: str, db: AsyncSession = Depends(get_db)):
    action = await db.get(Action, name)
    if not action:
        return create_error_response(404, "ACTION_NOT_FOUND", f"Action '{name}' not found")

    row_result = await db.execute(
        select(ActionVersion).where(ActionVersion.name == name, ActionVersion.version == version)
    )
    row = row_result.scalars().first()
    if not row:
        return create_error_response(404, "VERSION_NOT_FOUND", f"Version '{version}' not found")

    is_verified, verify_error = _verify_action_version(row)

    return ActionVerifyResponse(
        name=name,
        version=version,
        verified=is_verified,
        kid=row.sig_kid,
        alg=row.sig_alg,
        hash=row.hash,
        verify_error=verify_error,
    )


@app.post(
    "/actions/{name}/versions/{version}",
    status_code=201,
    response_model=ActionVersionResponse,
    summary="Publish Action Version",
    description=(
        "Publishes a signed action schema for a specific (name, version). Enforces API key auth, "
        "signature verification, and immutable version conflict protection."
    ),
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def publish_action(
    name: str,
    version: str,
    body: PublishRequest,
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not API_KEY or not x_api_key or x_api_key != API_KEY:
        return create_error_response(401, "UNAUTHORIZED", "Invalid or missing API key")

    schema_obj = body.schema_
    sig_data = body.signature

    canonical_bytes = canonical_dumps(schema_obj)
    hash_bytes_val = sha256_bytes(canonical_bytes)
    hash_hex = sha256_prefixed_hex(canonical_bytes)

    trusted_entry = TRUSTED_KEYS.get(sig_data.kid)
    if not trusted_entry:
        return create_error_response(
            400,
            "UNKNOWN_KEY_ID",
            f"Key id '{sig_data.kid}' is not in the trusted key store",
        )

    alg, pub_key_bytes = trusted_entry
    if alg != "ed25519":
        return create_error_response(400, "UNKNOWN_KEY_ID", f"Unsupported algorithm in trust store: {alg}")

    if not verify_signature_ed25519(
        hash_bytes=hash_bytes_val,
        sig_b64=sig_data.sig,
        public_key_bytes=pub_key_bytes,
    ):
        METRICS["verify_fail_total"] += 1
        return create_error_response(400, "BAD_SIGNATURE", "Signature verification failed")

    METRICS["verify_pass_total"] += 1

    existing_result = await db.execute(
        select(ActionVersion).where(ActionVersion.name == name, ActionVersion.version == version)
    )
    existing = existing_result.scalars().first()
    if existing:
        if existing.hash == hash_hex:
            return JSONResponse(
                status_code=200,
                content={
                    "name": name,
                    "version": version,
                    "schema": existing.schema_json,
                    "hash": existing.hash,
                    "signature": {
                        "alg": existing.sig_alg,
                        "kid": existing.sig_kid,
                        "sig": existing.sig_b64,
                    },
                    "verified": True,
                    "verify_error": None,
                },
            )
        return create_error_response(
            409,
            "IMMUTABLE_VERSION_CONFLICT",
            f"Version '{version}' of '{name}' already exists with a different schema",
        )

    action = await db.get(Action, name)
    if not action:
        action = Action(name=name)
        db.add(action)

    row = ActionVersion(
        name=name,
        version=version,
        schema_json=schema_obj,
        hash=hash_hex,
        sig_alg=sig_data.alg,
        sig_kid=sig_data.kid,
        sig_b64=sig_data.sig,
    )
    db.add(row)
    await db.commit()

    METRICS["publish_total"] += 1

    return ActionVersionResponse(
        name=name,
        version=version,
        schema=schema_obj,
        hash=hash_hex,
        signature=sig_data,
        verified=True,
        verify_error=None,
    )
