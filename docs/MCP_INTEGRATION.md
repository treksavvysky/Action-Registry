# MCP Server — Action-Registry

*How Claude Code and other MCP-compatible agents join the Action-Registry ecosystem.*

---

## Why MCP

The MCP server is the most important integration surface the Action-Registry will have. The REST API serves programmatic consumers. The GPT Actions surface serves Custom GPTs. But the MCP server is how **AI agents become first-class participants** in the registry — discovering capabilities, verifying trust chains, publishing new actions, and wiring schemas into their execution context, all within a single conversation.

When Claude Code connects to the Action-Registry MCP server, it gains the ability to:
- Look up any registered action and understand its contract
- Verify that an action hasn't been tampered with before using it
- Publish new action schemas signed with trusted keys
- Search for capabilities by description, not just by name
- Check whether an action has been deprecated and find its successor

This is the difference between an agent that *uses* tools and an agent that *understands the tool ecosystem it operates in*.

---

## Architecture

The Action-Registry follows the **triple interface pattern** established by OrcaOps and AI SSH Charon:

```
                    +------------------+
                    |   Core Logic     |
                    |                  |
                    |  discover()      |
                    |  fetch()         |
                    |  verify()        |
                    |  publish()       |
                    |  search()        |
                    +--+------+-----+-+
                       |      |     |
            +----------+   +--+--+  +----------+
            |              |     |             |
    +-------v------+ +----v---+ +------v-------+
    | MCP Server   | | REST   | | GPT Actions  |
    | (stdio)      | | API    | | (OpenAPI)     |
    | Claude Code, | | Any    | | Custom GPTs   |
    | Desktop,     | | HTTP   | |               |
    | agents       | | client | |               |
    +--------------+ +--------+ +--------------+
```

All three interfaces share the same core logic. The MCP server is a thin adapter layer using FastMCP, following the patterns established in the workspace.

---

## Framework and Transport

- **Framework:** FastMCP (decorator-based, same as OrcaOps and AI SSH Charon)
- **Transport:** stdio (for Claude Code integration)
- **Entry point:** `action-registry-mcp` console script (defined in `pyproject.toml`)

```toml
[tool.poetry.scripts]
action-registry-mcp = "app.mcp_server:main"
```

---

## MCP Tools

### Discovery and Search

#### `action_registry_discover`
List all registered actions with their available versions.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | No | Filter actions by name or description substring |
| `namespace` | string | No | Filter by namespace prefix (e.g., `ssh.*`, `docker.*`) |
| `limit` | int | No | Max results (default: 50) |

**Returns:** JSON array of action summaries with name, latest version, version list, and description.

**Example use case:** "What actions are available for file operations?" triggers a search with `query="file"`.

#### `action_registry_fetch`
Fetch a specific action schema by name and version.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Action name (e.g., `files.move`) |
| `version` | string | Yes | Version string (e.g., `1.1.0`) |

**Returns:** Full action schema, hash, signature block, verification status, and any deprecation info.

**Example use case:** Agent needs to invoke `ssh.exec@2.0.0` — fetches the schema to understand parameters and wire it into execution.

#### `action_registry_search`
Search actions by capability description using semantic matching.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `capability` | string | Yes | Natural language description of needed capability |
| `limit` | int | No | Max results (default: 10) |

**Returns:** Ranked list of matching actions with relevance indicators.

**Example use case:** "I need to deploy a Docker container" — finds `docker.deploy`, `docker.run`, `k8s.apply` without knowing exact action names.

### Verification

#### `action_registry_verify`
Verify the signature of a specific action version.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Action name |
| `version` | string | Yes | Version string |

**Returns:** Verification result with status, key ID, algorithm, hash, and any error details.

**Example use case:** Pre-flight check before executing an action — confirm the schema hasn't been tampered with and is signed by a trusted key.

### Publishing

#### `action_registry_publish`
Publish a new action schema with its signature.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Action name (dotted namespace, e.g., `ssh.exec`) |
| `version` | string | Yes | Version string (SemVer recommended) |
| `schema` | object | Yes | The action schema JSON |
| `signature` | object | Yes | Signature block: `{alg, kid, sig}` |

**Returns:** Published action with verification status, or error (immutability conflict, bad signature, unknown key).

**Example use case:** An agent develops a new capability and registers it with the ecosystem so other agents can discover and use it.

### Lifecycle (Phase 3+)

#### `action_registry_deprecate`
Mark an action version as deprecated.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Action name |
| `version` | string | Yes | Version to deprecate |
| `reason` | string | Yes | Why it's deprecated |
| `successor` | string | No | Recommended replacement version |

#### `action_registry_check_compatibility`
Check compatibility between two versions of an action.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Action name |
| `from_version` | string | Yes | Current version |
| `to_version` | string | Yes | Target version |

**Returns:** Compatibility assessment: compatible, breaking changes, added/removed fields.

---

## Response Format

Following the OrcaOps convention, all MCP tools return JSON strings with a consistent structure:

```python
# Success
{
    "success": True,
    "name": "files.move",
    "version": "1.1.0",
    "schema": { ... },
    "verified": True,
    ...
}

# Error
{
    "success": False,
    "error": {
        "code": "ACTION_NOT_FOUND",
        "message": "Action 'files.move' not found",
        "suggestion": "Use action_registry_discover to list available actions"
    }
}
```

The `suggestion` field helps the agent self-correct — if a lookup fails, the error tells it what tool to use next.

---

## Implementation Outline

```python
from mcp.server.fastmcp import FastMCP

server = FastMCP(
    name="action-registry",
    instructions=(
        "Action-Registry: Discover, verify, and publish signed action schemas. "
        "Use action_registry_discover to find available actions, "
        "action_registry_fetch to get a specific schema, "
        "action_registry_verify to check signature validity, "
        "and action_registry_publish to register new capabilities."
    ),
)


@server.tool(
    name="action_registry_discover",
    description="List registered actions. Optionally filter by query string or namespace.",
)
def action_registry_discover(
    query: str = "",
    namespace: str = "",
    limit: int = 50,
) -> str:
    ...


@server.tool(
    name="action_registry_fetch",
    description="Fetch a specific action schema by name and version. "
                "Returns the full schema, signature, hash, and verification status.",
)
def action_registry_fetch(name: str, version: str) -> str:
    ...


@server.tool(
    name="action_registry_verify",
    description="Verify the Ed25519 signature of an action. "
                "Returns whether the schema is trusted and signed by a known key.",
)
def action_registry_verify(name: str, version: str) -> str:
    ...


@server.tool(
    name="action_registry_publish",
    description="Publish a new signed action schema. Requires a valid signature "
                "from a trusted key. Immutable: cannot overwrite existing versions.",
)
def action_registry_publish(
    name: str,
    version: str,
    schema: dict,
    signature: dict,
) -> str:
    ...


def main():
    server.run(transport="stdio")
```

---

## Configuration

### Project MCP Config (`.claude/settings.local.json`)

```json
{
  "enableAllProjectMcpServers": true
}
```

### Project MCP Server Definition (`.mcp.json`)

```json
{
  "mcpServers": {
    "action-registry": {
      "command": "action-registry-mcp",
      "args": [],
      "env": {
        "TRUSTED_KEYS_JSON": "[{\"kid\":\"dev-root-1\",\"alg\":\"ed25519\",\"public_key\":\"base64:...\"}]",
        "ACTION_REGISTRY_API_KEY": "..."
      }
    }
  }
}
```

### Workspace-Level Access

When `enableAllProjectMcpServers: true` is set at the workspace level (already configured in `/root/projects/.claude/settings.local.json`), the Action-Registry MCP server is automatically available to Claude Code across all projects in the workspace.

This means any project — OrcaOps, personal-ops-console, ace-foundational-intent — can discover and consume action schemas without additional configuration.

---

## What This Enables

Once the MCP server is live, Claude Code can do things like:

**Discover before building:**
> "Before I implement this SSH command, let me check if there's already a registered action for it."
> → Calls `action_registry_discover(query="ssh")`
> → Finds `ssh.exec@2.0.0`, fetches schema, uses it instead of reimplementing

**Verify before executing:**
> "I'm about to use docker.deploy@1.0.0 in a production workflow. Let me verify the signature."
> → Calls `action_registry_verify(name="docker.deploy", version="1.0.0")`
> → Confirmed: signed by `infra-deploy-1`, trusted, not deprecated

**Publish new capabilities:**
> "I just built a new log analysis tool. Let me register it so other agents can find it."
> → Calls `action_registry_publish(name="logs.analyze", version="1.0.0", schema={...}, signature={...})`
> → Now discoverable by every agent in the swarm

**Self-correct on failure:**
> Tool returns `{success: false, error: {code: "VERSION_NOT_FOUND", suggestion: "Use action_registry_discover to list available versions"}}`
> → Agent calls discover, finds the correct version, retries

This is how the MCP server turns Claude Code from a tool user into an ecosystem participant.
