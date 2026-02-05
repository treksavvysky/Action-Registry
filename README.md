# Action-Registry

Action-Registry is a lightweight clearing-house where human developers and autonomous agents can publish, discover, and version callable actions.

Think of it as an npm-style registry for tool/function specs: each action is described by a signed JSON schema, stored under (name, version), and served via a small FastAPI service. The signature verification is the point: it prevents silent drift and tampering.

Why it exists
	•	Shared tool marketplace: IntelliSwarm / ACE agents can look up move_file@2.1.0 and wire it instantly.
	•	Single source of truth: no more copy-pasting specs across repos; one endpoint returns the canonical definition.
	•	Governance & traceability: SHA-256 digests + signatures allow reproducible pipelines and trustable interoperability.

MVP scope

This repo ships an MVP with three core behaviors:
	1.	Discover: list available actions and their versions.
	2.	Version: fetch a schema by name + version.
	3.	Verify: validate the schema’s signature against configured trusted public keys.

Immutability rule: once published, an (action_name, version) record is immutable. Any change requires a new version.

Architecture at a glance

Layer	Tech	Notes
API	FastAPI	REST endpoints for discovery + retrieval + verification
Data	PostgreSQL (SQLAlchemy)	JSONB stores schema; columns enable efficient version queries
Auth	API-Key header	Intended for internal use; upgrade path to JWT/OAuth later
CI/CD	GitHub Actions + Docker	tests, lint, build image on PRs

Concepts

What is an “Action”?

An action is a callable capability described by a schema and a signature:
	•	name: stable identifier (e.g., ssh.exec, files.move)
	•	version: immutable version string (prefer SemVer: 1.2.0)
	•	schema: JSON object describing inputs/outputs + metadata
	•	hash: SHA-256 digest of the canonical schema payload
	•	signature: detached signature over the schema hash
	•	kid: key id used to verify the signature

Canonicalization (non-negotiable)

Signatures only work if the payload is deterministic.

The registry computes a canonical representation of the schema (sorted keys, stable JSON encoding), computes sha256, and verifies the detached signature using the configured public key for the given kid.

API

List actions (discover)

GET /actions

Returns action headers (not full schemas), typically:
	•	action name
	•	available versions (or latest + versions)
	•	short description (if present)
	•	verification status summary (optional)

Example response shape:

{
  "items": [
    {
      "name": "files.move",
      "latest_version": "1.1.0",
      "versions": ["1.0.0", "1.1.0"]
    }
  ]
}

Fetch action schema by name + version (version)

GET /actions/{name}/versions/{version}

Returns the canonical stored schema plus signature metadata and verification result:

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

Verify action signature (verify)

Either:
	•	verification is performed automatically on fetch (verified: true/false), or
	•	a dedicated endpoint exists:

GET /actions/{name}/versions/{version}/verify

Example:

{
  "name": "files.move",
  "version": "1.1.0",
  "verified": true,
  "kid": "dev-root-1",
  "alg": "ed25519",
  "hash": "sha256:…"
}

Error Handling & Codes

Errors are returned in a stable JSON envelope:

```json
{
  "error": {
    "code": "ACTION_NOT_FOUND",
    "message": "Human readable message",
    "details": { ... }
  }
}
```

Common error codes:
	•	ACTION_NOT_FOUND (404)
	•	VERSION_NOT_FOUND (404)

Verification Behavior

When fetching an action version (`GET /actions/{name}/versions/{version}`), the server attempts to verify the signature against the trusted key store.

*   **Success**: Returns `verified: true`.
*   **Failure**: Returns `verified: false` and includes a `verify_error` field (e.g., "Bad signature", "Unknown key id"). The HTTP status code remains 200 OK to allow inspection of the artifact.

Signing model
	•	Recommended algorithm: Ed25519
	•	Trust store: registry loads a set of trusted public keys from config.
	•	Publishing: MVP may support either:
	•	offline publishing (pre-signed schemas stored in DB), or
	•	an authenticated publish endpoint that verifies submitted signatures and then stores the schema.

The MVP goal is that unsigned or improperly signed schemas are not treated as trusted.

Data model (suggested)
	•	actions table: name
	•	action_versions table:
	•	name (FK)
	•	version (string, indexed)
	•	schema_json (JSONB)
	•	hash (string)
	•	sig_alg (string)
	•	sig_kid (string)
	•	sig_b64 (text)
	•	created_at (timestamp)
	•	optional: deprecated (bool), deprecation_reason (text)

Quick start (dev)

git clone https://github.com/your-org/action-registry.git
cd action-registry
docker compose up --build

# Or if already in the repo root:
docker compose up --build

Service listens on:
	•	API: http://localhost:8000
	•	Docs: http://localhost:8000/docs

Configuration

Environment variables (example names; see .env.example):
	•	DATABASE_URL=postgresql+psycopg://…
	•	ACTION_REGISTRY_API_KEY=…
	•	TRUSTED_KEYS_JSON=… (or mount a trusted_keys.json file)

Trusted keys format example:

[
  { "kid": "dev-root-1", "alg": "ed25519", "public_key": "base64:…" }
]

Testing

pytest

Minimum tests expected for MVP:
	•	canonicalization produces deterministic output
	•	signature verification passes/fails correctly
	•	list endpoint returns expected names/versions
	•	fetch endpoint returns verified=false when tampered

Roadmap (post-MVP)
	•	publish endpoint with role-based auth + audit trail
	•	key rotation + revocation
	•	deprecation flags + “unsafe” warnings for clients
	•	event stream for action updates (WebSocket)
	•	compatibility checks between versions

⸻

