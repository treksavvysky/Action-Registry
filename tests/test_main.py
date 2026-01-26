from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_list_actions():
    response = client.get("/actions")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    item = data["items"][0]
    assert item["name"] == "files.move"
    assert "1.0.0" in item["versions"]
    assert item["latest_version"] == "1.1.0"

def test_get_action_version():
    response = client.get("/actions/files.move/versions/1.0.0")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "files.move"
    assert data["version"] == "1.0.0"
    assert "schema" in data
    assert "description" in data["schema"]
    assert data["hash"].startswith("sha256:")
    assert data["verified"] is False
    assert "signature" in data
    assert data["signature"]["kid"] == "dev-root-1"

def test_get_action_not_found():
    response = client.get("/actions/unknown/versions/1.0.0")
    assert response.status_code == 404

def test_get_version_not_found():
    response = client.get("/actions/files.move/versions/9.9.9")
    assert response.status_code == 404
