from fastapi.testclient import TestClient
import app.main as main_module
from app.main import app, ACTIONS_DB
from app.settings import TRUSTED_KEYS
from app.crypto import canonical_dumps, sha256_bytes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import base64
import pytest
from unittest.mock import patch

client = TestClient(app)

TEST_API_KEY = "test-secret-key"


def generate_key_and_sig(payload):
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_bytes = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    canonical = canonical_dumps(payload)
    hash_val = sha256_bytes(canonical)
    sig = priv.sign(hash_val)
    sig_b64 = base64.b64encode(sig).decode('utf-8')

    return pub_bytes, sig_b64, priv

def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_list_actions():
    response = client.get("/actions")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # Basic assertions against the default static DB
    assert len(data["items"]) >= 1
    item = next((i for i in data["items"] if i["name"] == "files.move"), None)
    assert item is not None
    assert "1.0.0" in item["versions"]
    assert item["latest_version"] == "1.1.0"

def test_get_action_success():
    payload = {"foo": "bar"}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    mock_db = {
        "test.action": {
            "1.0.0": {
                "schema": payload,
                "signature": {
                    "alg": "ed25519",
                    "kid": "test-key",
                    "sig": sig_b64
                }
            }
        }
    }

    mock_keys = {
        "test-key": ("ed25519", pub_bytes)
    }

    with patch.dict(ACTIONS_DB, mock_db, clear=True):
        with patch.dict(TRUSTED_KEYS, mock_keys, clear=True):
            response = client.get("/actions/test.action/versions/1.0.0")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test.action"
            assert data["version"] == "1.0.0"
            assert data["verified"] is True
            assert data["verify_error"] is None

def test_get_action_tamper():
    payload = {"foo": "bar"}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    # Tamper payload
    tampered_payload = {"foo": "baz"}

    mock_db = {
        "test.action": {
            "1.0.0": {
                "schema": tampered_payload,
                "signature": {
                    "alg": "ed25519",
                    "kid": "test-key",
                    "sig": sig_b64
                }
            }
        }
    }

    mock_keys = {
        "test-key": ("ed25519", pub_bytes)
    }

    with patch.dict(ACTIONS_DB, mock_db, clear=True):
        with patch.dict(TRUSTED_KEYS, mock_keys, clear=True):
            response = client.get("/actions/test.action/versions/1.0.0")
            assert response.status_code == 200
            data = response.json()
            assert data["verified"] is False
            assert data["verify_error"] == "Bad signature"

def test_get_action_unknown_key():
    payload = {"foo": "bar"}
    _, sig_b64, _ = generate_key_and_sig(payload)

    mock_db = {
        "test.action": {
            "1.0.0": {
                "schema": payload,
                "signature": {
                    "alg": "ed25519",
                    "kid": "unknown-key",
                    "sig": sig_b64
                }
            }
        }
    }

    with patch.dict(ACTIONS_DB, mock_db, clear=True):
        with patch.dict(TRUSTED_KEYS, {}, clear=True):
            response = client.get("/actions/test.action/versions/1.0.0")
            assert response.status_code == 200
            data = response.json()
            assert data["verified"] is False
            assert data["verify_error"] == "Unknown key id"

def test_not_found_errors():
    response = client.get("/actions/missing/versions/1.0.0")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "ACTION_NOT_FOUND"

    mock_db = {"exists": {}}
    with patch.dict(ACTIONS_DB, mock_db, clear=True):
        response = client.get("/actions/exists/versions/missing")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "VERSION_NOT_FOUND"


# --- Publish endpoint tests ---

def _publish(name, version, schema, sig_block, api_key=TEST_API_KEY):
    headers = {}
    if api_key is not None:
        headers["x-api-key"] = api_key
    return client.post(
        f"/actions/{name}/versions/{version}",
        json={"schema": schema, "signature": sig_block},
        headers=headers,
    )


def test_publish_success():
    payload = {"description": "Run a command", "parameters": {"cmd": {"type": "string"}}}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    mock_keys = {"pub-key-1": ("ed25519", pub_bytes)}
    sig_block = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_b64}

    with patch.dict(ACTIONS_DB, {}, clear=True), \
         patch.dict(TRUSTED_KEYS, mock_keys, clear=True), \
         patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish("shell.exec", "1.0.0", payload, sig_block)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "shell.exec"
        assert data["version"] == "1.0.0"
        assert data["verified"] is True
        assert data["schema"] == payload

        # Verify it's discoverable via GET
        get_resp = client.get("/actions/shell.exec/versions/1.0.0")
        assert get_resp.status_code == 200
        assert get_resp.json()["verified"] is True


def test_publish_idempotent():
    payload = {"description": "Idempotent test"}
    pub_bytes, sig_b64, _ = generate_key_and_sig(payload)

    mock_keys = {"pub-key-1": ("ed25519", pub_bytes)}
    sig_block = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_b64}

    with patch.dict(ACTIONS_DB, {}, clear=True), \
         patch.dict(TRUSTED_KEYS, mock_keys, clear=True), \
         patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp1 = _publish("idem.action", "1.0.0", payload, sig_block)
        assert resp1.status_code == 201

        resp2 = _publish("idem.action", "1.0.0", payload, sig_block)
        assert resp2.status_code == 200


def test_publish_immutability_conflict():
    payload_v1 = {"description": "Original"}
    payload_v2 = {"description": "Modified"}
    pub_bytes, sig_v1, priv = generate_key_and_sig(payload_v1)
    _, sig_v2, _ = generate_key_and_sig(payload_v2)

    mock_keys = {"pub-key-1": ("ed25519", pub_bytes)}
    sig_block_v1 = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_v1}
    sig_block_v2 = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_v2}

    with patch.dict(ACTIONS_DB, {}, clear=True), \
         patch.dict(TRUSTED_KEYS, mock_keys, clear=True), \
         patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp1 = _publish("conflict.action", "1.0.0", payload_v1, sig_block_v1)
        assert resp1.status_code == 201

        # v2 has a different schema signed by a different key — sig won't verify against pub_bytes
        # But immutability check happens after sig check, so we need v2 signed by the same key
        # Re-sign payload_v2 with the original private key
        canonical_v2 = canonical_dumps(payload_v2)
        hash_v2 = sha256_bytes(canonical_v2)
        sig_v2_real = base64.b64encode(priv.sign(hash_v2)).decode('utf-8')
        sig_block_v2_real = {"alg": "ed25519", "kid": "pub-key-1", "sig": sig_v2_real}

        resp2 = _publish("conflict.action", "1.0.0", payload_v2, sig_block_v2_real)
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "IMMUTABLE_VERSION_CONFLICT"


def test_publish_bad_signature():
    payload = {"description": "Bad sig"}
    pub_bytes, _, _ = generate_key_and_sig(payload)

    mock_keys = {"pub-key-1": ("ed25519", pub_bytes)}
    bad_sig = base64.b64encode(b'x' * 64).decode('utf-8')
    sig_block = {"alg": "ed25519", "kid": "pub-key-1", "sig": bad_sig}

    with patch.dict(ACTIONS_DB, {}, clear=True), \
         patch.dict(TRUSTED_KEYS, mock_keys, clear=True), \
         patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish("bad.sig", "1.0.0", payload, sig_block)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "BAD_SIGNATURE"


def test_publish_unknown_key():
    payload = {"description": "Unknown key"}
    _, sig_b64, _ = generate_key_and_sig(payload)
    sig_block = {"alg": "ed25519", "kid": "nonexistent-key", "sig": sig_b64}

    with patch.dict(ACTIONS_DB, {}, clear=True), \
         patch.dict(TRUSTED_KEYS, {}, clear=True), \
         patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish("unknown.key", "1.0.0", payload, sig_block)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "UNKNOWN_KEY_ID"


def test_publish_no_auth():
    payload = {"description": "No auth"}
    sig_block = {"alg": "ed25519", "kid": "k", "sig": "xxx"}

    with patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish("no.auth", "1.0.0", payload, sig_block, api_key=None)
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_publish_wrong_auth():
    payload = {"description": "Wrong auth"}
    sig_block = {"alg": "ed25519", "kid": "k", "sig": "xxx"}

    with patch.object(main_module, "API_KEY", TEST_API_KEY):
        resp = _publish("wrong.auth", "1.0.0", payload, sig_block, api_key="wrong-key")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"
