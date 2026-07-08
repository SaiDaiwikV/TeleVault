"""Auth: password hashing, register/login, token gating, rate limiting."""
from app.auth import hash_password, verify_password


def test_hash_password_roundtrip_and_uniqueness():
    h1 = hash_password("correct horse battery staple")
    h2 = hash_password("correct horse battery staple")
    # Per-hash random salt → same password yields different stored hashes.
    assert h1 != h2
    assert h1.startswith("pbkdf2_sha256$600000$")
    assert verify_password("correct horse battery staple", h1)
    assert not verify_password("wrong", h1)


def test_verify_password_backward_compatible_iterations():
    """A hash minted with an older iteration count still verifies, because the
    count is encoded in the stored string rather than assumed."""
    import hashlib
    import secrets

    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", b"legacy-pass", bytes.fromhex(salt), 260_000).hex()
    legacy = f"pbkdf2_sha256$260000${salt}${digest}"
    assert verify_password("legacy-pass", legacy)
    assert not verify_password("nope", legacy)


def test_verify_password_handles_none_and_garbage():
    assert not verify_password("anything", None)  # OAuth-only account
    assert not verify_password("anything", "not-a-valid-hash")


def test_register_then_login(client):
    reg = client.post("/api/auth/register", json={"username": "Bob", "password": "hunter2hunter2"})
    assert reg.status_code == 200
    body = reg.json()
    assert body["user"]["username"] == "bob"  # normalised to lowercase
    assert body["token"]

    login = client.post("/api/auth/login", json={"username": "bob", "password": "hunter2hunter2"})
    assert login.status_code == 200
    assert login.json()["token"]


def test_duplicate_registration_conflicts(client):
    client.post("/api/auth/register", json={"username": "carol", "password": "password123"})
    dup = client.post("/api/auth/register", json={"username": "carol", "password": "password123"})
    assert dup.status_code == 409


def test_login_wrong_password_401(client):
    client.post("/api/auth/register", json={"username": "dave", "password": "password123"})
    bad = client.post("/api/auth/login", json={"username": "dave", "password": "wrongpass1"})
    assert bad.status_code == 401


def test_short_password_rejected_by_schema(client):
    resp = client.post("/api/auth/register", json={"username": "eve", "password": "short"})
    assert resp.status_code == 422  # min_length=8


def test_protected_route_requires_token(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/items").status_code == 401


def test_me_returns_current_user(auth_client):
    resp = auth_client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_auth_rate_limit_trips(client, monkeypatch):
    from app import security

    # Tighten the limiter so the test is fast and deterministic.
    monkeypatch.setattr(security.auth_rate_limiter, "max_attempts", 3)
    security.auth_rate_limiter._hits.clear()

    codes = [
        client.post("/api/auth/login", json={"username": "ghost", "password": "whatever12"}).status_code
        for _ in range(5)
    ]
    assert 429 in codes, codes
