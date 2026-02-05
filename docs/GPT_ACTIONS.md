# Custom GPT Actions — Action-Registry

*Exposing the registry to OpenAI Custom GPTs via OpenAPI.*

---

## Why GPT Actions

Custom GPTs use "Actions" — HTTP endpoints described by an OpenAPI schema — to interact with external services. The Action-Registry's REST API is already built on FastAPI, which auto-generates OpenAPI specs at `/openapi.json`. This means GPT integration is nearly free: the schema already exists, the endpoints already work, the auth model (Bearer token) already matches what OpenAI expects.

A Custom GPT connected to the Action-Registry can:
- Discover what capabilities are available in the ecosystem
- Fetch action schemas to understand tool contracts
- Verify that actions are properly signed before recommending them
- Publish new action schemas on behalf of a developer

This bridges the gap between the OpenAI GPT ecosystem and the ACE/IntelliSwarm agent ecosystem. A developer working in ChatGPT can query the same registry that Claude Code agents, ACE cognitive layers, and IntelliSwarm coordinators use.

---

## Auth Model

OpenAI Custom GPT Actions support several authentication schemes. The Action-Registry uses:

- **Scheme:** Bearer token (`Authorization: Bearer <token>`)
- **Token source:** `ACTION_REGISTRY_API_KEY` environment variable
- **Scope:** Read endpoints (discover, fetch, verify) can be unauthenticated. Write endpoints (publish, deprecate) require the Bearer token.

This matches the DevOpsAssistant pattern already established in the workspace.

### OpenAI Actions Auth Configuration

When configuring the Custom GPT Action:
- **Authentication type:** API Key
- **Auth type:** Bearer
- **API Key:** The value of `ACTION_REGISTRY_API_KEY`

---

## Endpoints for GPT Consumption

### Read Endpoints (no auth required)

| Method | Path | GPT Use Case |
|--------|------|-------------|
| `GET /actions` | "What actions are available?" |
| `GET /actions/{name}/versions/{version}` | "Show me the schema for ssh.exec v2.0.0" |

### Write Endpoints (Bearer auth required)

| Method | Path | GPT Use Case |
|--------|------|-------------|
| `POST /actions/{name}/versions/{version}` | "Publish this new action schema" |

### Planned Endpoints

| Method | Path | GPT Use Case |
|--------|------|-------------|
| `GET /actions/{name}/versions/{version}/verify` | "Is this action properly signed?" |
| `GET /actions?q={search}` | "Find actions related to Docker" |
| `POST /actions/{name}/versions/{version}/deprecate` | "Deprecate this action version" |
| `GET /actions/{name}/diff?from=1.0.0&to=2.0.0` | "What changed between versions?" |
| `GET /actions/{name}/compatibility` | "Which versions are compatible?" |

---

## OpenAPI Schema

FastAPI generates the OpenAPI spec automatically. The spec is available at:

```
GET /openapi.json
```

The Custom GPT imports this URL directly. All endpoint descriptions, parameter types, request/response schemas, and error codes are included.

### Improving the Schema for GPTs

To make the OpenAPI spec more useful for GPTs, the FastAPI app should include:

**Rich endpoint descriptions** — GPTs use these to decide which endpoint to call:
```python
@app.get(
    "/actions",
    response_model=ActionList,
    summary="Discover registered actions",
    description=(
        "List all actions in the registry with their available versions. "
        "Returns action names, latest version, all version numbers, and descriptions. "
        "Use this to find what capabilities are available before fetching a specific schema."
    ),
)
```

**Detailed model descriptions** — GPTs use these to understand response fields:
```python
class ActionVersionResponse(BaseModel):
    name: str = Field(..., description="The action's unique identifier (e.g., 'ssh.exec')")
    version: str = Field(..., description="The version string (SemVer format, e.g., '2.0.0')")
    verified: bool = Field(..., description="Whether the signature was verified against a trusted key")
    verify_error: Optional[str] = Field(None, description="If verified is false, explains why")
```

**Example values** — Help GPTs construct valid requests:
```python
class PublishRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [{
                "schema": {
                    "description": "Execute a command via SSH",
                    "parameters": {
                        "host": {"type": "string"},
                        "command": {"type": "string"}
                    }
                },
                "signature": {
                    "alg": "ed25519",
                    "kid": "dev-root-1",
                    "sig": "base64:..."
                }
            }]
        }
    }
```

---

## Custom GPT System Prompt (Suggested)

When creating the Custom GPT, use a system prompt that explains the registry:

```
You are an Action-Registry assistant. You help developers discover, inspect,
and manage signed action schemas in the Action-Registry.

The Action-Registry is a versioned store of callable action contracts used by
AI agent swarms (ACE and IntelliSwarm). Each action is described by a JSON
schema and protected by an Ed25519 signature.

Key concepts:
- Actions are immutable: once published, a (name, version) pair cannot change.
- Signatures ensure tamper detection: verified=true means the schema is trusted.
- Actions use dotted namespaces: ssh.exec, files.move, docker.deploy.
- Versions follow SemVer: 1.0.0, 1.1.0, 2.0.0.

When users ask about capabilities, use the discover endpoint first.
When users want details, fetch the specific version.
Always note the verification status when showing action details.
```

---

## Example GPT Conversations

**User:** "What actions are available for Docker?"

**GPT flow:**
1. Calls `GET /actions`
2. Filters results for names containing "docker"
3. Presents: `docker.build@1.0.0`, `docker.deploy@2.0.0`, `docker.push@1.0.0`

---

**User:** "Show me the schema for docker.deploy version 2.0.0"

**GPT flow:**
1. Calls `GET /actions/docker.deploy/versions/2.0.0`
2. Presents the schema with parameters, signature info, and verification status
3. Notes: "This action is verified (signed by key `infra-deploy-1`)"

---

**User:** "Is files.move v1.0.0 safe to use?"

**GPT flow:**
1. Calls `GET /actions/files.move/versions/1.0.0`
2. Checks `verified` field
3. Responds: "Yes, files.move@1.0.0 is verified. Signed by dev-root-1 using Ed25519. The schema hash is sha256:abc123..."

---

## Relationship to MCP Server

The GPT Actions surface and the MCP server are complementary, not redundant:

| Aspect | MCP Server | GPT Actions |
|--------|-----------|-------------|
| **Consumer** | Claude Code, MCP-compatible agents | OpenAI Custom GPTs |
| **Transport** | stdio (local) | HTTPS (remote) |
| **Auth** | Implicit (local process) | Bearer token |
| **Use case** | Agent-to-registry (machine-to-machine) | Developer-to-registry (human-in-the-loop) |
| **Latency** | Sub-millisecond (local) | Network-dependent |
| **Publish** | Direct (agent has signing keys) | Mediated (developer provides signed payload) |

Both interfaces share the same core logic and data store. An action published via GPT Actions is immediately discoverable via MCP, and vice versa.
