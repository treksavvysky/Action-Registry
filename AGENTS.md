# AGENTS.md — Action-Registry MVP Delivery Contract

This file is the implementation contract for a coding agent. Follow it literally.  
MVP goal: **discover + version + verify** for signed action schemas.

---

## Mission

Ship **Action-Registry MVP (discover + version + sign/verify)**:

- **Discover**: list all actions and available versions.
- **Version**: fetch a specific schema by `(name, version)`.
- **Verify**: validate the schema’s signature against configured trusted public keys.
- **Immutability**: `(name, version)` is immutable once stored.

This service becomes the interoperability bus: every agent/tool-runner can discover contracts, pin versions, and reject tampered definitions.

---

## Non-Negotiables

### 1) Canonicalization
Signature verification MUST use a deterministic payload.

**Canonical JSON rules (MVP):**
- UTF-8 encoding
- recursive key sorting for all objects
- no insignificant whitespace
- array order preserved
- avoid float normalization surprises (prefer integers/strings; if floats exist, do not “pretty” round)

Implement a `canonical_dumps(obj) -> bytes` utility and test it for determinism.

### 2) What gets signed
Compute:

- `canonical_payload = canonical_dumps(schema_without_signature_fields)`
- `hash = SHA-256(canonical_payload)`

Verify a **detached signature** over the hash (recommended) or over the canonical payload.

**Schema fields excluded from hashing/signing:**
- `hash`
- `signature` (and nested fields like `sig`, `kid`, `alg`)
- `verified` (response-only)

### 3) Immutability
If a client tries to publish a schema that matches an existing `(name, version)` with different bytes/hash → **reject** with conflict.

---

## Recommended Crypto

Use **Ed25519** for MVP unless there’s a strong reason not to.

Trusted keys are provided by config. Each schema includes a `kid` so the service selects the right public key.

---

## API Contract

### Endpoints

#### 1) Discover
`GET /actions`

Returns headers only (not full schemas). Minimum fields:

```json
{
  "items": [
    {
      "name": "files.move",
      "latest_version": "1.1.0",
      "versions": ["1.0.0", "1.1.0"],
      "description": "Move a file from A to B (optional)"
    }
  ]
}

2) Versioned fetch
GET /actions/{name}/versions/{version}

Returns the stored schema, signature block, hash, and verification result:

{
  "name": "files.move",
  "version": "1.1.0",
  "schema": { "...": "..." },
  "hash": "sha256:…",
  "signature": {
    "alg": "ed25519",
    "kid": "dev-root-1",
    "sig": "base64:…"
  },
  "verified": true
}

3) Verify (optional but recommended)
If you implement separate verification:

GET /actions/{name}/versions/{version}/verify

{
  "name": "files.move",
  "version": "1.1.0",
  "verified": true,
  "kid": "dev-root-1",
  "alg": "ed25519",
  "hash": "sha256:…"
}

Errors & Status Codes (stable)

All errors should return JSON:

{
  "error": {
    "code": "VERSION_NOT_FOUND",
    "message": "Human readable message",
    "details": { "optional": "context" }
  }
}

Status + codes:
	•	404 ACTION_NOT_FOUND
	•	404 VERSION_NOT_FOUND
	•	400 UNKNOWN_KEY_ID
	•	400 BAD_SIGNATURE
	•	409 IMMUTABLE_VERSION_CONFLICT
	•	401 UNAUTHORIZED (if publish/admin endpoints are protected)

⸻

Data Model (Postgres)

Use Postgres + SQLAlchemy. Suggested tables:

actions
	•	name (PK)

action_versions
	•	id (PK)
	•	name (FK to actions.name, indexed)
	•	version (string, indexed)
	•	schema_json (JSONB)
	•	hash (string)
	•	sig_alg (string)
	•	sig_kid (string)
	•	sig_b64 (text)
	•	created_at (timestamp)
	•	optional: deprecated (bool), deprecation_reason (text)

Uniqueness constraint:
	•	unique (name, version)

⸻

Auth (MVP)

Endpoints are read-only in MVP by default.

If you add a publish endpoint, protect it via:
	•	X-API-Key: <token>
	•	token configured via env var

⸻

Config

Provide .env.example with at least:
	•	DATABASE_URL=postgresql+psycopg://...
	•	ACTION_REGISTRY_API_KEY=... (only if you implement publish)
	•	trusted keys source:
	•	either TRUSTED_KEYS_JSON='[{"kid":"...","alg":"ed25519","public_key":"base64:..."}]'
	•	or mount trusted_keys.json and reference via TRUSTED_KEYS_PATH=...

Trusted key entry format:

[
  { "kid": "dev-root-1", "alg": "ed25519", "public_key": "base64:..." }
]


⸻

Minimal Publish Story (choose one)

Pick ONE path and implement cleanly:

Option A — Read-only registry (fastest MVP)

Schemas are seeded into DB via a script or migration. API only lists/fetches/verifies.

Option B — Authenticated publish endpoint (still MVP-safe)

Add:
	•	POST /actions/{name}/versions/{version}

Request body includes:
	•	schema object
	•	signature block (kid, alg, sig)

Server behavior:
	•	compute canonical payload + hash
	•	verify signature
	•	store if new
	•	reject if existing and different (immutability)

⸻

Definition of Done (Acceptance Tests)

Implement these as pytest integration tests (FastAPI TestClient) and/or curl scripts.

A) Canonicalization determinism

Given the same schema object with keys in different order:
	•	canonical bytes MUST be identical
	•	sha256 MUST match

Test: reorder keys, hash equality.

B) Signature verification succeeds

Given a schema signed by trusted kid:
	•	GET /actions/{name}/versions/{version} returns verified: true

C) Tamper detection

If ANY byte in stored schema changes:
	•	verified: false OR request fails with BAD_SIGNATURE (pick one behavior and be consistent)
	•	verification endpoint (if present) returns verified: false with reason

D) Discover lists versions

After inserting two versions of same action:
	•	GET /actions includes that action name and both versions
	•	latest_version is correct (SemVer sort or DB max rule—document which)

E) Not found behavior
	•	unknown action → 404 ACTION_NOT_FOUND
	•	known action but unknown version → 404 VERSION_NOT_FOUND

F) Immutability conflict (if publish exists)

Publish (name, version) twice with different schema bytes:
	•	second publish → 409 IMMUTABLE_VERSION_CONFLICT

⸻

Implementation Notes (don’t get fancy)
	•	Keep the service small: one FastAPI app, one DB session layer, one crypto utility module.
	•	Avoid event streams, websockets, revocation, or governance workflows in MVP.
	•	Prefer clear, explicit code over “framework cleverness.”
	•	Put canonicalization + hashing + verify in a dedicated module with tests.

⸻

Repo Expectations

Suggested structure
	•	app/main.py — FastAPI app + routes
	•	app/db.py — engine/session setup
	•	app/models.py — SQLAlchemy models
	•	app/schemas.py — Pydantic response/request models
	•	app/crypto.py — canonicalize/hash/signature verification
	•	app/settings.py — env/config loading
	•	tests/ — unit + integration tests
	•	docker-compose.yml — api + postgres (and optional admin tooling)

Commands
	•	docker compose up --build
	•	pytest

⸻

Output Quality Bar
	•	Deterministic hashing + signature verification works reliably.
	•	Endpoints match contract (shapes + codes).
	•	Tests cover the acceptance suite above.
	•	README stays aligned with behavior (no aspirational promises).

Ship the MVP. Then we iterate.

