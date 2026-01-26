import pytest
from app.crypto import canonical_dumps, sha256_hex, verify_signature_ed25519

def test_canonical_dumps_determinism():
    obj1 = {"b": 2, "a": 1}
    obj2 = {"a": 1, "b": 2}

    assert canonical_dumps(obj1) == canonical_dumps(obj2)
    assert canonical_dumps(obj1) == b'{"a":1,"b":2}'

def test_canonical_dumps_nested():
    obj1 = {"c": {"y": 2, "x": 1}, "d": [3, 2, 1]}
    obj2 = {"d": [3, 2, 1], "c": {"x": 1, "y": 2}}

    # Arrays order should be preserved, keys sorted
    assert canonical_dumps(obj1) == canonical_dumps(obj2)
    assert canonical_dumps(obj1) == b'{"c":{"x":1,"y":2},"d":[3,2,1]}'

def test_canonical_dumps_utf8():
    obj = {"val": "é"}
    # UTF-8 encoded, not escaped
    # "é" in utf-8 is \xc3\xa9
    expected = b'{"val":"\xc3\xa9"}'
    assert canonical_dumps(obj) == expected

def test_sha256_hex():
    payload = b'test'
    # echo -n "test" | sha256sum
    # 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
    expected = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert sha256_hex(payload) == expected

def test_verify_signature_stub():
    assert verify_signature_ed25519(b"hash", "sig", "key") is False
