from fastapi.testclient import TestClient
from app.main import app, ACTIONS_DB
from app.settings import TRUSTED_KEYS
from app.crypto import canonical_dumps, sha256_bytes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import base64
import pytest
from unittest.mock import patch

client = TestClient(app)

def generate_key_and_sig(payload):
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_bytes = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    canonical = canonical_dumps(payload)
    hash_val = sha256_bytes(canonical)
    sig = priv.sign(hash_val)
    sig_b64 = base64.b64encode(sig).decode('utf-8')

    return pub_bytes, sig_b64

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
    pub_bytes, sig_b64 = generate_key_and_sig(payload)

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
    pub_bytes, sig_b64 = generate_key_and_sig(payload)

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
    _, sig_b64 = generate_key_and_sig(payload)

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
