# Architecture — Action-Registry in the Ecosystem

*How the registry connects ACE, IntelliSwarm, CWOM, and the broader agent infrastructure.*

---

## System Context

```
                        +---------------------------+
                        |     Aspirational Layer     |
                        |  (namespace permissions,   |
                        |   ethical action filters)   |
                        +------------+--------------+
                                     |
                        +------------v--------------+
                        |   Global Strategy Layer    |
                        |  (version preference,      |
                        |   capability planning)     |
                        +------------+--------------+
                                     |
                        +------------v--------------+
                        |    Agent Model Layer       |
                        | (capability registration,  |
                        |  self-knowledge via        |
     ACE Cognitive      |  published actions)        |
     Architecture       +------------+--------------+
                                     |
                        +------------v--------------+
                        |  Executive Function Layer  |
                        | (action allocation across  |
                        |  agents in the swarm)      |
                        +------------+--------------+
                                     |
                        +------------v--------------+
                        |  Cognitive Control Layer   |
                        | (deprecation monitoring,   |
                        |  event stream consumer)    |
                        +------------+--------------+
                                     |
                        +------------v--------------+
                        |  Task Prosecution Layer    |
                        | (schema fetch, signature   |
                        |  verify, execute)          |
                        +------------+--------------+
                                     |
                    +----------------v-----------------+
                    |                                   |
                    |        ACTION-REGISTRY            |
                    |                                   |
                    |  Discover | Version | Verify |    |
                    |  Publish  | Deprecate | Events   |
                    |                                   |
                    +--------+----------+--------------+
                             |          |
              +--------------+          +--------------+
              |                                        |
    +---------v-----------+              +-------------v-----------+
    |  IntelliSwarm       |              |  CWOM Data Plane        |
    |  Coordinator        |              |                         |
    |                     |              |  Action Schema =        |
    |  Queries registry   |              |    Doctrine Ref         |
    |  for capability     |              |                         |
    |  mapping across     |              |  Action Invocation =    |
    |  all agents in      |              |    Run                  |
    |  the swarm          |              |                         |
    |                     |              |  Execution Output =     |
    |  Decomposes tasks   |              |    Artifact             |
    |  into action        |              |                         |
    |  invocations        |              |  Key Trust State =      |
    |  using version +    |              |    Constraint Snapshot  |
    |  compatibility      |              |                         |
    |  data               |              +-------------------------+
    +---------------------+
```

---

## Component Relationships

### Action-Registry <-> ACE

The registry serves as ACE's **capability catalog**. Each ACE layer interacts with it differently:

**Read path (discovery + verification):**
- Task Prosecution fetches action schemas and verifies signatures before execution.
- Cognitive Control subscribes to the event stream for deprecation and revocation signals.
- Global Strategy queries compatibility graphs to select optimal action versions.
- Agent Model queries the registry to build a self-model of available capabilities.

**Write path (publishing):**
- When ACE develops a new capability, it publishes the action schema to the registry.
- The schema is signed with ACE's signing key, scoped to its namespace.
- Other agents in the swarm can discover and consume the new capability.

**Policy path (filtering):**
- Aspirational Layer defines namespace permissions: which action categories are ethically permissible.
- These permissions are enforced at query time — the registry only returns actions within permitted namespaces.

### Action-Registry <-> IntelliSwarm

The IntelliSwarm coordinator uses the registry as its **capability routing table**:

1. **Task intake**: A high-level task arrives (e.g., "deploy service X to staging").
2. **Decomposition**: The coordinator breaks this into action invocations: `docker.build@1.0.0`, `docker.push@1.0.0`, `k8s.apply@2.0.0`.
3. **Agent selection**: For each action, the coordinator queries the registry to find which agents have that capability registered.
4. **Version negotiation**: The coordinator uses compatibility data to ensure all agents in the workflow use compatible action versions.
5. **Execution**: The coordinator dispatches invocations, and each agent verifies the action signature before executing.
6. **Tracing**: Each invocation is logged as a CWOM Run with the action version, signature kid, and verification status.

### Action-Registry <-> CWOM

CWOM objects map cleanly onto registry concepts:

| CWOM Object | Registry Equivalent | Relationship |
|---|---|---|
| Doctrine Ref | Action schema | The schema *is* the doctrine for how to perform this capability |
| Run | Action invocation | Each Run references the exact `(name, version)` that was executed |
| Artifact | Execution output | Produced by Runs; linked to the action schema that generated them |
| Constraint Snapshot | Trust state | Which keys were trusted, which were revoked, at execution time |
| Context Packet | Invocation parameters | The inputs provided when calling the action |

This mapping means CWOM traceability comes for free: every action invocation is automatically a CWOM Run with full provenance.

---

## Triple Interface Pattern

The Action-Registry exposes the same core logic through three interfaces, each serving a different consumer type. This pattern is consistent with OrcaOps and AI SSH Charon in the workspace.

```
+-------------------+    +-------------------+    +-------------------+
|   MCP Server      |    |   REST API        |    |   GPT Actions     |
|   (stdio)         |    |   (HTTP)          |    |   (OpenAPI)       |
|                   |    |                   |    |                   |
|   Claude Code     |    |   IntelliSwarm    |    |   Custom GPTs     |
|   Desktop agents  |    |   ACE layers      |    |   ChatGPT devs   |
|   Any MCP client  |    |   CI/CD pipelines |    |                   |
|                   |    |   curl / scripts  |    |                   |
+--------+----------+    +--------+----------+    +--------+----------+
         |                        |                        |
         +------------------------+------------------------+
                                  |
                         +--------v---------+
                         |    Core Logic    |
                         |    (core.py)     |
                         |                  |
                         |  discover()      |
                         |  fetch()         |
                         |  verify()        |
                         |  publish()       |
                         |  search()        |
                         +--------+---------+
                                  |
                         +--------v---------+
                         |   Data Layer     |
                         |   (db.py /       |
                         |    in-memory)    |
                         +--------+---------+
                                  |
                         +--------v---------+
                         |   Trust Store    |
                         |   (settings.py)  |
                         +------------------+
```

| Interface | Transport | Auth | Primary Consumer | Docs |
|-----------|-----------|------|------------------|------|
| MCP Server | stdio | Implicit (local) | Claude Code, MCP agents | [MCP_INTEGRATION.md](MCP_INTEGRATION.md) |
| REST API | HTTP | API key header | Programmatic clients, agents | `/docs` (Swagger) |
| GPT Actions | HTTPS | Bearer token | OpenAI Custom GPTs | [GPT_ACTIONS.md](GPT_ACTIONS.md) |

---

## Data Flow

### Publish Flow

```
Publisher (agent or human)
    |
    |  1. Create schema JSON
    |  2. Canonicalize (sorted keys, no whitespace, UTF-8)
    |  3. SHA-256 hash the canonical bytes
    |  4. Sign the hash with Ed25519 private key
    |
    v
POST /actions/{name}/versions/{version}
    {
      "schema": { ... },
      "signature": { "alg": "ed25519", "kid": "...", "sig": "base64:..." }
    }
    |
    |  5. Server verifies API key (authn)
    |  6. Server re-canonicalizes and re-hashes (integrity)
    |  7. Server looks up kid in trust store
    |  8. Server verifies signature against trusted public key
    |  9. Server checks immutability (no existing record with different hash)
    | 10. Server stores if new, returns 201
    |
    v
Stored: { name, version, schema_json, hash, sig_alg, sig_kid, sig_b64, created_at }
```

### Consume Flow

```
Consumer (agent)
    |
    |  1. Query GET /actions to discover available actions
    |  2. Select action by name and version
    |
    v
GET /actions/{name}/versions/{version}
    |
    |  3. Server retrieves stored record
    |  4. Server re-canonicalizes schema, re-hashes
    |  5. Server verifies signature against trust store
    |  6. Server returns schema + verified status
    |
    v
Consumer receives:
    {
      "name": "...",
      "version": "...",
      "schema": { ... },
      "hash": "sha256:...",
      "signature": { "alg": "ed25519", "kid": "...", "sig": "base64:..." },
      "verified": true
    }
    |
    |  7. Consumer checks verified == true
    |  8. Consumer wires action into its execution context
    |  9. Consumer invokes action using schema contract
    | 10. Invocation logged as CWOM Run
    |
    v
Execution
```

---

## Trust Model

### Current (MVP)

```
Flat trust store:
  [
    { kid: "dev-root-1", alg: "ed25519", public_key: "base64:..." },
    { kid: "dev-root-2", alg: "ed25519", public_key: "base64:..." }
  ]

Any key in the store can sign any action.
Verification: signature valid against stored public key = trusted.
```

### Target (Phase 3+)

```
Hierarchical trust:
  Root Key (offline)
    +-- Org: infrastructure (namespace: infra.*, production.*)
    |     +-- Signing Key: infra-deploy-1
    |     +-- Signing Key: infra-deploy-2
    +-- Org: agent-framework (namespace: ace.*, swarm.*)
          +-- Signing Key: ace-agent-1
          +-- Signing Key: intelliswarm-coord-1

Verification:
  1. Leaf key signed the action
  2. Leaf key was delegated by org key
  3. Org key was delegated by root key
  4. Leaf key has scope for the action's namespace
  5. No key in the chain is revoked
```

---

## Current Module Structure

```
app/
  main.py       — FastAPI app, routes (discover, version, publish)
  schemas.py    — Pydantic models (request/response shapes)
  crypto.py     — Canonicalization, SHA-256, Ed25519 verification
  settings.py   — Env-based config (trusted keys, API key)

tests/
  test_main.py   — Integration tests (endpoints, auth, immutability)
  test_crypto.py — Unit tests (canonicalization, hashing, signatures)
```

### Planned Module Additions (Phase 1)

```
app/
  db.py         — SQLAlchemy engine, session factory
  models.py     — ORM models (Action, ActionVersion)
  migrations/   — Alembic migration scripts
```

### Planned Module Additions (Phase 2)

```
app/
  mcp_server.py — FastMCP server (stdio transport, tool definitions)
  core.py       — Shared logic extracted from main.py (used by both REST and MCP)
```

### Planned Module Additions (Phase 5+)

```
app/
  events.py     — WebSocket event stream
  policies.py   — Namespace and deprecation policy enforcement
  reputation.py — Usage tracking and trust scoring
```

---

## Deployment

### Current

```yaml
# docker-compose.yml
services:
  api:     FastAPI on port 8000
  db:      PostgreSQL 15 (provisioned but not yet wired)
```

### Target

```yaml
services:
  api:       FastAPI (multiple replicas behind load balancer)
  db:        PostgreSQL with connection pooling (PgBouncer)
  events:    WebSocket relay for event stream
  metrics:   Prometheus + Grafana for observability
```

Kubernetes deployment with:
- Horizontal pod autoscaling based on request rate
- Readiness/liveness probes on `/healthz`
- Secrets management for trusted keys and API keys
- Network policies restricting publish access to internal agents only
