# Action-Registry

_Action-Registry_ is a lightweight clearing-house where human developers and autonomous agents can **publish, discover, and version callable “actions.”**  
Think of it as an **npm-style registry for OpenAI-function specs**: each action is described by a signed JSON schema, stored with semantic-versioning, and surfaced via a small FastAPI service.

---

## ✨ Why it exists
1. **Shared tool marketplace** – IntelliSwarm or any ACE agent can look up “`move_file` v2.1.0” and wire it instantly.  
2. **Single source of truth** – No more copy-pasted specs across repos; one endpoint returns the canonical definition.  
3. **Governance & traceability** – SHA-256 digests, deprecation flags, and audit trails make it easy to track what changed, when, and why.

---

## 🏗️ Architecture at a glance

| Layer | Tech | Notes |
|-------|------|-------|
| API   | **FastAPI** | REST + (future) WebSocket event stream |
| Data  | **PostgreSQL** via SQLAlchemy | JSONB column stores raw spec; semver columns enable quick latest-lookups |
| Auth  | API-Key header (upgradeable to JWT/OAuth) | First cut keeps it simple for internal use |
| CI/CD | GitHub Actions + Docker | Test, lint, build, and push image on every PR |

---

## 🚀 Quick start (dev)

```bash
# clone & enter repo
git clone https://github.com/your-org/action-registry.git
cd action-registry

# spin up API + DB
docker compose up --build
# service listens on http://localhost:8000
