# Action-Registry

Action-Registry is a FastAPI service for publishing, discovering, versioning, and verifying signed action schemas.

Core guarantees:
- Deterministic canonicalization for hashing/signature checks
- Immutable `(name, version)` records
- Detached signature verification against configured trusted keys

## Implemented API

### Discovery
- `GET /actions`
- Supports: `q`, `kid`, `offset`, `limit`

### Versioned fetch
- `GET /actions/{name}/versions/{version}`
- Returns schema, hash, signature block, and `verified` status.

### Verify
- `GET /actions/{name}/versions/{version}/verify`
- Returns verification result without full schema payload.

### Publish
- `POST /actions/{name}/versions/{version}`
- Requires `x-api-key` matching `ACTION_REGISTRY_API_KEY`.
- Verifies signature before storing.
- Rejects immutable conflicts with `409 IMMUTABLE_VERSION_CONFLICT`.

### Ops endpoints
- `GET /healthz`
- `GET /livez`
- `GET /readyz`
- `GET /metrics` (Prometheus text format)

## Data model

The service uses SQLAlchemy models backed by `actions` and `action_versions` tables.
`(name, version)` is unique in `action_versions`.

## Configuration

Create `.env` from `.env.example`.

- `DATABASE_URL` (default: `sqlite:///./action_registry.db`)
- `ACTION_REGISTRY_API_KEY`
- `TRUSTED_KEYS_JSON` or `TRUSTED_KEYS_PATH`

Trusted keys format:

```json
[
  { "kid": "dev-root-1", "alg": "ed25519", "public_key": "base64:..." }
]
```

## Local development

```bash
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload
```

API docs: `http://localhost:8000/docs`

## Docker

```bash
docker compose up --build
```

## Testing

```bash
pytest
```

## Notes

- Canonicalization and signature verification logic lives in `app/crypto.py`.
- Verification failures are returned as `verified: false` with `verify_error` on fetch/verify endpoints.
- See `docs/ROADMAP.md` for next phases.
