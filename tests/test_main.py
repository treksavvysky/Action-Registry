import asyncio
import base64
from unittest.mock import patch

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.main as main_module
from app.crypto import canonical_dumps, sha256_bytes, sha256_prefixed_hex
from app.db import get_db
from app.main import app
from app.models import Action, ActionVersion, Base
from app.settings import TRUSTED_KEYS


TEST_API_KEY = "test-secret-key"


def run_async(coro):
    return asyncio.run(coro)


class ASGIClient:
    def request(self, method: str, path: str, **kwargs):
        async def _request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, path, **kwargs)

        return run_async(_request())

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _init_models():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
            )
            expected_head = main_module.get_expected_migration_head()
            if expected_head:
                await conn.execute(text("DELETE FROM alembic_version"))
                await conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                    {"version_num": expected_head},
                )

    run_async(_init_models())

    async def override_get_db():
        async with TestingSessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    yield ASGIClient(), TestingSessionLocal

    app.dependency_overrides.clear()

    async def _teardown_models():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    run_async(_teardown_models())


def generate_key_and_sig(payload):
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_bytes = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    canonical = canonical_dumps(payload)
    hash_val = sha256_bytes(canonical)
    sig = priv.sign(hash_val)
    sig_b64 = base64.b64encode(sig).decode("utf-8")

    return pub_bytes, sig_b64, priv


def seed_action(db_factory, name: str, version: str, schema: dict, sig_alg: str, sig_kid: str, sig_b64: str):
    async def _seed():
        async with db_factory() as db:
            if not await db.get(Action, name):
                db.add(Action(name=name))
            db.add(
                ActionVersion(
                    name=name,
                    version=version,
                    schema_json=schema,
                    hash=sha256_prefixed_hex(canonical_dumps(schema)),
                    sig_alg=sig_alg,
                    sig_kid=sig_kid,
                    sig_b64=sig_b64,
                )
            )
            await db.commit()

    run_async(_seed())


def seed_action_name(db_factory, name: str):
    async def _seed():
        async with db_factory() as db:
            db.add(Action(name=name))
            await db.commit()

    run_async(_seed())


def _publish(client, name, version, schema, sig_block, api_key=TEST_API_KEY):
    headers = {}
    if api_key is not None:
        headers["x-api-key"] = api_key
    return client.post(
        f"/actions/{name}/versions/{version}",
        json={"schema": schema, "signature": sig_block},
        headers=headers,
    )


def test_healthz(client):
    c, _ = client
    response = c.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_probe_endpoints(client):
    c, _ = client
    assert c.get("/livez").status_code == 200
    ready = c.get("/readyz")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_readyz_fails_when_migrations_behind(client):
    c, db_factory = client

    async def _downgrade_marker():
        async with db_factory() as db:
            await db.execute(text("DELETE FROM alembic_version"))
            await db.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                {"version_num": "000000000000"},
            )
            await db.commit()

    run_async(_downgrade_marker())

    resp = c.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "NOT_READY_MIGRATIONS"


def test_list_actions(client):
    c, db_factory = client
    payload1 = {"description": "Move v1", "parameters": {"source": {"type": "string"}}}
    payload2 = {
        "description": "Move v2",
        "parameters": {"source": {"type": "string"}, "overwrite": {"type": "boolean"}},
    }
    pub_bytes, sig1, priv = generate_key_and_sig(payload1)
    sig2 = base64.b64encode(priv.sign(sha256_bytes(canonical_dumps(payload2)))).decode("utf-8")

    with patch.dict(TRUSTED_KEYS, {"test-key": ("ed25519", pub_bytes)}, clear=True):
        seed_action(db_factory, "files.move", "1.0.0", payload1, "ed25519", "test-key", sig1)
        seed_action(db_factory, "files.move", "1.1.0", payload2, "ed25519", "test-key", sig2)

        response = c.get("/actions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["name"] == "files.move"
        assert item["latest_version"] == "1.1.0"
        assert item["versions"] == ["1.0.0", "1.1.0"]


def test_list_actions_filters_and_pagination(client):
    c, db_factory = client
    payload = {"description": "SSH command execution", "parameters": {"cmd": {"type": "string"}}}
    pub_bytes, sig, _ = generate_key_and_sig(payload)

    with patch.dict(TRUSTED_KEYS, {"dev-root-1": ("ed25519", pub_bytes)}, clear=True):
        seed_action(db_factory, "ssh.exec", "1.0.0", payload, "ed25519", "dev-root-1", sig)
        seed_action(db_factory, "files.move", "1.0.0", {"description": "Move file"}, "ed25519", "dev-root-1", sig)

        by_query = c.get("/actions", params={"q": "ssh"})
        assert by_query.status_code == 200
        assert [x["name"] for x in by_query.json()["items"]] == ["ssh.exec"]

        by_kid = c.get("/actions", params={"kid": "dev-root-1"})
        assert by_kid.status_code == 200
        assert len(by_kid.json()["items"]) == 2

        paged = c.get("/actions", params={"offset": 1, "limit": 1})
        assert paged.status_code == 200
        assert len(paged.json()["items"]) == 1


def test_get_action_success(client):
    c, db_factory = client
    payload = {"foo": "bar"}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    with patch.dict(TRUSTED_KEYS, {"test-key": ("ed25519", pub_bytes)}, clear=True):
        seed_action(db_factory, "test.action", "1.0.0", payload, "ed25519", "test-key", sig_b64)

        response = c.get("/actions/test.action/versions/1.0.0")
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["verify_error"] is None


def test_get_action_tamper(client):
    c, db_factory = client
    payload = {"foo": "bar"}
    tampered_payload = {"foo": "baz"}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    with patch.dict(TRUSTED_KEYS, {"test-key": ("ed25519", pub_bytes)}, clear=True):
        seed_action(db_factory, "test.action", "1.0.0", tampered_payload, "ed25519", "test-key", sig_b64)

        response = c.get("/actions/test.action/versions/1.0.0")
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is False
        assert data["verify_error"] == "Bad signature"


def test_get_action_unknown_key(client):
    c, db_factory = client
    payload = {"foo": "bar"}
    _, sig_b64, _ = generate_key_and_sig(payload)

    with patch.dict(TRUSTED_KEYS, {}, clear=True):
        seed_action(db_factory, "test.action", "1.0.0", payload, "ed25519", "unknown-key", sig_b64)

        response = c.get("/actions/test.action/versions/1.0.0")
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is False
        assert data["verify_error"] == "Unknown key id"


def test_verify_endpoint(client):
    c, db_factory = client
    payload = {"foo": "bar"}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    with patch.dict(TRUSTED_KEYS, {"test-key": ("ed25519", pub_bytes)}, clear=True):
        seed_action(db_factory, "test.action", "1.0.0", payload, "ed25519", "test-key", sig_b64)

        response = c.get("/actions/test.action/versions/1.0.0/verify")
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["kid"] == "test-key"
        assert data["alg"] == "ed25519"


def test_not_found_errors(client):
    c, db_factory = client

    response = c.get("/actions/missing/versions/1.0.0")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACTION_NOT_FOUND"

    seed_action_name(db_factory, "exists")

    response = c.get("/actions/exists/versions/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VERSION_NOT_FOUND"


def test_publish_success(client):
    c, _ = client
    payload = {"description": "Run a command", "parameters": {"cmd": {"type": "string"}}}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    mock_keys = {"pub-key-1": ("ed25519", pub_bytes)}
    sig_block = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_b64}

    with patch.dict(TRUSTED_KEYS, mock_keys, clear=True), patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish(c, "shell.exec", "1.0.0", payload, sig_block)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "shell.exec"
        assert data["version"] == "1.0.0"
        assert data["verified"] is True
        assert data["schema"] == payload

        get_resp = c.get("/actions/shell.exec/versions/1.0.0")
        assert get_resp.status_code == 200
        assert get_resp.json()["verified"] is True


def test_publish_idempotent(client):
    c, _ = client
    payload = {"description": "Idempotent test"}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    mock_keys = {"pub-key-1": ("ed25519", pub_bytes)}
    sig_block = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_b64}

    with patch.dict(TRUSTED_KEYS, mock_keys, clear=True), patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp1 = _publish(c, "idem.action", "1.0.0", payload, sig_block)
        assert resp1.status_code == 201

        resp2 = _publish(c, "idem.action", "1.0.0", payload, sig_block)
        assert resp2.status_code == 200


def test_publish_immutability_conflict(client):
    c, _ = client
    payload_v1 = {"description": "Original"}
    payload_v2 = {"description": "Modified"}
    pub_bytes, sig_v1, priv = generate_key_and_sig(payload_v1)

    mock_keys = {"pub-key-1": ("ed25519", pub_bytes)}
    sig_block_v1 = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_v1}

    with patch.dict(TRUSTED_KEYS, mock_keys, clear=True), patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp1 = _publish(c, "conflict.action", "1.0.0", payload_v1, sig_block_v1)
        assert resp1.status_code == 201

        canonical_v2 = canonical_dumps(payload_v2)
        hash_v2 = sha256_bytes(canonical_v2)
        sig_v2_real = base64.b64encode(priv.sign(hash_v2)).decode("utf-8")
        sig_block_v2_real = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_v2_real}

        resp2 = _publish(c, "conflict.action", "1.0.0", payload_v2, sig_block_v2_real)
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "IMMUTABLE_VERSION_CONFLICT"


def test_publish_bad_signature(client):
    c, _ = client
    payload = {"description": "Bad sig"}
    pub_bytes, _, _ = generate_key_and_sig(payload)

    mock_keys = {"pub-key-1": ("ed25519", pub_bytes)}
    bad_sig = base64.b64encode(b"x" * 64).decode("utf-8")
    sig_block = {"alg": "ed25519", "kid": "pub-key-1", "sig": bad_sig}

    with patch.dict(TRUSTED_KEYS, mock_keys, clear=True), patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish(c, "bad.sig", "1.0.0", payload, sig_block)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "BAD_SIGNATURE"


def test_publish_unknown_key(client):
    c, _ = client
    payload = {"description": "Unknown key"}
    _, sig_b64, _ = generate_key_and_sig(payload)
    sig_block = {"alg": "ed25519", "kid": "nonexistent-key", "sig": sig_b64}

    with patch.dict(TRUSTED_KEYS, {}, clear=True), patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish(c, "unknown.key", "1.0.0", payload, sig_block)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "UNKNOWN_KEY_ID"


def test_publish_no_auth(client):
    c, _ = client
    payload = {"description": "No auth"}
    sig_block = {"alg": "ed25519", "kid": "k", "sig": "xxx"}

    with patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish(c, "no.auth", "1.0.0", payload, sig_block, api_key=None)
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_publish_wrong_auth(client):
    c, _ = client
    payload = {"description": "Wrong auth"}
    sig_block = {"alg": "ed25519", "kid": "k", "sig": "xxx"}

    with patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish(c, "wrong.auth", "1.0.0", payload, sig_block, api_key="wrong-key")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_metrics_endpoint(client):
    c, _ = client
    c.get("/healthz")
    resp = c.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "action_registry_publish_total" in text
    assert "action_registry_http_requests_total" in text
    assert "action_registry_http_request_duration_seconds_bucket" in text
    assert 'le="+Inf"' in text
    assert "action_registry_http_request_duration_seconds_count" in text
    assert "action_registry_http_request_duration_seconds_sum" in text


def test_openapi_has_route_and_model_metadata(client):
    c, _ = client
    resp = c.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()

    list_actions_op = spec["paths"]["/actions"]["get"]
    assert list_actions_op["summary"] == "Discover Actions"
    assert "pagination controls" in list_actions_op["description"]

    publish_req_schema = spec["components"]["schemas"]["PublishRequest"]
    assert "example" in publish_req_schema
    assert "signature" in publish_req_schema["properties"]
