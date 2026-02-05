# Action-Registry Roadmap

*From signed schema store to the trust layer of autonomous agent ecosystems.*

---

## Where We Are

**MVP (Complete):** Discover, version, verify, and publish signed action schemas. The registry stores immutable `(name, version)` records, verifies Ed25519 signatures against a trusted key store, and serves them over a REST API with API-key-protected publishing.

This is a working foundation. Everything below grows from it.

---

## Phase 1 — Operational Hardening

*Make the MVP production-real.*

### 1.1 PostgreSQL Persistence
- Migrate from in-memory `ACTIONS_DB` to PostgreSQL (models and tables already spec'd in AGENTS.md).
- Alembic migrations for `actions` and `action_versions` tables.
- Connection pooling via SQLAlchemy async sessions.

### 1.2 Dedicated Verify Endpoint
- `GET /actions/{name}/versions/{version}/verify` — returns verification result without the full schema payload.
- Useful for lightweight pre-flight checks by agents that already have the schema cached.

### 1.3 Search and Filter
- `GET /actions?q=ssh` — full-text search across action names and descriptions.
- `GET /actions?kid=dev-root-1` — filter by signing key.
- Pagination (`?offset=0&limit=50`).

### 1.4 Health and Observability
- Structured logging (JSON) with correlation IDs.
- `/metrics` endpoint (Prometheus-compatible) — publish counts, verification pass/fail rates, latency histograms.
- Readiness vs. liveness probes for Kubernetes.

---

## Phase 2 — Integration Surfaces

*Expose the registry to every type of consumer: AI agents, Custom GPTs, and programmatic clients.*

### 2.1 MCP Server
- FastMCP server with stdio transport — makes the registry a native tool for Claude Code and MCP-compatible agents.
- Tools: `action_registry_discover`, `action_registry_fetch`, `action_registry_verify`, `action_registry_publish`, `action_registry_search`.
- Entry point: `action-registry-mcp` console script.
- Self-correcting error responses with `suggestion` field guide the agent to the right next action.
- See [MCP_INTEGRATION.md](MCP_INTEGRATION.md) for full specification.

### 2.2 Custom GPT Actions
- Enrich the existing OpenAPI spec with detailed descriptions, field docs, and examples so Custom GPTs can consume the API directly.
- Bearer token auth aligns with OpenAI's Actions auth model (already implemented).
- Suggested Custom GPT system prompt for an "Action-Registry Assistant."
- See [GPT_ACTIONS.md](GPT_ACTIONS.md) for full specification.

### 2.3 OpenAPI Schema Hardening
- Add `summary`, `description`, and `examples` to all endpoints and Pydantic models.
- Ensure `/openapi.json` is a first-class deliverable, not just an auto-generated artifact.
- Version the API schema: `v1` prefix on endpoints for future breaking changes.

---

## Phase 3 — Trust Chain Architecture

*Move from flat key lists to hierarchical trust.*

### 2.1 Key Hierarchy
The current trust model is a flat list of public keys. Real ecosystems need hierarchy:

```
Root Key (offline, cold storage)
  |
  +-- Org Key: infrastructure-team
  |     +-- Signing Key: infra-deploy-1
  |     +-- Signing Key: infra-deploy-2
  |
  +-- Org Key: agent-framework
        +-- Signing Key: ace-agent-1
        +-- Signing Key: intelliswarm-coord-1
```

- Each key has a scope (which action namespaces it can sign for).
- Delegation chains: a root key signs an org key, which signs individual signing keys.
- The registry validates the full chain, not just the leaf signature.

### 2.2 Key Rotation and Revocation
- `POST /keys/rotate` — publish a new key signed by its parent, marking the old key as superseded.
- Revocation list (CRL-style): revoked keys reject all future publishes and flag existing actions signed by them.
- Grace period: actions signed by a rotated (but not revoked) key remain `verified: true` with a `key_status: "rotated"` annotation.

### 2.3 Signature Algorithms
- Support additional algorithms beyond Ed25519: ECDSA P-256 for environments that require NIST compliance.
- Algorithm negotiation: the `alg` field already exists in the signature block; extend the trust store to map `(kid, alg)` pairs.

---

## Phase 4 — Compatibility and Lifecycle

*Actions don't exist in isolation. They evolve.*

### 3.1 Deprecation
- `POST /actions/{name}/versions/{version}/deprecate` — marks a version as deprecated with a reason and a suggested successor version.
- Deprecated actions return `deprecated: true` and `successor: "2.0.0"` in responses.
- Agents consuming deprecated actions receive a warning header: `X-Action-Deprecated: true`.

### 3.2 Compatibility Declarations
- When publishing version `2.0.0`, the publisher can declare:
  - `breaks: ["1.x"]` — this version is not backward-compatible.
  - `compatible_with: ["1.1.0", "1.2.0"]` — this version is a drop-in replacement.
- `GET /actions/{name}/compatibility` — returns a compatibility graph across all versions.

### 3.3 Schema Diffing
- `GET /actions/{name}/diff?from=1.0.0&to=2.0.0` — returns a structured diff of the schema (added fields, removed fields, type changes).
- Enables agents to programmatically assess migration risk before upgrading.

### 3.4 Namespace Governance
- Action names follow a dotted namespace convention: `ssh.exec`, `files.move`, `docker.deploy`.
- Namespace ownership: only keys with namespace scope can publish under that prefix.
- Prevents squatting and collision in multi-team environments.

---

## Phase 5 — Agent-Native Capabilities

*The registry stops being a lookup table and becomes an active participant in agent coordination.*

### 4.1 Runtime Capability Discovery
- Agents register their available actions with the registry at startup.
- `GET /capabilities?agent=ace-task-prosecutor` — returns all actions an agent can perform.
- `GET /capabilities?action=ssh.exec&version=2.0.0` — returns all agents that can perform this action.
- This turns the registry into a service mesh for capabilities.

### 4.2 Agent-to-Agent Negotiation Protocol
- Agent A needs `analyze.logs@1.x`. It queries the registry.
- The registry returns Agent B as a provider, with a verified schema and trust chain.
- Agent A invokes Agent B using the schema contract — no human introduction required.
- The registry logs the negotiation as a CWOM Run (see Phase 5).

### 4.3 Event Stream
- WebSocket endpoint: `ws://registry/events` — real-time notifications for:
  - New action published
  - Action deprecated
  - Key rotated or revoked
  - Compatibility break declared
- Agents subscribe to namespaces they depend on and react to changes autonomously.

### 4.4 Capability Composition
- Define composite actions: `deploy.full` = `docker.build@1.0.0` + `docker.push@1.0.0` + `k8s.apply@2.0.0`.
- The registry stores composition graphs with dependency ordering.
- Agents can discover and execute composite workflows as single units.

---

## Phase 6 — CWOM and ACE Integration

*The registry becomes a first-class organ in the cognitive architecture.*

### 5.1 CWOM Object Mapping
Actions map directly into the CWOM data model:

| CWOM Object | Action-Registry Equivalent |
|---|---|
| **Doctrine Ref** | Action schema (the "how we do this" contract) |
| **Run** | An invocation of a specific action version by an agent |
| **Artifact** | The output produced by executing the action |
| **Constraint Snapshot** | The key trust state at time of execution |

Every action invocation becomes a traceable CWOM Run with explicit inputs (context packet, constraints, doctrine version) and outputs (artifacts).

### 5.2 ACE Layer Integration
Each ACE cognitive layer interacts with the registry differently:

| ACE Layer | Registry Role |
|---|---|
| **Aspirational** | Defines which action namespaces are ethically permissible |
| **Global Strategy** | Selects which action versions align with strategic goals |
| **Agent Model** | Registers own capabilities; queries others' capabilities |
| **Executive Function** | Allocates action execution across available agents |
| **Cognitive Control** | Monitors action deprecation events; re-routes attention |
| **Task Prosecution** | Fetches action schemas, verifies signatures, executes |

The registry becomes ACE's "motor cortex catalog" — the definitive list of things the entity *can do*, with trust guarantees about each capability.

### 5.3 IntelliSwarm Coordinator Integration
- The IntelliSwarm coordinator queries the registry to build a capability map of all agents in the swarm.
- Task decomposition uses the compatibility graph to find the optimal agent + action version for each subtask.
- The coordinator enforces that only verified, non-deprecated actions are used in production workflows.

---

## Phase 7 — Governance and Intelligence

*The registry becomes the immune system and the memory of the swarm.*

### 6.1 Policy Enforcement
- **Namespace policies**: "All actions under `production.*` must be signed by the infrastructure root key."
- **Deprecation enforcement**: "No agent may invoke a deprecated action without explicit override."
- **Version pinning**: "All agents in the `stable` ring must use action versions from the `verified` channel."
- Policies are themselves versioned and stored as Doctrine Refs in CWOM.

### 6.2 Usage Analytics and Reputation
- Track which actions are consumed, how often, by which agents, with what success rate.
- Actions with high consumption and consistent verification build trust scores.
- Actions that frequently fail verification or cause downstream errors get flagged.
- Publishers who consistently deliver stable, well-signed actions earn reputation — creating a natural quality signal.

### 6.3 Anomaly Detection
- Detect unusual patterns: a sudden spike in publishes from a single key, an action that was stable for months suddenly being republished under new versions rapidly, an agent consuming actions it has never used before.
- Feed anomaly signals into ACE's Cognitive Control layer for attention routing.

### 6.4 Learning from Execution History
- Correlate action versions with Run outcomes in CWOM.
- "Version 2.1.0 of `docker.deploy` has a 98% success rate across 400 runs; version 2.2.0 has a 73% success rate across 50 runs" — this informs ACE's strategy layer about which versions to prefer.
- The registry becomes a feedback loop: publish -> execute -> measure -> learn -> prefer.

---

## Phase 8 — Federation and Scale

*Beyond a single registry instance.*

### 7.1 Multi-Registry Federation
- Organizations run their own registries for internal actions.
- Federation protocol: registries can mirror actions from upstream registries (like Docker Hub mirrors).
- Trust chains span registries: an action published in Registry A and mirrored to Registry B retains its original signature chain.

### 7.2 Content-Addressed Storage
- Actions are stored by their content hash, not just by `(name, version)`.
- Enables deduplication across namespaces and registries.
- `GET /actions/by-hash/sha256:abc123...` — retrieve any action by its content hash regardless of name.

### 7.3 Offline and Edge Support
- Agents operating in disconnected environments can carry a signed snapshot of the registry.
- Snapshot verification ensures the snapshot itself hasn't been tampered with.
- Sync protocol for reconnection: merge local publishes back into the central registry.

---

## Summary

| Phase | Theme | Key Outcome |
|---|---|---|
| MVP | Foundation | Signed schema store with publish, discover, verify |
| 1 | Hardening | PostgreSQL, search, observability |
| 2 | Integration | MCP server, Custom GPT Actions, OpenAPI hardening |
| 3 | Trust | Key hierarchies, rotation, revocation |
| 4 | Lifecycle | Deprecation, compatibility graphs, schema diffs |
| 5 | Agent-Native | Runtime discovery, negotiation, event streams, composition |
| 6 | Integration | CWOM mapping, ACE layer integration, IntelliSwarm coordination |
| 7 | Governance | Policy enforcement, reputation, anomaly detection, learning |
| 8 | Federation | Multi-registry, content-addressed, offline support |

The trajectory: from a schema store to a trust layer to a nervous system to an immune system. Each phase builds on the last. The immutability rule and signature verification established in the MVP are the invariants that make everything above possible.
